from __future__ import annotations

import copy
import math
from dataclasses import replace
from datetime import datetime, timedelta

import pytest

pytest.importorskip("sklearn")

from filter_pattern.compass import validate_candles
from filter_pattern.compass_context import confirmation_rule, fit_fold, fold_split, predict_fold, quick_metrics
from filter_pattern.compass_context_data import CONTEXT_FEATURES, ETF_SOURCES, attach_context, audit_context, build_context
from filter_pattern.compass_context_report import write_context_report
from filter_pattern.models import Candle


def candles(n=350):
    return [Candle(datetime(2020, 1, 1)+timedelta(days=i), 100+i*.03+math.sin(i/7),
                   102+i*.03+math.sin(i/7), 98+i*.03+math.sin(i/7),
                   100+i*.03+math.sin(i/7), 1000) for i in range(n)]


def test_machine_precision_tolerance_does_not_allow_real_bad_ohlc():
    c = candles(1)[0]
    validate_candles([replace(c, high=math.nextafter(c.close, 0))])
    with pytest.raises(ValueError, match="OHLC"):
        validate_candles([replace(c, high=c.close-.00001)])
    with pytest.raises(ValueError, match="OHLC"):
        validate_candles([replace(c, low=c.open+.00001)])


def test_context_join_forbids_same_day_and_stale_values():
    context = [{"date": d, "values": {"value": i}} for i, d in enumerate(["2024-01-05", "2024-01-08"])]
    rows = [{"date": d} for d in ["2024-01-05", "2024-01-06", "2024-01-08", "2024-01-09", "2024-01-14"]]
    attached = attach_context(rows, context)
    assert attached[0]["context"] is None
    assert attached[1]["context"] == {"value": 0}
    assert attached[2]["context_date"] == "2024-01-05"
    assert attached[3]["context"] == {"value": 1}
    assert attached[4]["context"] is None and attached[4]["context_age_days"] == 6


def test_context_feature_history_cannot_change_with_future_prices():
    symbols = (*ETF_SOURCES, "VIX", "VIX3M", "DXY")
    data = {s: candles(400) for s in symbols}
    before = build_context({s: c[:350] for s, c in data.items()})
    altered = {s: c[:350]+[replace(r, open=r.open*10, high=r.high*10, low=r.low*10, close=r.close*10) for r in c[350:]] for s, c in data.items()}
    assert before == build_context(altered)[:len(before)]
    assert len(before[-1]["values"]) == len(CONTEXT_FEATURES) == 14


def test_missing_source_is_explicit_error_not_silent_breadth_change():
    with pytest.raises(ValueError, match="Missing validated context"):
        build_context({"SPY": candles()})


def test_source_audit_keeps_bad_source_visible():
    from dataclasses import asdict
    from datetime import date
    rows = [{**asdict(c), "datetime": c.datetime.isoformat()} for c in candles()]
    rows[50]["high"] = rows[50]["close"] - 5
    accepted, metadata, errors = audit_context({"sources": {"BAD": {"candles": rows}}}, date(2026, 9, 17))
    assert not accepted and not metadata and "OHLC" in errors["BAD"]


def test_fold_purges_both_boundaries_and_keeps_unavailable_test_days():
    def row(day, exit_day):
        return {"date": day, "context": {"ok": 1}, "outcomes": {"10": {"exit_date": exit_day, "return_pct": 1}}}
    train = row("2022-11-01", "2022-11-15")
    cal = row("2023-11-01", "2023-11-15")
    test = {"date": "2024-06-01", "context": None, "outcomes": {}}
    groups = fold_split([train, cal, test, row("2022-12-25", "2023-01-05"), row("2023-12-25", "2024-01-05")], 2024)
    assert groups == {"train": [train], "calibration": [cal], "test": [test]}


def rule_row():
    return {"date": "2024-01-01", "features": [0, 1]+[0]*13, "extension_atr": 1.,
            "context": {**{f: 0. for f in CONTEXT_FEATURES}, "sector_above_ema50": 8/9,
                        "credit_minus_treasury5": .01, "vix_term_ratio": .8,
                        "dollar_z20": -1., "treasury_z20": 1.}}


def test_confirmation_rule_is_directional_and_rejects_chasing():
    r = rule_row()
    assert confirmation_rule(r, "US500") == "LONG"
    assert confirmation_rule(r, "GOLD_FUTURES") == "LONG"
    r["extension_atr"] = 2.01
    assert confirmation_rule(r, "US500") == "WAIT"
    r["extension_atr"] = -1
    r["features"][1] = -1
    r["context"].update(sector_above_ema50=1/9, credit_minus_treasury5=-.01, vix_term_ratio=1.1)
    assert confirmation_rule(r, "BTCUSD") == "SHORT"
    assert confirmation_rule({**r, "context": None}, "BTCUSD") == "WAIT"


def test_no_model_fit_never_fabricates_probability():
    r = rule_row()
    p = predict_fold([r, {**r, "context": None}], {}, "US500")
    assert p[0]["forecasts"]["context"]["p_up"] is None
    assert p[0]["forecasts"]["context"]["bias"] == "WAIT"
    assert p[0]["forecasts"]["confirmation"]["bias"] == "LONG"
    assert p[1]["forecasts"]["confirmation"]["bias"] == "WAIT"


def test_test_outcomes_and_features_never_enter_training_or_calibration():
    from threadpoolctl import threadpool_limits
    def samples(year):
        return [{**rule_row(), "date": (datetime(year, 1, 1)+timedelta(days=i)).date().isoformat(),
                 "features": [math.sin(i+j) for j in range(15)],
                 "outcomes": {"10": {"return_pct": 1 if i%3 else -1,
                                       "exit_date": (datetime(year, 1, 1)+timedelta(days=i+10)).date().isoformat()}}} for i in range(220)]
    a = {"train": samples(2022), "calibration": samples(2023), "test": samples(2024)}
    b = copy.deepcopy(a)
    for r in b["test"]:
        r["features"] = [99999.]*15
        r["outcomes"]["10"]["return_pct"] *= -10000
    with threadpool_limits(limits=1):
        ma, fa = fit_fold(a)
        mb, fb = fit_fold(b)
        pa = predict_fold(a["test"][:5], ma, "US500")
        pb = predict_fold(a["test"][:5], mb, "US500")
    assert fa == fb
    assert [r["forecasts"] for r in pa] == [r["forecasts"] for r in pb]


def test_wait_remains_in_coverage_denominator():
    rows = [{"outcomes": {"10": {"return_pct": result}}, "forecasts": {"context": {"bias": bias}}}
            for result, bias in [(1., "LONG"), (-1., "SHORT"), (0., "SHORT"), (1., "WAIT")]]
    m = quick_metrics(rows, "context")
    assert m["accuracy"] == 2/3 and m["coverage"] == .75 and m["signals"] == 3


def test_context_report_escapes_embedded_json(tmp_path):
    path = tmp_path / "report.html"
    write_context_report({"label": "</script><script>bad()</script>"}, path)
    assert "</script><script>bad()" not in path.read_text(encoding="utf8")
