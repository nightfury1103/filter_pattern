from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

from filter_pattern.chart import _minimum_body_height, _price_label, _date_formatter, _session_positions, render_chart
from filter_pattern.detector import detect_vcp
from filter_pattern.models import Candle, ScanResult, SymbolSpec
from filter_pattern.report import (
    apply_watchlist_changes,
    result_payload,
    write_combined_html_report,
    write_combined_results_json,
    write_html_report,
)
from tests.test_detector import make_config, make_series


def test_chart_and_report_smoke(tmp_path: Path) -> None:
    cfg = make_config()
    candles = make_series([20, 12, 6], current_close=96, late_volume=80_000)
    evidence = detect_vcp(candles, cfg)
    symbol = SymbolSpec(
        symbol="AAPL",
        market="US stock",
        tradingview_symbol="NASDAQ:AAPL",
        csv_path=tmp_path / "aapl.csv",
    )
    result = ScanResult(symbol=symbol, timeframe="D1", evidence=evidence)

    chart_path = render_chart(result, candles, tmp_path / "charts", cfg)
    result = ScanResult(symbol=symbol, timeframe="D1", evidence=evidence, chart_path=str(chart_path))
    row = result.to_json()
    row["direction_authority"] = {
        "bias": "WATCH LONG",
        "phase": "Accumulation / Recovery",
        "trend_score": -12.5,
        "momentum_score": 45.0,
        "confidence": 62.0,
        "setup_direction": "short",
        "decision": "BLOCK_SHORT_ACCUMULATION_RISK",
        "decision_label": "Block short: accumulation/recovery risk",
        "trade_filter": "Block shorts: improving from weak state",
        "reasons": ["20-bar return: +8.0%"],
    }
    payload = result_payload([row], [], {"timeframe": "D1"})
    results_path = tmp_path / "results.json"
    results_path.write_text(json.dumps(payload))

    report_path = write_html_report(results_path, tmp_path / "index.html")

    assert chart_path.exists()
    assert chart_path.suffix == ".jpg"
    assert chart_path.stat().st_size > 0
    preview_path = chart_path.parent / "preview" / chart_path.name
    assert preview_path.exists()
    assert preview_path.stat().st_size < chart_path.stat().st_size
    assert report_path.exists()
    html = report_path.read_text()
    assert "AAPL" in html
    assert 'href="charts/AAPL_minervini-vcp_all.jpg"' in html
    assert 'data-src="charts/preview/AAPL_minervini-vcp_all.jpg"' in html
    assert "Scanned Universe (1 symbols)" in html
    assert 'id="marketFilter"' in html
    assert 'id="techniqueFilter"' in html
    assert 'id="setupFilter"' in html
    assert 'id="filterCount"' in html
    assert 'id="coverageSection"' in html
    assert "applyFilters();" in html
    assert 'data-filterable="true"' in html
    assert "Block short: accumulation/recovery risk" in html
    assert "Accumulation / Recovery" in html


def test_report_renders_rrg_confidence_reference_beside_candidate_chart(tmp_path: Path) -> None:
    cfg = make_config()
    candles = make_series([20, 12, 6], current_close=96, late_volume=80_000)
    evidence = detect_vcp(candles, cfg)
    symbol = SymbolSpec(
        symbol="MSFT",
        market="US stock",
        tradingview_symbol="NASDAQ:MSFT",
        csv_path=tmp_path / "msft.csv",
    )
    chart_path = render_chart(ScanResult(symbol=symbol, timeframe="D1", evidence=evidence), candles, tmp_path / "charts", cfg)
    rrg_path = tmp_path / "rrg" / "msft-rrg-proof.jpg"
    rrg_path.parent.mkdir()
    rrg_path.write_bytes(b"fake jpg")
    row = ScanResult(symbol=symbol, timeframe="D1", evidence=evidence, chart_path=str(chart_path)).to_json()
    row["rrg"] = {
        "benchmark": "XLK",
        "sector": "Information Technology",
        "rrg_chart_path": str(rrg_path),
        "stock_intent": {"quadrant": "LAGGING", "dx1": 0.5, "dy1": 0.4, "dy2": 0.2},
        "confidence": {"label": "RRG Early Reference", "tone": "early", "blocks_pattern": False},
    }
    payload = result_payload([row], [], {"timeframe": "D1"})
    results_path = tmp_path / "results.json"
    results_path.write_text(json.dumps(payload))

    report_path = write_html_report(results_path, tmp_path / "index.html")
    html = report_path.read_text()

    assert "RRG Confidence" in html
    assert "RRG Early Reference" in html
    assert "Information Technology vs XLK" in html
    assert "msft-rrg-proof.jpg" in html


