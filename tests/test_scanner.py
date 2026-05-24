from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from filter_pattern.models import Candle, VCPEvidence
from filter_pattern.scanner import scan, scan_all_csv, scan_all_market, scan_market
from filter_pattern.universe import UniverseSymbol
from tests.test_detector import make_flat_series, make_series


def test_scan_records_missing_symbol_csv_as_rejected_data_error(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        "timeframe: D1\n"
        "symbols:\n"
        "  - symbol: AAPL\n"
        "    market: US stock\n"
        "    tradingview_symbol: NASDAQ:AAPL\n"
        "    csv_path: data/AAPL_D1.csv\n"
    )

    results_path = scan(config_path, tmp_path / "reports/latest", "D1")
    payload = json.loads(results_path.read_text())

    assert payload["scanned_symbols"] == 1
    assert payload["qualified_count"] == 0
    assert payload["rejected"][0]["symbol"] == "AAPL"
    assert payload["rejected"][0]["evidence"]["status"] == "data_error"
    assert "CSV not found" in payload["rejected"][0]["evidence"]["failures"][0]
    assert (tmp_path / "reports/latest/index.html").exists()


def test_scan_market_uses_downloaded_data_and_writes_candidate(tmp_path: Path, monkeypatch) -> None:
    def fake_loader(symbols: list[str], period: str = "2y", timeframe: str = "D1"):
        return {symbol: make_series([20, 12, 6], current_close=96, late_volume=80_000) for symbol in symbols}

    monkeypatch.setattr("filter_pattern.scanner.load_yahoo_ohlcv_many", fake_loader)

    results_path = scan_market(tmp_path / "reports/latest", limit=1)
    payload = json.loads(results_path.read_text())

    assert payload["scanned_symbols"] == 1
    assert payload["qualified_count"] == 1
    assert payload["candidates"][0]["chart_path"]
    assert (tmp_path / "reports/latest/index.html").exists()


def test_scan_all_csv_uses_tradingview_csv_source_and_all_patterns(tmp_path: Path) -> None:
    csv_path = tmp_path / "AAPL_H4.csv"
    candles = make_series([20, 12, 6], current_close=96, late_volume=80_000)
    csv_path.write_text(
        "time,open,high,low,close,volume\n"
        + "".join(
            f"{candle.datetime.isoformat()},{candle.open},{candle.high},{candle.low},{candle.close},{candle.volume}\n"
            for candle in candles
        )
    )
    config_path = tmp_path / "config.yml"
    config_path.write_text(
        "timeframe: H4\n"
        "symbols:\n"
        "  - symbol: AAPL\n"
        "    market: US stock\n"
        "    tradingview_symbol: NASDAQ:AAPL\n"
        f"    csv_path: {csv_path}\n"
    )

    results_path = scan_all_csv(config_path, tmp_path / "reports/tv", "H4")
    payload = json.loads(results_path.read_text())

    assert payload["config"]["data_source"] == "TradingView CSV"
    assert payload["timeframe"] == "H4"
    assert payload["evaluation_count"] == 13
    assert payload["scanned_symbols"] == 1
    assert payload["candidates"][0]["timeframe"] == "H4"
    assert (tmp_path / "reports/tv/index.html").exists()


def test_scan_market_passes_h4_timeframe_to_provider_and_report(tmp_path: Path, monkeypatch) -> None:
    seen: dict[str, str] = {}

    def fake_loader(symbols: list[str], period: str = "2y", timeframe: str = "D1"):
        seen["timeframe"] = timeframe
        return {symbol: make_series([20, 12, 6], current_close=96, late_volume=80_000) for symbol in symbols}

    monkeypatch.setattr("filter_pattern.scanner.load_yahoo_ohlcv_many", fake_loader)

    results_path = scan_market(tmp_path / "reports/h4", timeframe="H4", limit=1)
    payload = json.loads(results_path.read_text())
    html = (tmp_path / "reports/h4/index.html").read_text()

    assert seen["timeframe"] == "H4"
    assert payload["timeframe"] == "H4"
    assert payload["config"]["timeframe"] == "H4"
    assert payload["candidates"][0]["timeframe"] == "H4"
    assert 'id="timeframeFilter"' in html
    assert 'data-timeframe="H4"' in html


