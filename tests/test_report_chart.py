from __future__ import annotations

import json
from pathlib import Path

from filter_pattern.chart import render_chart
from filter_pattern.detector import detect_vcp
from filter_pattern.models import ScanResult, SymbolSpec
from filter_pattern.report import apply_watchlist_changes, result_payload, write_combined_html_report, write_html_report
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
    payload = result_payload([result.to_json()], [], {"timeframe": "D1"})
    results_path = tmp_path / "results.json"
    results_path.write_text(json.dumps(payload))

    report_path = write_html_report(results_path, tmp_path / "index.html")

    assert chart_path.exists()
    assert chart_path.stat().st_size > 0
    assert report_path.exists()
    html = report_path.read_text()
    assert "AAPL" in html
    assert "Scanned Universe (1 symbols)" in html
    assert 'id="marketFilter"' in html
    assert 'id="techniqueFilter"' in html
    assert 'id="setupFilter"' in html
    assert 'id="filterCount"' in html
    assert 'id="coverageSection"' in html
    assert "applyFilters();" in html
    assert 'data-filterable="true"' in html


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