def test_report_renders_market_rrg_overview(tmp_path: Path) -> None:
    first = _candidate("BTCUSDT", "bb", 86, "WAITING")
    first.update({"market": "Crypto", "timeframe": "D1"})
    first["rrg"] = {
        "benchmark": "$ONE",
        "sector": "Crypto",
        "latest": {"x": 103.2, "y": 104.1},
        "rrg_series": [
            {"x": 101.6, "y": 102.5, "end": "2026-06-01"},
            {"x": 102.4, "y": 103.1, "end": "2026-06-02"},
            {"x": 103.2, "y": 104.1, "end": "2026-06-03"},
        ],
        "stock_intent": {"quadrant": "LEADING", "dx1": 0.7, "dy1": 0.9},
        "confidence": {"label": "RRG Supportive Reference"},
    }
    second = _candidate("XAUUSD", "compression", 78, "WAITING")
    second.update({"market": "Commodity", "timeframe": "D1"})
    second["rrg"] = {
        "benchmark": "$ONE",
        "sector": "Commodity",
        "latest": {"x": 96.3, "y": 97.4},
        "rrg_series": [
            {"x": 97.1, "y": 98.2, "end": "2026-06-01"},
            {"x": 96.8, "y": 97.8, "end": "2026-06-02"},
            {"x": 96.3, "y": 97.4, "end": "2026-06-03"},
        ],
        "stock_intent": {"quadrant": "LAGGING", "dx1": -0.2, "dy1": -0.4},
        "confidence": {"label": "RRG Warning Reference"},
    }
    payload = result_payload([first, second], [], {"timeframe": "D1"})
    results_path = tmp_path / "results.json"
    results_path.write_text(json.dumps(payload))

    report_path = write_html_report(results_path, tmp_path / "index.html")
    html = report_path.read_text()

    assert "Market RRG Overview" in html
    assert "Daily RRG Chart" in html
    assert "Latest RRG row: 2026-06-03" in html
    assert 'class="rrg-svg"' in html
    assert "Leading" in html
    assert "Lagging" in html
    assert "BTCUSDT" in html
    assert "XAUUSD" in html
    assert "Support / risk" in html
    assert "Crypto" in html
    assert "Commodity" in html


def test_report_rrg_overview_uses_representatives_and_switches_market_charts(tmp_path: Path) -> None:
    crypto = _candidate("BTCUSDT", "bb", 86, "WAITING")
    crypto.update({"market": "Crypto", "timeframe": "D1"})
    crypto["rrg"] = {
        "benchmark": "$ONE",
        "sector": "Crypto",
        "latest": {"x": 103.2, "y": 104.1},
        "rrg_series": [
            {"x": 101.6, "y": 102.5, "end": "2026-06-01"},
            {"x": 102.4, "y": 103.1, "end": "2026-06-02"},
            {"x": 103.2, "y": 104.1, "end": "2026-06-03"},
        ],
        "stock_intent": {"quadrant": "LEADING", "dx1": 0.8, "dy1": 1.0},
        "confidence": {"label": "RRG Supportive Reference"},
    }
    crypto_alt = _candidate("SOLUSDT", "vcp", 79, "WAITING")
    crypto_alt.update({"market": "Crypto", "timeframe": "D1"})
    crypto_alt["rrg"] = {
        "benchmark": "$ONE",
        "sector": "Crypto",
        "latest": {"x": 99.2, "y": 101.4},
        "rrg_series": [
            {"x": 98.7, "y": 100.7, "end": "2026-06-01"},
            {"x": 98.9, "y": 101.0, "end": "2026-06-02"},
            {"x": 99.2, "y": 101.4, "end": "2026-06-03"},
        ],
        "stock_intent": {"quadrant": "IMPROVING", "dx1": 0.3, "dy1": 0.4},
        "confidence": {"label": "RRG Early Reference"},
    }
    commodity = _candidate("XAUUSD", "compression", 78, "WAITING")
    commodity.update({"market": "Commodity", "timeframe": "D1"})
    commodity["rrg"] = {
        "benchmark": "$ONE",
        "sector": "Commodity",
        "latest": {"x": 96.3, "y": 97.4},
        "rrg_series": [
            {"x": 97.1, "y": 98.2, "end": "2026-06-01"},
            {"x": 96.8, "y": 97.8, "end": "2026-06-02"},
            {"x": 96.3, "y": 97.4, "end": "2026-06-03"},
        ],
        "stock_intent": {"quadrant": "LAGGING", "dx1": -0.5, "dy1": -0.4},
        "confidence": {"label": "RRG Warning Reference"},
    }
    payload = result_payload([crypto, crypto_alt, commodity], [], {"timeframe": "D1"})
    payload["rrg_reference"] = {
        "market_representatives": [
            {
                "symbol": "SPY",
                "market": "US stock",
                "timeframe": "D1",
                "rrg": {
                    "benchmark": "SPY",
                    "sector": "US stock",
                    "latest": {"x": 101.4, "y": 101.2},
                    "rrg_series": [
                        {"x": 99.0, "y": 98.6, "end": "2026-06-01"},
                        {"x": 100.2, "y": 100.1, "end": "2026-06-02"},
                        {"x": 101.4, "y": 101.2, "end": "2026-06-03"},
                    ],
                    "stock_intent": {"quadrant": "LEADING", "dx1": 1.2, "dy1": 1.1},
                },
            },
            {
                "symbol": "BTCUSDT",
                "market": "Crypto",
                "timeframe": "D1",
                "rrg": {
                    "benchmark": "$ONE",
                    "sector": "Crypto",
                    "latest": {"x": 101.3, "y": 99.8},
                    "rrg_series": [
                        {"x": 101.7, "y": 102.1, "end": "2026-06-01"},
                        {"x": 102.0, "y": 100.2, "end": "2026-06-02"},
                        {"x": 101.3, "y": 99.8, "end": "2026-06-03"},
                    ],
                    "stock_intent": {"quadrant": "WEAKENING", "dx1": -0.7, "dy1": -0.4},
                },
            },
            {
                "symbol": "ETHUSDT",
                "market": "Crypto",
                "timeframe": "D1",
                "rrg": {
                    "benchmark": "$ONE",
                    "sector": "Crypto",
                    "latest": {"x": 100.8, "y": 100.5},
                    "rrg_series": [
                        {"x": 99.4, "y": 99.7, "end": "2026-06-01"},
                        {"x": 100.0, "y": 100.1, "end": "2026-06-02"},
                        {"x": 100.8, "y": 100.5, "end": "2026-06-03"},
                    ],
                    "stock_intent": {"quadrant": "LEADING", "dx1": 0.8, "dy1": 0.4},
                },
            },
        ]
    }
    results_path = tmp_path / "results.json"
    results_path.write_text(json.dumps(payload))

    report_path = write_html_report(results_path, tmp_path / "index.html")
    html = report_path.read_text()

    all_chart_start = html.index('data-rrg-market="all"')
    crypto_chart_start = html.index('data-rrg-market="Crypto"')
    all_chart_html = html[all_chart_start:crypto_chart_start]
    assert "SPY" in all_chart_html
    assert "BTCUSDT" in all_chart_html
    assert "ETHUSDT" in all_chart_html
    assert 'data-rrg-market="Crypto"' in html
    crypto_chart_start = html.index('data-rrg-market="Crypto"')
    crypto_chart_end = html.index("</svg>", crypto_chart_start)
    crypto_chart_html = html[crypto_chart_start:crypto_chart_end]
    assert "BTCUSDT" in crypto_chart_html
    assert "ETHUSDT" in crypto_chart_html
    assert "SOLUSDT" not in crypto_chart_html
    assert 'id="rrgChartMode"' in html
    assert "function updateRrgOverview" in html
    assert "updateRrgOverview(market);" in html
    assert "marker-end=" in html
    assert html.index('<circle class="rrg-dot"') < html.index('class="rrg-tail rrg-arrow-segment"')