def test_scan_market_mixed_provider_uses_ccxt_for_crypto_and_yahoo_for_other_markets(
    tmp_path: Path,
    monkeypatch,
) -> None:
    universe = [
        UniverseSymbol("AAPL", "US stock", "NASDAQ:AAPL", "AAPL"),
        UniverseSymbol("FPT", "Vietnam stock", "HOSE:FPT", "FPT.VN"),
        UniverseSymbol("BTCUSDT", "Crypto", "BINANCE:BTCUSDT", "BTC-USD"),
    ]
    seen: dict[str, list[str]] = {}

    def fake_universe(name: str):
        return universe

    def fake_yahoo(symbols: list[str], period: str = "2y", timeframe: str = "D1"):
        seen["yahoo"] = symbols
        return {symbol: make_series([20, 12, 6], current_close=96, late_volume=80_000) for symbol in symbols}

    def fake_ccxt(symbols: list[str], period: str = "2y", timeframe: str = "D1", exchange_id: str = "", market_type: str = "spot"):
        seen["ccxt"] = symbols
        seen["ccxt_exchange_id"] = [exchange_id]
        seen["ccxt_market_type"] = [market_type]
        return {symbol: make_series([20, 12, 6], current_close=96, late_volume=80_000) for symbol in symbols}

    def fake_vnstock(symbols: list[str], period: str = "2y", timeframe: str = "D1"):
        seen["vnstock"] = symbols
        return {symbol: make_series([20, 12, 6], current_close=96, late_volume=80_000) for symbol in symbols}

    monkeypatch.setattr("filter_pattern.scanner.get_universe", fake_universe)
    monkeypatch.setattr(
        "filter_pattern.scanner.expand_crypto_universe",
        lambda items, exchange_id, market_type="perp", max_symbols=None: items,
    )
    monkeypatch.setattr("filter_pattern.scanner.load_yahoo_ohlcv_many", fake_yahoo)
    monkeypatch.setattr("filter_pattern.scanner.load_ccxt_ohlcv_many", fake_ccxt)
    monkeypatch.setattr("filter_pattern.scanner.load_vnstock_ohlcv_many", fake_vnstock)

    results_path = scan_market(tmp_path / "reports/mixed", data_provider="mixed")
    payload = json.loads(results_path.read_text())

    assert seen["yahoo"] == ["AAPL", "FPT.VN"]
    assert seen["ccxt"] == ["BTCUSDT"]
    assert "vnstock" not in seen
    assert payload["config"]["data_provider"] == "mixed"
    assert payload["config"]["data_source"] == "Yahoo Finance + VNStock + CCXT"
    assert payload["scanned_symbols"] == 3


