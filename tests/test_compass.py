from __future__ import annotations

import json
import math
from dataclasses import replace
from datetime import date, datetime, timedelta

import pytest

from filter_pattern.compass import calculate_compass_series, setup_alignment, validate_candles
from filter_pattern.compass_research import (
    bootstrap_intervals, build_trials, evidence_status, load_research_data,
    outcome, reaction_delay, run_compass_research, stability, summarize_side,
)
from filter_pattern.models import Candle


def candles(count=500, direction=1, scale=1.0):
    start = datetime(2020, 1, 1)
    closes = [100 * scale * math.exp(direction * (0.002 * i + 0.002 * math.sin(i / 3))) for i in range(count)]
    return [Candle(start + timedelta(days=i), c, c * 1.006, c * .994, c, 1000) for i, c in enumerate(closes)]


def test_signal_prefix_cannot_see_future_prices():
    data = candles()
    before = calculate_compass_series(data[:300])
    after = calculate_compass_series(data[:300] + [replace(c, open=c.open * .01, high=c.high * .01, low=c.low * .01, close=c.close * .01) for c in data[300:]])
    assert all(before[model] == after[model][:300] for model in before)


def test_multi_horizon_and_atr_are_symmetric_and_price_scale_invariant():
    up = calculate_compass_series(candles())
    down = calculate_compass_series(candles(direction=-1))
    tiny = calculate_compass_series(candles(scale=1e-7))
    for model in up:
        assert up[model][-1]["bias"] == "LONG"
        # EMA/ATR's acceleration condition may temporarily wait during a trend.
        if model != "ema_atr":
            assert down[model][-1]["bias"] == "SHORT"
        assert tiny[model][-1]["bias"] == up[model][-1]["bias"]
        assert tiny[model][-1]["score"] == pytest.approx(up[model][-1]["score"])
    assert down["multi_horizon"][-1]["score"] == pytest.approx(-up["multi_horizon"][-1]["score"])


def test_flat_or_insufficient_history_never_issues_direction():
    data = [replace(c, open=100, high=100, low=100, close=100) for c in candles()]
    for rows in calculate_compass_series(data).values():
        assert all(row["bias"] == "WAIT" for row in rows)
    for rows in calculate_compass_series(candles(200)).values():
        assert all(not row["available"] and row["bias"] == "WAIT" for row in rows)


@pytest.mark.parametrize("bad", [0, float("nan"), float("inf")])
def test_bad_prices_rejected(bad):
    with pytest.raises(ValueError):
        validate_candles([replace(candles(1)[0], close=bad)])


def test_invalid_ohlc_and_duplicate_dates_rejected():
    data = candles(3)
    with pytest.raises(ValueError, match="OHLC"):
        validate_candles([replace(data[0], high=99)])
    with pytest.raises(ValueError, match="unique"):
        validate_candles([data[0], data[0]])


def test_outcome_starts_next_open_and_records_actual_adverse_excursion():
    data = candles(8)
    data[1] = replace(data[1], open=120, high=130, low=90, close=125)
    for i in range(2, 6):
        data[i] = replace(data[i], open=120, high=125, low=115, close=120)
    result = outcome(data, 0, 5)
    assert result["return_pct"] == 0
    assert result["low_pct"] == -25
    assert result["high_pct"] == pytest.approx(100 * (130 / 120 - 1))
    assert result["entry_date"] == "2020-01-02"
    assert result["exit_date"] == "2020-01-06"
    with pytest.raises(ValueError):
        outcome(data, 6, 5)


def test_chronological_split_purges_crossing_labels_and_schedule_is_model_independent():
    data = candles()
    signals = calculate_compass_series(data)
    cutoff = data[350].datetime.date().isoformat()
    groups = build_trials(data, signals["multi_horizon"], 20, cutoff)
    assert all(r["exit_date"] < cutoff for r in groups["development"])
    assert all(r["date"] >= cutoff for r in groups["holdout"])
    other = build_trials(data, signals["ema"], 20, cutoff)
    first = [r["index"] for r in groups["holdout"] if r["scheduled"]]
    assert first == [r["index"] for r in other["holdout"] if r["scheduled"]]
    assert all(b - a >= 20 for a, b in zip(first, first[1:]))


def test_correct_short_outcomes_and_wait_coverage():
    rows = [{"bias": b, "return_pct": r, "low_pct": -5, "high_pct": 3, "scheduled": True}
            for b, r in [("SHORT", -2), ("SHORT", 1), ("WAIT", 8), ("LONG", 10)]]
    summary = summarize_side(rows, "SHORT")
    assert summary["hit_rate"] == .5
    assert summary["coverage"] == .5
    assert summary["mean_return_pct"] == .5
    assert summary["mean_adverse_pct"] == -3
    assert summary["mean_favorable_pct"] == 5


def test_no_extra_claim_for_always_long_in_a_rising_market():
    rows = [{"bias": "LONG", "return_pct": 2, "low_pct": -1, "high_pct": 3, "scheduled": True} for _ in range(100)]
    summary = summarize_side(rows, "LONG")
    assert summary["hit_rate"] == 1
    assert summary["lift_ci95"] == [0.0, 0.0]
    assert evidence_status(summary) == "not_demonstrated"
    assert bootstrap_intervals(rows, "LONG") == bootstrap_intervals(rows, "LONG")
    assert evidence_status(summarize_side(rows[:5], "LONG")) == "insufficient"