def test_report_uses_full_width_chart_layout_without_right_side_panel(tmp_path: Path) -> None:
    cfg = make_config()
    candles = make_series([20, 12, 6], current_close=96, late_volume=80_000)
    evidence = detect_vcp(candles, cfg)
    symbol = SymbolSpec(
        symbol="MSFT",
        market="US stock",
        tradingview_symbol="NASDAQ:MSFT",
        csv_path=tmp_path / "msft.csv",
    )
    chart_path = render_chart(ScanResult(symbol=symbol, timeframe="D1", evidence=evidence), candles, tmp_path / "charts", cfg)
    row = ScanResult(symbol=symbol, timeframe="D1", evidence=evidence, chart_path=str(chart_path)).to_json()
    payload = result_payload([row], [], {"timeframe": "D1"})
    results_path = tmp_path / "results.json"
    results_path.write_text(json.dumps(payload))

    report_path = write_html_report(results_path, tmp_path / "index.html")
    html = report_path.read_text()

    assert 'class="side-panel"' not in html
    assert "Setup Distribution" not in html
    assert ".layout { display: block;" in html
    assert ".card-content {\n      display: block;" in html


def test_chart_x_axis_uses_trading_sessions_without_weekend_gap() -> None:
    candles = [
        Candle(datetime=datetime(2026, 5, 1), open=10, high=11, low=9, close=10.5, volume=100),
        Candle(datetime=datetime(2026, 5, 4), open=10.5, high=12, low=10, close=11.5, volume=120),
        Candle(datetime=datetime(2026, 5, 5), open=11.5, high=12, low=11, close=11.8, volume=110),
    ]

    positions = _session_positions(candles)
    formatter = _date_formatter("D1", candles)

    assert positions == [0.0, 1.0, 2.0]
    assert formatter(0, 0) == "2026-05-01"
    assert formatter(1, 1) == "2026-05-04"
    assert formatter(2, 2) == "2026-05-05"


def test_tiny_price_chart_uses_adaptive_candle_body_and_labels(tmp_path: Path) -> None:
    candles = [
        Candle(
            datetime=datetime(2026, 5, 1) + timedelta(days=day - 1),
            open=0.00001000 + day * 0.00000002,
            high=0.00001060 + day * 0.00000002,
            low=0.00000970 + day * 0.00000002,
            close=0.00001015 + day * 0.00000002,
            volume=1_000_000 + day * 10_000,
        )
        for day in range(1, 35)
    ]
    cfg = make_config()
    evidence = replace(
        detect_vcp(make_series([20, 12, 6], current_close=96, late_volume=80_000), cfg),
        pivot=0.000011,
        current_close=candles[-1].close,
        contractions=[],
    )
    symbol = SymbolSpec(
        symbol="SHIBUSDT",
        market="Crypto",
        tradingview_symbol="BINANCE:SHIBUSDT",
        csv_path=tmp_path / "shib.csv",
    )
    result = ScanResult(symbol=symbol, timeframe="D1", evidence=evidence)

    body_floor = _minimum_body_height(candles)
    chart_path = render_chart(result, candles, tmp_path / "charts", cfg)

    assert body_floor < candles[-1].close * 0.01
    assert _price_label(candles[-1].close) != "0.00"
    assert chart_path.exists()
    assert chart_path.stat().st_size > 0