def test_scan_market_expands_crypto_universe_for_mixed_provider(tmp_path: Path, monkeypatch) -> None:
    universe = [
        UniverseSymbol("BTCUSDT", "Crypto", "BINANCE:BTCUSDT", "BTC-USD"),
    ]
    expanded = [
        UniverseSymbol("BTCUSDT", "Crypto", "BINANCE:BTCUSDT", "BTC-USD"),
        UniverseSymbol("PEPEUSDT", "Crypto", "MEXC:PEPEUSDT", "PEPE-USD"),
    ]
    seen: dict[str, list[str]] = {}

    def fake_universe(name: str):
        return universe

    def fake_expand(
        items: list[UniverseSymbol],
        exchange_id: str,
        market_type: str = "spot",
        max_symbols: int | None = None,
    ):
        seen["expand_input"] = [item.symbol for item in items]
        seen["exchange_id"] = [exchange_id]
        seen["market_type"] = [market_type]
        seen["max_symbols"] = [] if max_symbols is None else [str(max_symbols)]
        return expanded

    def fake_yahoo(symbols: list[str], period: str = "2y", timeframe: str = "D1"):
        seen["yahoo"] = symbols
        return {}

    def fake_ccxt(
        symbols: list[str],
        period: str = "2y",
        timeframe: str = "D1",
        exchange_id: str = "",
        market_type: str = "spot",
    ):
        seen["ccxt"] = symbols
        seen["ccxt_exchange_id"] = [exchange_id]
        seen["ccxt_market_type"] = [market_type]
        return {symbol: make_series([20, 12, 6], current_close=96, late_volume=80_000) for symbol in symbols}

    monkeypatch.setattr("filter_pattern.scanner.get_universe", fake_universe)
    monkeypatch.setattr("filter_pattern.scanner.expand_crypto_universe", fake_expand)
    monkeypatch.setattr("filter_pattern.scanner.load_yahoo_ohlcv_many", fake_yahoo)
    monkeypatch.setattr("filter_pattern.scanner.load_ccxt_ohlcv_many", fake_ccxt)
    monkeypatch.setenv("CRYPTO_MODE", "core")
    monkeypatch.setenv("CRYPTO_MAX_SYMBOLS", "2")
    monkeypatch.setenv("CRYPTO_MARKET_TYPE", "perp")

    results_path = scan_market(tmp_path / "reports/crypto-expanded", data_provider="mixed", markets="Crypto")
    payload = json.loads(results_path.read_text())

    assert seen["expand_input"] == ["BTCUSDT"]
    assert seen["exchange_id"] == ["binance,bybit,okx"]
    assert seen["market_type"] == ["perp"]
    assert seen["max_symbols"] == ["2"]
    assert seen["ccxt"] == ["BTCUSDT", "PEPEUSDT"]
    assert seen["ccxt_exchange_id"] == ["binance,bybit,okx"]
    assert seen["ccxt_market_type"] == ["perp"]
    assert payload["scanned_symbols"] == 2
    assert {item["symbol"] for item in payload["candidates"]} == {"BTCUSDT", "PEPEUSDT"}


def test_scan_market_static_crypto_mode_skips_dynamic_expansion(tmp_path: Path, monkeypatch) -> None:
    universe = [
        UniverseSymbol("BTCUSDT", "Crypto", "BINANCE:BTCUSDT", "BTC-USD"),
    ]
    seen: dict[str, list[str]] = {}

    def fake_universe(name: str):
        return universe

    def fake_expand(items: list[UniverseSymbol], exchange_id: str, market_type: str = "spot", max_symbols: int | None = None):
        raise AssertionError("static crypto mode should not call dynamic expansion")

    def fake_yahoo(symbols: list[str], period: str = "2y", timeframe: str = "D1"):
        return {}

    def fake_ccxt(
        symbols: list[str],
        period: str = "2y",
        timeframe: str = "D1",
        exchange_id: str = "",
        market_type: str = "spot",
    ):
        seen["ccxt"] = symbols
        return {symbol: make_series([20, 12, 6], current_close=96, late_volume=80_000) for symbol in symbols}

    monkeypatch.setattr("filter_pattern.scanner.get_universe", fake_universe)
    monkeypatch.setattr("filter_pattern.scanner.expand_crypto_universe", fake_expand)
    monkeypatch.setattr("filter_pattern.scanner.load_yahoo_ohlcv_many", fake_yahoo)
    monkeypatch.setattr("filter_pattern.scanner.load_ccxt_ohlcv_many", fake_ccxt)
    monkeypatch.setenv("CRYPTO_MODE", "static")

    results_path = scan_market(tmp_path / "reports/crypto-static", data_provider="mixed", markets="Crypto")
    payload = json.loads(results_path.read_text())

    assert seen["ccxt"] == ["BTCUSDT"]
    assert payload["scanned_symbols"] == 1
    assert payload["config"]["crypto_mode"] == "static"


