from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

from filter_pattern.chart import _minimum_body_height, _price_label, _date_formatter, _session_positions, render_chart
from filter_pattern.detector import detect_vcp
from filter_pattern.models import Candle, ScanResult, SymbolSpec
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
    assert chart_path.suffix == ".jpg"
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
    assert 'loading="lazy"' in html
    assert 'decoding="async"' in html
    assert "ATOMUSDT" in html
    assert "ATOMUSDT.P_nhathoai_irb.png" in html


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