def test_combined_report_merges_multiple_results_and_adds_filters(tmp_path: Path) -> None:
    cfg = make_config()
    candles = make_series([20, 12, 6], current_close=96, late_volume=80_000)
    evidence = detect_vcp(candles, cfg)
    symbol = SymbolSpec(
        symbol="AAPL",
        market="US stock",
        tradingview_symbol="NASDAQ:AAPL",
        csv_path=tmp_path / "aapl.csv",
    )
    vcp_result = ScanResult(symbol=symbol, timeframe="D1", evidence=evidence, technique="minervini-vcp", setup="all")
    ema_result = ScanResult(
        symbol=symbol,
        timeframe="D1",
        evidence=evidence,
        technique="experimental-ema21-compression",
        setup="all",
    )
    first_payload = result_payload([vcp_result.to_json()], [], {"timeframe": "D1", "technique": "minervini-vcp"})
    second_payload = result_payload(
        [ema_result.to_json()],
        [],
        {"timeframe": "D1", "technique": "experimental-ema21-compression"},
    )
    first_path = tmp_path / "vcp.json"
    second_path = tmp_path / "ema.json"
    first_path.write_text(json.dumps(first_payload))
    second_path.write_text(json.dumps(second_payload))

    report_path = write_combined_html_report([first_path, second_path], tmp_path / "combined.html")
    html = report_path.read_text()

    assert "AAPL" in html
    assert "experimental-ema21-compression" in html
    assert "minervini-vcp" in html
    assert 'id="techniqueFilter"' in html
    assert 'id="setupFilter"' in html
    assert html.count('data-status="qualified"') == 2


def test_report_adds_symbol_dedup_filter_mode(tmp_path: Path) -> None:
    first = _candidate("AAPL", "bb", 81, "WAITING")
    second = _candidate("AAPL", "sb", 88, "WAITING")
    third = _candidate("MSFT", "bb", 82, "WAITING")
    for row in (first, second, third):
        row["evidence"]["distance_to_pivot_pct"] = 15
    payload = result_payload([first, second, third], [], {"timeframe": "D1", "technique": "nhathoai"})
    results_path = tmp_path / "results.json"
    results_path.write_text(json.dumps(payload))

    report_path = write_html_report(results_path, tmp_path / "index.html")
    html = report_path.read_text()

    assert 'id="dedupFilter"' in html
    assert '<option value="off">All pattern matches</option>' in html
    assert '<option value="symbol">One chart per symbol</option>' in html
    assert html.count('data-symbol="AAPL"') == 2
    assert html.count('data-symbol="MSFT"') == 1
    assert "function dedupRank(node)" in html
    assert "const selectedDedupCards = new Set();" in html
    assert "dedupFilter.addEventListener('change', applyFilters);" in html


def test_combined_results_preserve_review_rrg_references(tmp_path: Path) -> None:
    review_row = _candidate("ATOMUSDT", "irb", 60, "rejected")
    review_row.update(
        {
            "market": "Crypto",
            "tradingview_symbol": "BINANCE:ATOMUSDT.P",
            "csv_path": "ccxt:ATOMUSDT",
            "chart_path": str(tmp_path / "crypto" / "charts" / "atomusdt.jpg"),
        }
    )
    review_row["evidence"].update(
        {
            "qualified": False,
            "pivot": 2.19,
            "current_close": 2.105,
            "distance_to_pivot_pct": 3.88,
            "reasons": ["Pattern: IRB", "Direction: Long"],
            "failures": ["Inner block break is not triggered or close enough"],
        }
    )
    payload = result_payload([], [review_row], {"timeframe": "D1", "technique": "nhathoai"})
    payload["review_setups"][0]["rrg"] = {
        "benchmark": "$ONE",
        "sector": "Crypto",
        "rrg_chart_path": str(tmp_path / "crypto" / "rrg-reference" / "atomusdt-rrg-proof.jpg"),
        "stock_intent": {"quadrant": "IMPROVING", "dx1": 0.4, "dy1": 0.6},
        "confidence": {"label": "RRG Early Reference", "tone": "early", "blocks_pattern": False},
    }
    first_path = tmp_path / "crypto" / "results.json"
    first_path.parent.mkdir(parents=True)
    first_path.write_text(json.dumps(payload))

    combined_results = write_combined_results_json([first_path], tmp_path / "combined" / "results.json")
    combined_payload = json.loads(combined_results.read_text())

    assert combined_payload["review_setups"][0]["rrg"]["rrg_chart_path"].endswith("atomusdt-rrg-proof.jpg")