def test_mixed_provider_falls_back_to_vnstock_for_missing_vietnam_data(tmp_path: Path, monkeypatch) -> None:
    universe = [
        UniverseSymbol("FPT", "Vietnam stock", "HOSE:FPT", "FPT.VN"),
    ]
    seen: dict[str, list[str]] = {}

    def fake_universe(name: str):
        return universe

    def fake_yahoo(symbols: list[str], period: str = "2y", timeframe: str = "D1"):
        seen["yahoo"] = symbols
        return {symbol: ValueError("missing yahoo data") for symbol in symbols}

    def fake_vnstock(symbols: list[str], period: str = "2y", timeframe: str = "D1"):
        seen["vnstock"] = symbols
        return {symbol: make_series([20, 12, 6], current_close=96, late_volume=80_000) for symbol in symbols}

    monkeypatch.setattr("filter_pattern.scanner.get_universe", fake_universe)
    monkeypatch.setattr("filter_pattern.scanner.load_yahoo_ohlcv_many", fake_yahoo)
    monkeypatch.setattr("filter_pattern.scanner.load_vnstock_ohlcv_many", fake_vnstock)

    results_path = scan_market(tmp_path / "reports/mixed-vn", data_provider="mixed")
    payload = json.loads(results_path.read_text())

    assert seen["yahoo"] == ["FPT.VN"]
    assert seen["vnstock"] == ["FPT"]
    assert payload["candidates"][0]["symbol"] == "FPT"


def test_scan_market_rejects_long_candidate_below_ema21(tmp_path: Path, monkeypatch) -> None:
    universe = [UniverseSymbol("AAPL", "US stock", "NASDAQ:AAPL", "AAPL")]

    def fake_universe(name: str):
        return universe

    def fake_loader(symbols: list[str], period: str = "2y", timeframe: str = "D1"):
        candles = []
        start = datetime(2026, 1, 1)
        for index in range(30):
            close = 100.0 if index < 29 else 80.0
            candles.append(
                Candle(
                    datetime=start + timedelta(days=index),
                    open=close,
                    high=close + 1,
                    low=close - 1,
                    close=close,
                    volume=100_000,
                )
            )
        return {symbol: candles for symbol in symbols}

    def fake_detect(candles: list[Candle], technique: str, config, setup: str):
        return VCPEvidence(
            qualified=True,
            status="WAITING",
            score=88,
            pivot=101,
            current_close=candles[-1].close,
            distance_to_pivot_pct=1,
            contractions=[],
            reasons=["Direction: Long", "Synthetic long candidate"],
            failures=[],
        )

    monkeypatch.setattr("filter_pattern.scanner.get_universe", fake_universe)
    monkeypatch.setattr("filter_pattern.scanner.load_yahoo_ohlcv_many", fake_loader)
    monkeypatch.setattr("filter_pattern.scanner.detect_pattern", fake_detect)

    results_path = scan_market(tmp_path / "reports/ema-guard", technique="nhathoai", setup="dd")
    payload = json.loads(results_path.read_text())

    assert payload["qualified_count"] == 0
    assert payload["rejected"][0]["evidence"]["status"] == "rejected"
    assert "EMA21 final-side guard failed" in payload["rejected"][0]["evidence"]["failures"][-1]


