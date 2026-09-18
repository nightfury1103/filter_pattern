import copy
from datetime import date, timedelta

import numpy as np

from filter_pattern.compass_adaptive import (
    library_rows, monthly_stream, calibration_rows, fit_calibrator,
    calibrated_probabilities, validate_gate, forecast,
)


def row(i=0, day="2020-01-01", ret=1., p=.8):
    d = date.fromisoformat(day) + timedelta(days=i)
    return {"symbol": "BTCUSD", "date": d.isoformat(), "index": 200 + i,
            "features": [float(i % 7)] * 15, "weekly_features": [0.] * 8,
            "raw_p": p, "library_month": d.strftime("%Y-%m-01"),
            "outcomes": {"10": {"return_pct": ret, "exit_date": (d + timedelta(days=10)).isoformat()}}}


def test_library_cutoff_uses_mature_labels_and_four_year_window():
    rows = [row(day=d, ret=r) for d, r in (("2018-12-31", 1), ("2019-01-01", 1),
            ("2022-12-21", -1), ("2022-12-22", 1), ("2023-01-01", 1), ("2022-12-01", 0))]
    assert [r["date"] for r in library_rows(rows, "2023-01-01")] == ["2019-01-01", "2022-12-21"]


def test_future_labels_and_features_cannot_change_past_month_forecast():
    history = [row(i, ret=1 if i % 3 else -1) for i in range(1200)]
    original, libraries, manifests = monthly_stream(history, start="2023-01-01")
    changed = copy.deepcopy(history)
    for r in changed:
        if r["outcomes"]["10"]["exit_date"] >= "2023-01-01":
            r["outcomes"]["10"]["return_pct"] *= -100
        if r["date"] >= "2023-02-01":
            r["features"] = [1e6] * 15
    after, _, _ = monthly_stream(changed, start="2023-01-01")
    january = lambda rs: [r["raw_p"] for r in rs if r["date"].startswith("2023-01")]
    assert january(original) == january(after)
    assert len(january(original)) == 31
    for month, library in libraries.items():
        assert all(r["exit_date"] < month for r in library["references"])
        assert manifests[month]["last_label_exit"] < month


def test_mature_new_labels_become_available_next_month():
    r = row(day="2023-01-05")
    assert library_rows([r], "2023-01-01") == []
    assert library_rows([r], "2023-02-01") == [r]


def test_calibration_purges_year_boundary_and_ignores_test_rows():
    rows = [row(i, day="2022-01-01", ret=1 if i % 2 else -1,
                p=.8 if i % 2 else .2) for i in range(365)]
    future = row(day="2024-03-01", ret=-9999)
    selected = calibration_rows(rows + [future], 2024)
    assert len(selected) == 355
    assert all(r["outcomes"]["10"]["exit_date"] < "2023-01-01" for r in selected)
    model = fit_calibrator(selected)
    query = [row(p=.2), row(p=.8)]
    values = calibrated_probabilities(query, model)
    for r in query:
        r["outcomes"]["10"]["return_pct"] *= -100
    assert values == calibrated_probabilities(query, model)
    assert values[0] < .25 and values[1] > .75


def test_no_calibrator_does_not_invent_probability():
    assert fit_calibrator([row()]) is None
    assert calibrated_probabilities([row()], None) == [None]
    rs = forecast([row()], None, {"threshold": None, "status": "failed"})
    assert rs[0]["forecasts"]["selected"] == {"p_up": None, "bias": "WAIT"}


def test_gate_requires_both_sides_counts_flat_wrong_and_cannot_reselect():
    rows = [row(i, ret=1 if i % 2 else -1) for i in range(200)]
    good = [.8 if i % 2 else .2 for i in range(200)]
    gate = validate_gate(rows, good)
    assert gate["threshold"] == .75 and gate["accuracy"] == 1
    # All-Long success cannot qualify as a two-sided compass.
    assert validate_gate([row(i) for i in range(200)], [.8] * 200)["threshold"] is None
    failed = validate_gate(rows, [1 - p for p in good])
    assert failed["threshold"] is None and failed["proposed_threshold"] == .75
    for r in rows[:60]:
        r["outcomes"]["10"]["return_pct"] = 0
    flat = validate_gate(rows, good)
    assert np.isclose(flat["accuracy"], .7) and flat["threshold"] is None


def test_missing_scores_remain_in_gate_coverage():
    rows = [row(i, ret=1 if i % 2 else -1) for i in range(2000)]
    ps = [.8 if i % 2 else .2 for i in range(100)] + [None] * 1900
    gate = validate_gate(rows, ps)
    assert np.isclose(gate["coverage"], .05)
    assert gate["threshold"] is None