def test_combined_results_can_materialize_shard_assets(tmp_path: Path) -> None:
    shard_dir = tmp_path / "public" / "d1-shards" / "d1-shard-crypto"
    chart_path = shard_dir / "charts" / "atomusdt.jpg"
    preview_path = shard_dir / "charts" / "preview" / "atomusdt.jpg"
    rrg_path = shard_dir / "rrg-reference" / "atomusdt-rrg-proof.jpg"
    chart_path.parent.mkdir(parents=True)
    preview_path.parent.mkdir(parents=True)
    rrg_path.parent.mkdir(parents=True)
    chart_path.write_bytes(b"full chart")
    preview_path.write_bytes(b"preview chart")
    rrg_path.write_bytes(b"rrg chart")

    row = _candidate("ATOMUSDT", "irb", 60, "WAITING")
    row.update({"market": "Crypto", "chart_path": str(chart_path)})
    row["rrg"] = {
        "benchmark": "$ONE",
        "sector": "Crypto",
        "rrg_chart_path": str(rrg_path),
        "stock_intent": {"quadrant": "IMPROVING", "dx1": 0.4, "dy1": 0.6},
        "confidence": {"label": "RRG Early Reference", "tone": "early", "blocks_pattern": False},
    }
    source_results = shard_dir / "results.json"
    source_results.write_text(json.dumps(result_payload([row], [], {"timeframe": "D1"})))

    combined_results = write_combined_results_json(
        [source_results],
        tmp_path / "public" / "d1" / "results.json",
        copy_assets=True,
        asset_root=tmp_path / "public" / "d1",
    )
    combined_payload = json.loads(combined_results.read_text())
    copied_chart = tmp_path / "public" / "d1" / "assets" / "d1-shard-crypto" / "charts" / "atomusdt.jpg"
    copied_preview = copied_chart.parent / "preview" / "atomusdt.jpg"
    copied_rrg = tmp_path / "public" / "d1" / "assets" / "d1-shard-crypto" / "rrg-reference" / "atomusdt-rrg-proof.jpg"

    assert copied_chart.exists()
    assert copied_preview.exists()
    assert copied_rrg.exists()
    assert combined_payload["candidates"][0]["chart_path"] == str(copied_chart)
    assert combined_payload["candidates"][0]["rrg"]["rrg_chart_path"] == str(copied_rrg)


def test_combined_report_links_h4_volume_confirmation_to_d1_near_trigger(tmp_path: Path) -> None:
    d1_candidate = _candidate("AAPL", "bb", 84, "WAITING")
    h4_candidate = _candidate("AAPL", "compression", 88, "TRIGGERED")
    h4_candidate["timeframe"] = "H4"
    h4_candidate["chart_path"] = str(tmp_path / "h4-aapl.png")
    h4_candidate["evidence"]["current_close"] = 101
    h4_candidate["evidence"]["reasons"].append(
        "Trigger volume confirmed: latest closed candle volume 150,000 is 1.50x the previous 5-candle average"
    )

    d1_payload = result_payload([d1_candidate], [], {"timeframe": "D1", "technique": "nhathoai", "setup": "all"})
    h4_payload = result_payload([h4_candidate], [], {"timeframe": "H4", "technique": "nhathoai", "setup": "all"})
    d1_path = tmp_path / "d1.json"
    h4_path = tmp_path / "h4.json"
    d1_path.write_text(json.dumps(d1_payload))
    h4_path.write_text(json.dumps(h4_payload))

    report_path = write_combined_html_report([d1_path, h4_path], tmp_path / "combined.html")
    html = report_path.read_text()

    assert "Review lower timeframe" in html
    assert "Near break + H4 volume" in html
    assert "H4 nhathoai / compression is triggered and latest closed candle has confirmed volume" in html
    assert "Use this lower-timeframe chart for manual review only" in html


def test_combined_report_does_not_link_h4_review_far_from_d1_trigger(tmp_path: Path) -> None:
    d1_candidate = _candidate("AAPL", "bb", 84, "WAITING")
    h4_candidate = _candidate("AAPL", "compression", 88, "TRIGGERED")
    h4_candidate["timeframe"] = "H4"
    h4_candidate["chart_path"] = str(tmp_path / "h4-aapl.png")
    h4_candidate["evidence"]["pivot"] = 150
    h4_candidate["evidence"]["current_close"] = 151
    h4_candidate["evidence"]["reasons"].append(
        "Trigger volume confirmed: latest closed candle volume 150,000 is 1.50x the previous 5-candle average"
    )

    d1_payload = result_payload([d1_candidate], [], {"timeframe": "D1", "technique": "nhathoai", "setup": "all"})
    h4_payload = result_payload([h4_candidate], [], {"timeframe": "H4", "technique": "nhathoai", "setup": "all"})
    d1_path = tmp_path / "d1.json"
    h4_path = tmp_path / "h4.json"
    d1_path.write_text(json.dumps(d1_payload))
    h4_path.write_text(json.dumps(h4_payload))

    report_path = write_combined_html_report([d1_path, h4_path], tmp_path / "combined.html")
    html = report_path.read_text()

    assert "Near break + H4 volume" not in html
    assert "Use this lower-timeframe chart for manual review only" not in html