def test_scan_market_marks_near_trigger_candidate_with_volume_building(tmp_path: Path, monkeypatch) -> None:
    universe = [UniverseSymbol("AAPL", "US stock", "NASDAQ:AAPL", "AAPL")]

    def fake_universe(name: str):
        return universe

    def fake_loader(symbols: list[str], period: str = "2y", timeframe: str = "D1"):
        candles = []
        start = datetime(2026, 1, 1)
        for index in range(30):
            close = 100.0 if index < 29 else 105.0
            volume = 100_000 if index < 29 else 150_000
            candles.append(
                Candle(
                    datetime=start + timedelta(days=index),
                    open=close,
                    high=close + 1,
                    low=close - 1,
                    close=close,
                    volume=volume,
                )
            )
        return {symbol: candles for symbol in symbols}

    def fake_detect(candles: list[Candle], technique: str, config, setup: str):
        return VCPEvidence(
            qualified=True,
            status="WAITING",
            score=88,
            pivot=106,
            current_close=candles[-1].close,
            distance_to_pivot_pct=1,
            contractions=[],
            reasons=["Direction: Long", "Synthetic triggered candidate"],
            failures=[],
        )

    monkeypatch.setattr("filter_pattern.scanner.get_universe", fake_universe)
    monkeypatch.setattr("filter_pattern.scanner.load_yahoo_ohlcv_many", fake_loader)
    monkeypatch.setattr("filter_pattern.scanner.detect_pattern", fake_detect)

    results_path = scan_market(tmp_path / "reports/volume-signal", technique="nhathoai", setup="bb")
    payload = json.loads(results_path.read_text())

    assert payload["qualified_count"] == 1
    reasons = payload["candidates"][0]["evidence"]["reasons"]
    assert any("Pre-trigger volume building" in reason for reason in reasons)
    assert payload["trigger_warnings"][0]["trigger_warning"]["label"] == "Near break, volume building"


def test_scan_all_market_can_filter_markets_before_download(tmp_path: Path, monkeypatch) -> None:
    universe = [
        UniverseSymbol("AAPL", "US stock", "NASDAQ:AAPL", "AAPL"),
        UniverseSymbol("FPT", "Vietnam stock", "HOSE:FPT", "FPT.VN"),
        UniverseSymbol("BTCUSDT", "Crypto", "BINANCE:BTCUSDT", "BTC-USD"),
    ]
    seen: dict[str, list[str]] = {}

    def fake_universe(name: str):
        return universe

    def fake_loader(symbols: list[str], period: str = "2y", timeframe: str = "D1"):
        seen["symbols"] = symbols
        return {symbol: make_series([20, 12, 6], current_close=96, late_volume=80_000) for symbol in symbols}

    monkeypatch.setattr("filter_pattern.scanner.get_universe", fake_universe)
    monkeypatch.setattr("filter_pattern.scanner.load_yahoo_ohlcv_many", fake_loader)

    results_path = scan_all_market(
        tmp_path / "reports/filtered",
        markets="US stock,Crypto",
        near_match_chart_limit=0,
    )
    payload = json.loads(results_path.read_text())

    assert seen["symbols"] == ["AAPL", "BTC-USD"]
    assert payload["scanned_symbols"] == 2
    assert payload["config"]["markets"] == "US stock,Crypto"


def test_scan_market_records_download_errors(tmp_path: Path, monkeypatch) -> None:
    def fake_loader(symbols: list[str], period: str = "2y", timeframe: str = "D1"):
        return {symbol: ValueError("no data") for symbol in symbols}

    monkeypatch.setattr("filter_pattern.scanner.load_yahoo_ohlcv_many", fake_loader)

    results_path = scan_market(tmp_path / "reports/latest", limit=1)
    payload = json.loads(results_path.read_text())

    assert payload["scanned_symbols"] == 1
    assert payload["qualified_count"] == 0
    assert payload["rejected"][0]["evidence"]["status"] == "data_error"
    assert payload["rejected"][0]["evidence"]["failures"] == ["no data"]