def test_stability_counts_opposite_signals_through_wait():
    rows = [{"available": True, "bias": b} for b in ["LONG", "WAIT", "SHORT", "SHORT", "WAIT", "LONG"]]
    result = stability(rows)
    assert result["state_changes"] == 4
    assert result["opposite_within_5_bars"] == 2


def test_setup_alignment_does_not_treat_weak_long_as_short():
    assert setup_alignment("WAIT", "short") == "WAIT"
    assert setup_alignment("LONG", "long") == "ALIGNED"
    assert setup_alignment("SHORT", "long") == "AGAINST"
    assert setup_alignment("LONG", "unknown") == "WAIT"


def test_reaction_delay_reports_missing_signals_instead_of_zero_delay():
    data = candles()
    signals = [{"date": c.datetime.date().isoformat(), "bias": "WAIT"} for c in data]
    result = reaction_delay(data, signals, "2020-01-01")
    assert result["events"] == 1
    assert result["missed_within_10"] == 1
    assert result["median_delay_bars"] is None
    signals[203]["bias"] = "LONG"
    result = reaction_delay(data, signals, "2020-01-01")
    assert result["recognized_within_10"] == 1
    assert result["median_delay_bars"] == 3


def write_cache(path, data):
    rows = [{"datetime": c.datetime.isoformat(), "open": c.open, "high": c.high, "low": c.low, "close": c.close, "volume": c.volume} for c in data]
    path.write_text(json.dumps({"instruments": {"TEST": {"metadata": {"label": "TEST", "market": "Crypto", "source": "fixture", "provider": "fixture", "proxy": False}, "candles": rows}}, "errors": {"MISSING": "unavailable"}}), encoding="utf-8")


def test_cached_data_excludes_incomplete_candle_and_preserves_provenance(tmp_path):
    source = tmp_path / "cache.json"
    write_cache(source, candles())
    cutoff = candles()[450].datetime.date()
    data, metadata, errors = load_research_data(tmp_path / "out", before=cutoff, cache_path=source)
    assert len(data["TEST"]) == 450
    assert metadata["TEST"]["excluded_on_or_after_cutoff"] == 50
    assert len(metadata["TEST"]["sha256"]) == 64
    assert errors == {"MISSING": "unavailable"}
    _, replay_meta, _ = load_research_data(tmp_path / "replay", before=cutoff, cache_path=tmp_path / "out/candles.json")
    assert replay_meta["TEST"]["sha256"] == metadata["TEST"]["sha256"]
    assert replay_meta["TEST"]["original_excluded_on_or_after_cutoff"] == 50


def test_offline_report_has_real_metrics_and_explicit_research_status(tmp_path):
    source = tmp_path / "cache.json"
    write_cache(source, candles())
    rrg_path = tmp_path / "rrg.json"
    rrg_snapshot = {"generated_at": "2020-01-01", "rrg_reference": {"market_representatives": [{"symbol": "TEST", "rrg": {"benchmark": "$ONE", "rrg_series": [{"x": 101, "y": 102}]}}]}}
    rrg_path.write_text(json.dumps(rrg_snapshot), encoding="utf-8")
    result = run_compass_research(tmp_path / "report", cache_path=source, rrg_results=rrg_path)
    payload = json.loads(result.read_text(encoding="utf-8"))
    asset = payload["assets"]["TEST"]
    assert payload["applies_to_scanner"] is False
    assert len(payload["implementation_sha256"]["compass.py"]) == 64
    assert asset["latest"]["bias"] == "WAIT"  # Old fixture is stale now.
    assert asset["latest"]["raw_bias"] == "LONG"
    assert asset["models"]["multi_horizon"]["horizons"]["10"]["holdout"]["LONG"]["samples"] > 0
    html = (result.parent / "index.html").read_text(encoding="utf-8")
    assert 'lang="vi"' in html and "RRG hiện tại" in html
    assert (result.parent / "protocol.md").exists()
    assert payload["rrg_comparison"]["historical_ab_test"] is False
    assert payload["rrg_comparison"]["reference"] == rrg_snapshot["rrg_reference"]
    assert json.loads(rrg_path.read_text()) == rrg_snapshot


def test_report_escapes_embedded_script_boundaries(tmp_path):
    from filter_pattern.compass_report import write_compass_report
    path = write_compass_report({"source": "</script><script>alert(1)</script>"}, tmp_path / "index.html")
    html = path.read_text(encoding="utf-8")
    assert "</script><script>alert(1)" not in html
    assert "\\u003c/script>" in html


def test_cli_dispatches_research_options(tmp_path, monkeypatch):
    from filter_pattern.cli import main
    seen = []
    monkeypatch.setattr("filter_pattern.cli.run_compass_research", lambda *args: seen.append(args) or tmp_path / "results.json")
    assert main(["compass-research", "--out", str(tmp_path), "--cache", "candles.json", "--before", "2026-01-01"]) == 0
    assert seen[0] == (str(tmp_path), "10y", None, "2026-01-01", "candles.json", None)