def test_report_renders_not_configured_setup_rows_for_filtering(tmp_path: Path) -> None:
    symbol = SymbolSpec(
        symbol="AAPL",
        market="US stock",
        tradingview_symbol="NASDAQ:AAPL",
        csv_path=tmp_path / "aapl.csv",
    )
    evidence = detect_vcp(make_series([20, 12, 6], current_close=96, late_volume=80_000), make_config())
    not_configured_result = ScanResult(
        symbol=symbol,
        timeframe="D1",
        evidence=type(evidence)(
            qualified=False,
            status="not_configured",
            score=0.0,
            pivot=None,
            current_close=None,
            distance_to_pivot_pct=None,
            contractions=[],
            reasons=[],
            failures=["Nhật Hoài RB is not configured yet."],
        ),
        technique="nhathoai",
        setup="rb",
    )
    payload = result_payload([], [not_configured_result.to_json()], {"timeframe": "D1", "technique": "nhathoai"})
    results_path = tmp_path / "results.json"
    results_path.write_text(json.dumps(payload))

    report_path = write_html_report(results_path, tmp_path / "index.html")
    html = report_path.read_text()

    assert '<option value="not_configured">Not configured</option>' in html
    assert 'data-status="not_configured"' in html
    assert 'data-setup="rb"' in html


def test_report_renders_near_break_warning_filter(tmp_path: Path) -> None:
    waiting_candidate = _candidate("AAPL", "dd", 84, "WAITING")
    triggered_candidate = _candidate("MSFT", "bb", 88, "TRIGGERED")
    payload = result_payload(
        [waiting_candidate, triggered_candidate],
        [],
        {"timeframe": "D1", "technique": "nhathoai", "setup": "all"},
    )
    results_path = tmp_path / "results.json"
    results_path.write_text(json.dumps(payload))

    report_path = write_html_report(results_path, tmp_path / "index.html")
    html = report_path.read_text()

    assert len(payload["trigger_warnings"]) == 2
    assert "Near Break / Trigger Warnings" in html
    assert '<option value="warning">Near break warning</option>' in html
    assert 'data-status="warning"' in html
    assert "Near break" in html
    assert "Triggered" in html


def test_payload_keeps_structured_rejected_setups_for_lifecycle_review() -> None:
    filler_rows = []
    for index in range(25):
        filler = _candidate(f"FILL{index}", "bb", 79, "rejected")
        filler["evidence"]["qualified"] = False
        filler["evidence"]["reasons"] = [f"passed check {step}" for step in range(12)]
        filler["evidence"]["failures"] = ["strict failed"]
        filler_rows.append(filler)

    review_row = _candidate("ATOMUSDT", "irb", 60, "rejected")
    review_row.update(
        {
            "market": "Crypto",
            "tradingview_symbol": "BINANCE:ATOMUSDT.P",
            "csv_path": "ccxt:ATOMUSDT",
        }
    )
    review_row["evidence"].update(
        {
            "qualified": False,
            "pivot": 2.19,
            "current_close": 2.105,
            "distance_to_pivot_pct": 3.88,
            "reasons": [
                "Pattern: IRB",
                "Range description: 2026-04-21 -> 2026-05-19",
                "Upper range boundary: 2.235",
                "Lower range boundary: 1.763",
                "Inner buildup/block description: 2026-05-20 -> 2026-05-23; area 1.979 - 2.19",
                "Trigger level: 2.19",
                "Stop-loss area: 1.979",
            ],
            "failures": [
                "Status: REJECT",
                "Inner block break is not triggered or close enough",
                "Risk/reward to boundary is poor",
            ],
        }
    )

    payload = result_payload([], filler_rows + [review_row], {"timeframe": "D1", "technique": "nhathoai"})

    assert all(item["symbol"] != "ATOMUSDT" for item in payload["near_matches"])
    assert any(item["symbol"] == "ATOMUSDT" and item["setup"] == "irb" for item in payload["review_setups"])


def test_payload_prioritizes_near_trigger_lifecycle_review_rows() -> None:
    filler_rows = []
    for index in range(260):
        filler = _candidate(f"FILL{index}", "compression", 95, "rejected")
        filler["evidence"].update(
            {
                "qualified": False,
                "pivot": 100,
                "current_close": 80,
                "distance_to_pivot_pct": 20,
                "reasons": ["Compression zone: 92 - 100", "Direction: Long"],
                "failures": ["Strict setup failed"],
            }
        )
        filler_rows.append(filler)

    review_row = _candidate("ATOMUSDT", "irb", 68, "rejected")
    review_row.update(
        {
            "market": "Crypto",
            "tradingview_symbol": "OKX:ATOMUSDT.P",
            "csv_path": "ccxt:ATOMUSDT",
        }
    )
    review_row["evidence"].update(
        {
            "qualified": False,
            "pivot": 2.189,
            "current_close": 2.126,
            "distance_to_pivot_pct": 2.878,
            "reasons": ["Pattern: IRB", "Direction: Long"],
            "failures": ["Status: REJECT", "Strict setup failed"],
        }
    )

    payload = result_payload([], filler_rows + [review_row], {"timeframe": "D1", "technique": "nhathoai"})

    assert any(item["symbol"] == "ATOMUSDT" and item["setup"] == "irb" for item in payload["review_setups"])


