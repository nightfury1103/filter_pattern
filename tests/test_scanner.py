from __future__ import annotations

import json
from pathlib import Path

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
        UniverseSymbol("BTCUSDT", "Crypto", "BINANCE:BTCUSDT", "BTC-USD"),
    ]
    seen: dict[str, list[str]] = {}

    def fake_universe(name: str):
        return universe

    def fake_yahoo(symbols: list[str], period: str = "2y", timeframe: str = "D1"):
        seen["yahoo"] = symbols
        return {symbol: make_series([20, 12, 6], current_close=96, late_volume=80_000) for symbol in symbols}

    def fake_ccxt(symbols: list[str], period: str = "2y", timeframe: str = "D1"):
        seen["ccxt"] = symbols
        return {symbol: make_series([20, 12, 6], current_close=96, late_volume=80_000) for symbol in symbols}

    monkeypatch.setattr("filter_pattern.scanner.get_universe", fake_universe)
    monkeypatch.setattr("filter_pattern.scanner.load_yahoo_ohlcv_many", fake_yahoo)
    monkeypatch.setattr("filter_pattern.scanner.load_ccxt_ohlcv_many", fake_ccxt)

    results_path = scan_market(tmp_path / "reports/mixed", data_provider="mixed")
    payload = json.loads(results_path.read_text())

    assert seen["yahoo"] == ["AAPL"]
    assert seen["ccxt"] == ["BTCUSDT"]
    assert payload["config"]["data_provider"] == "mixed"
    assert payload["config"]["data_source"] == "Yahoo Finance + CCXT"
    assert payload["scanned_symbols"] == 2


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
