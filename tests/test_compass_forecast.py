from __future__ import annotations

import copy
import math
from dataclasses import replace
from datetime import datetime, timedelta

import pytest

pytest.importorskip("sklearn")

from filter_pattern.compass_forecast import (
    PROTOCOL, audit_continuity, bias_from_probability, feature_rows, fit_models, label_rows,
    predict_rows, split_rows, summarize,
)
from filter_pattern.compass_forecast_report import write_forecast_report
from filter_pattern.models import Candle


def candles(n=500):
    values = [100 + .02 * i + 5 * math.sin(i / 9) for i in range(n)]
    return [Candle(datetime(2020, 1, 1) + timedelta(days=i), c, c + 1, c - 1, c, 1000) for i, c in enumerate(values)]


def test_features_are_prefix_causal_and_scale_free():
    data = candles()
    features = feature_rows(data[:350])
    assert features == feature_rows(data)[:150]
    huge = [replace(c, open=c.open*1000, high=c.high*1000, low=c.low*1000, close=c.close*1000) for c in data[:350]]
    for a, b in zip(features, feature_rows(huge)):
        assert a["features"] == pytest.approx(b["features"])


def test_labels_use_next_open_and_do_not_invent_pending_outcomes():
    data = candles()
    rows = label_rows(data, feature_rows(data))
    first = rows[0]
    assert first["outcomes"]["10"]["return_pct"] == pytest.approx(100*(data[210].close/data[201].open-1))
    assert rows[-1]["outcomes"] == {}
    assert "5" in rows[-10]["outcomes"] and "10" not in rows[-10]["outcomes"]


def test_continuity_rejects_missing_years_and_stale_flat_quotes():
    data = candles()
    assert audit_continuity(data)["eligible"]
    gap = data[:300] + [replace(c, datetime=c.datetime+timedelta(days=812)) for c in data[300:]]
    assert not audit_continuity(gap)["eligible"]
    assert audit_continuity(gap)["gaps_over_14_days"][0]["calendar_days"] == 813
    frozen = [replace(c, open=100, high=100, low=100, close=100) for c in data[:20]]
    assert audit_continuity(frozen)["longest_unchanged_zero_range_run"] == 20
    assert not audit_continuity(frozen)["eligible"]


def test_split_purges_forward_labels_crossing_calibration_and_test():
    def row(day, exit_day):
        return {"date": day, "outcomes": {"10": {"exit_date": exit_day}}}
    a = row("2021-12-01", "2021-12-15")
    b = row("2022-01-01", "2022-01-15")
    c = row("2024-01-01", "2024-01-15")
    groups = split_rows([a, b, c, row("2021-12-25", "2022-01-05"), row("2023-12-25", "2024-01-05")])
    assert groups == {"train": [a], "calibration": [b], "test": [c]}


@pytest.mark.parametrize("p,expected", [(0, "SHORT"), (.25, "SHORT"), (.251, "WAIT"), (.749, "WAIT"), (.75, "LONG"), (1, "LONG")])
def test_fixed_confidence_gate(p, expected):
    assert bias_from_probability(p) == expected


def test_invalid_probability_is_not_a_signal():
    for p in [float("nan"), -.01, 1.01]:
        with pytest.raises(ValueError):
            bias_from_probability(p)


def sample_row(i, bias="LONG", result=1.):
    return {"symbol": "TEST", "date": (datetime(2024, 1, 1)+timedelta(days=i)).date().isoformat(),
            "index": 200+i, "extension_atr": .5,
            "forecasts": {"boosted": {"bias": bias}}, "outcomes": {"10": {"return_pct": result}}}


def test_accuracy_coverage_short_and_flat_outcomes():
    rows = [sample_row(0), sample_row(1, "SHORT", -1), sample_row(2, "SHORT", 1),
            sample_row(3, "LONG", 0), sample_row(4, "WAIT", 5)]
    s = summarize(rows, "boosted")
    assert s["signals"] == 4 and s["wins"] == 2 and s["false_signals"] == 2
    assert s["accuracy"] == .5 and s["coverage"] == .8
    assert s["scheduled_signals"] == 1 and s["block_ci95"] is None
    assert s["evidence"] == "not_demonstrated"


def test_wait_does_not_become_zero_percent_accuracy_or_evidence():
    s = summarize([sample_row(i, "WAIT") for i in range(150)], "boosted")
    assert s["accuracy"] is None and s["coverage"] == 0 and s["block_ci95"] is None


def test_sparse_or_constant_results_do_not_claim_certain_bootstrap_interval():
    rows = [sample_row(i, "LONG" if i in (20, 100, 180) else "WAIT") for i in range(240)]
    assert summarize(rows, "boosted")["block_ci95"] is None
    assert summarize([sample_row(i) for i in range(240)], "boosted")["block_ci95"] is None


def test_block_interval_does_not_treat_duplicate_assets_as_independent():
    rows = [sample_row(i, result=1 if (i//40)%2 else -1) for i in range(240)]
    duplicates = rows + [{**r, "symbol": "DUPLICATE"} for r in rows]
    a, b = summarize(rows, "boosted"), summarize(duplicates, "boosted")
    assert a["block_ci95"] == pytest.approx(b["block_ci95"])
    assert a["block_ci95"][1]-a["block_ci95"][0] > 0


def test_test_labels_never_affect_fitting_or_probabilities():
    from threadpoolctl import threadpool_limits
    def samples(start):
        return [{"symbol": "X", "date": str(start+i), "features": [math.sin(i), math.cos(i)],
                 "outcomes": {"10": {"return_pct": 1 if i%3 else -1}}} for i in range(220)]
    groups = {"train": samples(20160000), "calibration": samples(20220000), "test": samples(20240000)}
    changed = copy.deepcopy(groups)
    for r in changed["test"]:
        r["outcomes"]["10"]["return_pct"] *= -1000
        r["features"] = [999999, -999999]
    with threadpool_limits(limits=1):
        a, _ = fit_models(groups)
        b, _ = fit_models(changed)
        pa = predict_rows(a, groups["test"][:5])
        pb = predict_rows(b, groups["test"][:5])
    assert [r["forecasts"] for r in pa] == [r["forecasts"] for r in pb]


def test_insufficient_data_does_not_produce_forecast():
    with pytest.raises(ValueError, match="Insufficient train"):
        fit_models({"train": [], "calibration": [], "test": []})


def test_report_embedded_data_cannot_inject_script(tmp_path):
    target = tmp_path / "index.html"
    write_forecast_report({"symbol": "</script><script>alert(1)</script>"}, target)
    assert "</script><script>alert(1)" not in target.read_text(encoding="utf8")
    assert PROTOCOL["setup_dependency"] is False