def test_report_renders_lifecycle_review_setups(tmp_path: Path) -> None:
    review_row = _candidate("ATOMUSDT", "irb", 60, "rejected")
    review_row.update(
        {
            "market": "Crypto",
            "tradingview_symbol": "BINANCE:ATOMUSDT.P",
            "csv_path": "ccxt:ATOMUSDT",
            "chart_path": str(tmp_path / "charts" / "ATOMUSDT.P_nhathoai_irb.png"),
        }
    )
    review_row["evidence"].update(
        {
            "qualified": False,
            "pivot": 2.19,
            "current_close": 2.105,
            "distance_to_pivot_pct": 3.88,
            "reasons": [
                "Pattern: IRB",
                "Range description: 2026-04-21 -> 2026-05-19",
                "Inner buildup/block description: 2026-05-20 -> 2026-05-23; area 1.979 - 2.19",
            ],
            "failures": ["Inner block break is not triggered or close enough"],
        }
    )
    payload = result_payload([], [review_row], {"timeframe": "D1", "technique": "nhathoai"})
    results_path = tmp_path / "results.json"
    results_path.write_text(json.dumps(payload))

    report_path = write_html_report(results_path, tmp_path / "index.html")
    html = report_path.read_text()

    assert "Continue Watching" in html
    assert 'data-status="review"' in html
    assert 'class="lazy-chart"' in html
    assert 'data-src="charts/ATOMUSDT.P_nhathoai_irb.png"' in html
    assert 'loading="lazy"' in html
    assert 'decoding="async"' in html
    assert "IntersectionObserver" in html
    assert "ATOMUSDT" in html
    assert "ATOMUSDT.P_nhathoai_irb.png" in html


def test_direction_filter_keeps_directionless_review_rows_visible(tmp_path: Path) -> None:
    review_row = _candidate("IBM", "sb", 22, "rejected")
    review_row["evidence"]["qualified"] = False
    review_row["evidence"]["reasons"] = ["Pattern: SB"]
    payload = result_payload([], [review_row], {"timeframe": "D1", "technique": "nhathoai"})
    results_path = tmp_path / "results.json"
    results_path.write_text(json.dumps(payload))

    report_path = write_html_report(results_path, tmp_path / "index.html")
    html = report_path.read_text()

    assert 'data-status="review"' in html
    assert 'data-direction=""' in html
    assert "direction !== 'all' && nodeDirection && nodeDirection !== direction" in html


def test_report_renders_rrg_reference_on_lifecycle_review_card(tmp_path: Path) -> None:
    review_row = _candidate("ATOMUSDT", "irb", 60, "rejected")
    review_row.update(
        {
            "market": "Crypto",
            "tradingview_symbol": "BINANCE:ATOMUSDT.P",
            "csv_path": "ccxt:ATOMUSDT",
            "chart_path": str(tmp_path / "charts" / "ATOMUSDT.P_nhathoai_irb.jpg"),
        }
    )
    review_row["evidence"].update(
        {
            "qualified": False,
            "pivot": 2.19,
            "current_close": 2.105,
            "distance_to_pivot_pct": 3.88,
            "reasons": ["Pattern: IRB", "Direction: Long"],
            "failures": ["Inner block break is not triggered or close enough"],
        }
    )
    rrg_path = tmp_path / "rrg-reference" / "atomusdt-rrg-proof.jpg"
    rrg_path.parent.mkdir(parents=True, exist_ok=True)
    rrg_path.write_bytes(b"fake jpg")
    payload = result_payload([], [review_row], {"timeframe": "D1", "technique": "nhathoai"})
    payload["review_setups"][0]["rrg"] = {
        "benchmark": "$ONE",
        "sector": "Crypto",
        "rrg_chart_path": str(rrg_path),
        "stock_intent": {"quadrant": "IMPROVING", "dx1": 0.4, "dy1": 0.6},
        "confidence": {"label": "RRG Early Reference", "tone": "early", "blocks_pattern": False},
    }
    results_path = tmp_path / "results.json"
    results_path.write_text(json.dumps(payload))

    report_path = write_html_report(results_path, tmp_path / "index.html")
    html = report_path.read_text()

    assert 'data-status="review"' in html
    assert "Lifecycle Pattern" in html
    assert "RRG Confidence" in html
    assert "RRG Early Reference" in html
    assert "atomusdt-rrg-proof.jpg" in html