def test_scan_market_writes_near_match_chart_and_scanned_coverage(tmp_path: Path, monkeypatch) -> None:
    def fake_loader(symbols: list[str], period: str = "2y", timeframe: str = "D1"):
        return {
            symbol: make_series([20, 12, 6], current_close=96, late_volume=80_000, prior_start=79, prior_end=80)
            for symbol in symbols
        }

    monkeypatch.setattr("filter_pattern.scanner.load_yahoo_ohlcv_many", fake_loader)

    results_path = scan_market(tmp_path / "reports/latest", limit=1)
    payload = json.loads(results_path.read_text())
    html = (tmp_path / "reports/latest/index.html").read_text()

    assert payload["qualified_count"] == 0
    assert payload["near_matches"][0]["chart_path"]
    assert Path(payload["near_matches"][0]["chart_path"]).exists()
    assert payload["scanned_symbols_by_market"]["US stock"] == ["AAPL"]
    assert "Scanned Universe (1 symbols)" in html
    assert "AAPL" in html
    assert "near-match VCP chart" in html


def test_scan_market_applies_exness_broker_filter(tmp_path: Path, monkeypatch) -> None:
    seen_symbols: list[str] = []

    def fake_loader(symbols: list[str], period: str = "2y", timeframe: str = "D1"):
        seen_symbols.extend(symbols)
        return {symbol: ValueError("no data") for symbol in symbols}

    monkeypatch.setattr("filter_pattern.scanner.load_yahoo_ohlcv_many", fake_loader)

    results_path = scan_market(tmp_path / "reports/latest", limit=8, broker_filter="exness")
    payload = json.loads(results_path.read_text())

    assert "SPY" not in seen_symbols
    assert payload["config"]["broker_filter"] == "exness"


def test_scan_market_preserves_nhathoai_setup_and_reports_rule_evidence(tmp_path: Path, monkeypatch) -> None:
    def fake_loader(symbols: list[str], period: str = "2y", timeframe: str = "D1"):
        return {symbol: make_series([20, 12, 6], current_close=96, late_volume=80_000) for symbol in symbols}

    monkeypatch.setattr("filter_pattern.scanner.load_yahoo_ohlcv_many", fake_loader)

    results_path = scan_market(tmp_path / "reports/latest", limit=1, technique="nhathoai", setup="rb")
    payload = json.loads(results_path.read_text())
    html = (tmp_path / "reports/latest/index.html").read_text()

    assert payload["config"]["technique"] == "nhathoai"
    assert payload["config"]["setup"] == "rb"
    assert payload["qualified_count"] == 0
    assert payload["rejected"][0]["technique"] == "nhathoai"
    assert payload["rejected"][0]["setup"] == "rb"
    assert payload["rejected"][0]["evidence"]["status"] == "rejected"
    assert payload["rejected"][0]["evidence"]["reasons"] or payload["rejected"][0]["evidence"]["failures"]
    assert "Technique: nhathoai" in html
    assert "Setup: rb" in html
    assert 'id="setupFilter"' in html


def test_scan_market_uses_technique_and_setup_from_symbolless_config(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "market.yml"
    config_path.write_text(
        "timeframe: D1\n"
        "technique: nhathoai\n"
        "setup: rb\n"
        "vcp:\n"
        "  near_pivot_pct: 4\n"
    )

    def fake_loader(symbols: list[str], period: str = "2y", timeframe: str = "D1"):
        return {symbol: make_series([20, 12, 6], current_close=96, late_volume=80_000) for symbol in symbols}

    monkeypatch.setattr("filter_pattern.scanner.load_yahoo_ohlcv_many", fake_loader)

    results_path = scan_market(tmp_path / "reports/latest", config_path=config_path, limit=1)
    payload = json.loads(results_path.read_text())

    assert payload["config"]["technique"] == "nhathoai"
    assert payload["config"]["setup"] == "rb"
    assert payload["config"]["vcp"]["near_pivot_pct"] == 4
    assert payload["rejected"][0]["evidence"]["status"] == "rejected"


def test_scan_market_cli_arguments_override_config_technique_and_setup(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "market.yml"
    config_path.write_text(
        "timeframe: D1\n"
        "technique: nhathoai\n"
        "setup: rb\n"
    )

    def fake_loader(symbols: list[str], period: str = "2y", timeframe: str = "D1"):
        return {symbol: make_series([20, 12, 6], current_close=96, late_volume=80_000) for symbol in symbols}

    monkeypatch.setattr("filter_pattern.scanner.load_yahoo_ohlcv_many", fake_loader)

    results_path = scan_market(
        tmp_path / "reports/latest",
        config_path=config_path,
        limit=1,
        technique="minervini-vcp",
        setup="all",
    )
    payload = json.loads(results_path.read_text())

    assert payload["config"]["technique"] == "minervini-vcp"
    assert payload["config"]["setup"] == "all"
    assert payload["qualified_count"] == 1


def test_scan_market_expands_all_nhathoai_setups_into_one_filterable_report(tmp_path: Path, monkeypatch) -> None:
    def fake_loader(symbols: list[str], period: str = "2y", timeframe: str = "D1"):
        return {symbol: make_series([20, 12, 6], current_close=96, late_volume=80_000) for symbol in symbols}

    monkeypatch.setattr("filter_pattern.scanner.load_yahoo_ohlcv_many", fake_loader)

    results_path = scan_market(tmp_path / "reports/latest", limit=1, technique="nhathoai", setup="all")
    payload = json.loads(results_path.read_text())
    html = (tmp_path / "reports/latest/index.html").read_text()

    assert payload["config"]["technique"] == "nhathoai"
    assert payload["config"]["setup"] == "all"
    assert payload["scanned_symbols"] == 1
    assert payload["evaluation_count"] == 9
    evaluated = payload["rejected"] + payload["candidates"]
    assert {item["setup"] for item in evaluated} == {
        "dd",
        "fb",
        "sb",
        "bb",
        "rb",
        "irb",
        "arb",
        "vcp",
        "compression",
    }
    assert payload["scanned_symbols_by_market"]["US stock"] == ["AAPL"]
    assert 'id="setupFilter"' in html
    assert '<option value="rb">RB</option>' in html
    assert 'data-setup="rb"' in html


def test_scan_market_does_not_label_flat_market_as_nhathoai_candidate(tmp_path: Path, monkeypatch) -> None:
    def fake_loader(symbols: list[str], period: str = "2y", timeframe: str = "D1"):
        return {symbol: make_flat_series() for symbol in symbols}

    monkeypatch.setattr("filter_pattern.scanner.load_yahoo_ohlcv_many", fake_loader)

    results_path = scan_market(tmp_path / "reports/latest", limit=1, technique="nhathoai", setup="all")
    payload = json.loads(results_path.read_text())

    assert payload["qualified_count"] == 0
    assert payload["evaluation_count"] == 9
    assert all(item["evidence"]["status"] == "rejected" for item in payload["rejected"])


def test_scan_all_market_includes_original_vcp_and_all_nhathoai_setups(tmp_path: Path, monkeypatch) -> None:
    def fake_loader(symbols: list[str], period: str = "2y", timeframe: str = "D1"):
        return {symbol: make_series([20, 12, 6], current_close=96, late_volume=80_000) for symbol in symbols}

    monkeypatch.setattr("filter_pattern.scanner.load_yahoo_ohlcv_many", fake_loader)

    results_path = scan_all_market(tmp_path / "reports/all", limit=1)
    payload = json.loads(results_path.read_text())
    evaluated = payload["rejected"] + payload["candidates"]

    assert payload["config"]["technique"] == "all-patterns"
    assert payload["config"]["setup"] == "all"
    assert payload["evaluation_count"] == 13
    assert {item["setup"] for item in evaluated if item["technique"] == "minervini-vcp"} == {
        "original-vcp",
        "vcp-1c",
        "vcp-2c",
        "vcp-3c",
    }
    assert {item["setup"] for item in evaluated if item["technique"] == "nhathoai"} == {
        "dd",
        "fb",
        "sb",
        "bb",
        "rb",
        "irb",
        "arb",
        "vcp",
        "compression",
    }
    assert (tmp_path / "reports/all/index.html").exists()