def test_payload_includes_near_pivot_vcp_rejects_as_review_setups() -> None:
    review_row = _candidate("EA", "original-vcp", 20, "rejected")
    review_row.update(
        {
            "technique": "minervini-vcp",
            "setup": "original-vcp",
        }
    )
    review_row["evidence"].update(
        {
            "qualified": False,
            "score": 20,
            "pivot": 204.22,
            "current_close": 203.27,
            "distance_to_pivot_pct": 0.47,
            "reasons": [
                "Current close is 0.47% below pivot, inside entry watch zone",
                "Base depth is controlled at 3.8%",
            ],
            "failures": [
                "Prior uptrend is -1.7%, below 20.0%",
                "Found 0 valid contractions, need at least 2",
                "Volume dry-up cannot be confirmed",
            ],
        }
    )

    payload = result_payload([], [review_row], {"timeframe": "D1", "technique": "minervini-vcp"})

    assert any(item["symbol"] == "EA" and item["setup"] == "original-vcp" for item in payload["review_setups"])


def test_payload_includes_low_score_non_vcp_rejects_as_review_setups() -> None:
    review_row = _candidate("IBM", "sb", 22, "rejected")
    review_row.update(
        {
            "technique": "nhathoai",
            "setup": "sb",
        }
    )
    review_row["evidence"].update(
        {
            "qualified": False,
            "score": 22,
            "pivot": 202.5,
            "current_close": 203.2,
            "distance_to_pivot_pct": 0.35,
            "reasons": [
                "Pattern: SB",
                "Direction: Long",
                "First break trigger: waiting 0.35% from 202.5",
            ],
            "failures": [
                "Status is REJECT, not an active SB entry candidate",
                "Score 22 is below required SB threshold 80",
            ],
        }
    )

    payload = result_payload([], [review_row], {"timeframe": "D1", "technique": "nhathoai"})

    assert any(item["symbol"] == "IBM" and item["setup"] == "sb" for item in payload["review_setups"])


def test_payload_keeps_large_recall_first_review_queue() -> None:
    filler_rows = []
    for index in range(900):
        filler = _candidate(f"FILL{index}", "irb", 79, "rejected")
        filler["evidence"].update(
            {
                "qualified": False,
                "pivot": 100,
                "current_close": 99,
                "distance_to_pivot_pct": 1,
                "reasons": ["Pattern: IRB", "Trigger level: 100", "Stop-loss area: 96"],
                "failures": ["Strict setup failed"],
            }
        )
        filler_rows.append(filler)

    review_row = _candidate("EA", "original-vcp", 22, "rejected")
    review_row.update({"technique": "minervini-vcp", "setup": "original-vcp"})
    review_row["evidence"].update(
        {
            "qualified": False,
            "pivot": 204.22,
            "current_close": 203.27,
            "distance_to_pivot_pct": 0.47,
            "reasons": ["Current close is 0.47% below pivot, inside entry watch zone"],
            "failures": ["Strict VCP setup failed"],
        }
    )

    payload = result_payload([], filler_rows + [review_row], {"timeframe": "D1", "technique": "all-patterns"})

    assert any(item["symbol"] == "EA" and item["setup"] == "original-vcp" for item in payload["review_setups"])


def test_watchlist_change_tracking_marks_new_unchanged_and_dropped(tmp_path: Path) -> None:
    previous_candidate = _candidate("AAPL", "dd", 84, "WAITING")
    previous_payload = result_payload([previous_candidate], [], {"timeframe": "D1"})
    previous_path = tmp_path / "previous.json"
    previous_path.write_text(json.dumps(previous_payload))

    current_candidate = _candidate("AAPL", "dd", 84, "WAITING")
    new_candidate = _candidate("MSFT", "bb", 88, "TRIGGERED")
    current_payload = result_payload([current_candidate, new_candidate], [], {"timeframe": "D1"})

    apply_watchlist_changes(current_payload, previous_path)

    by_symbol = {item["symbol"]: item for item in current_payload["candidates"]}
    assert by_symbol["AAPL"]["watchlist_change"] == "UNCHANGED"
    assert by_symbol["MSFT"]["watchlist_change"] == "NEW"
    assert current_payload["watchlist_dropped"] == []
    assert current_payload["watchlist_changes"]["counts"]["NEW"] == 1

    next_payload = result_payload([new_candidate], [], {"timeframe": "D1"})
    apply_watchlist_changes(next_payload, previous_path)

    assert next_payload["watchlist_dropped"][0]["symbol"] == "AAPL"
    assert next_payload["watchlist_dropped"][0]["watchlist_change"] == "DROPPED"


def _candidate(symbol: str, setup: str, score: int, status: str) -> dict:
    return {
        "symbol": symbol,
        "market": "US stock",
        "tradingview_symbol": f"NASDAQ:{symbol}",
        "csv_path": f"yahoo:{symbol}",
        "timeframe": "D1",
        "technique": "nhathoai",
        "setup": setup,
        "chart_path": "",
        "evidence": {
            "qualified": True,
            "status": status,
            "score": score,
            "pivot": 100,
            "current_close": 99,
            "distance_to_pivot_pct": 1,
            "contractions": [],
            "reasons": ["Direction: Long"],
            "failures": [],
            "base_start_index": None,
            "base_end_index": None,
            "volume_dry_up_ratio": None,
            "prior_uptrend_pct": None,
        },
    }
    assert "visibleResults" in html
