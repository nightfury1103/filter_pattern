from __future__ import annotations

import copy
import math
from datetime import datetime, timedelta

import pytest

pytest.importorskip("sklearn")

from filter_pattern.compass_context_data import CONTEXT_FEATURES
from filter_pattern.compass_exact import GROUPS, SYMBOLS, fit_selected, predict, stages
from filter_pattern.compass_exact_report import write_exact_report


def sample(day, exit_day, value=1):
    return {"date": day, "context": {f: .1 for f in CONTEXT_FEATURES},
            "features": [math.sin(value+i) for i in range(15)],
            "outcomes": {"10": {"return_pct": value, "exit_date": exit_day}}}


def test_exact_screenshot_roster_no_silent_replacements():
    assert SYMBOLS == ("XAUUSD", "BTCUSD", "ETHUSD", "DXY", "US500", "SPY", "E1VFVN30")
    assert len(GROUPS) == 6 and GROUPS[1] == ("Crypto", ("BTCUSD", "ETHUSD"))
    assert "GOLD_FUTURES" not in SYMBOLS and "VNINDEX" not in SYMBOLS


def test_all_selection_calibration_and_test_boundaries_purged():
    a = sample("2021-10-01", "2021-10-15")
    b = sample("2022-10-01", "2022-10-15")
    c = sample("2023-10-01", "2023-10-15")
    pending = {"date": "2024-12-30", "context": None, "outcomes": {}}
    cross_a = sample("2021-12-25", "2022-01-10")
    cross_b = sample("2022-12-25", "2023-01-10")
    cross_c = sample("2023-12-25", "2024-01-10")
    g = stages([a,b,c,pending,cross_a,cross_b,cross_c],2024)
    assert g["inner_train"] == [a]
    assert g["validation"] == [b]
    assert g["refit"] == [a,b,cross_a]
    assert g["calibration"] == [c]
    assert g["test"] == [pending]


def test_missing_context_and_exact_flat_not_used_for_model_fit():
    rows = [sample("2021-01-01","2021-01-15",0),
            {**sample("2021-02-01","2021-02-15"),"context":None}]
    assert stages(rows,2024)["inner_train"] == []


def test_selected_models_and_predictions_cannot_see_test_outcomes():
    from threadpoolctl import threadpool_limits
    def period(year):
        start = datetime(year,1,1)
        return [sample((start+timedelta(days=i)).date().isoformat(),
                       (start+timedelta(days=i+10)).date().isoformat(),1 if i%3 else -1) for i in range(220)]
    g = {"inner_train":period(2021),"validation":period(2022),
         "refit":period(2021)+period(2022),"calibration":period(2023),"test":period(2024)}
    altered = copy.deepcopy(g)
    for r in altered["test"]:
        r["features"] = [1e9]*15
        r["outcomes"]["10"]["return_pct"] *= -100000
    with threadpool_limits(limits=1):
        a,ma = fit_selected(g)
        b,mb = fit_selected(altered)
        pa,pb = predict(g["test"][:3],a),predict(g["test"][:3],b)
    assert ma == mb
    assert [r["forecasts"] for r in pa] == [r["forecasts"] for r in pb]
    assert all(len(ma[m]["validation_brier"])==3 for m in ("context","price_only"))


def test_insufficient_fit_is_visible_and_no_probability_invented():
    g={key:[] for key in ("inner_train","validation","refit","calibration","test")}
    models,manifest=fit_selected(g)
    assert not models and manifest["status"] == "insufficient_inner_train"
    r=sample("2024-01-01","2024-01-15")
    p=predict([r],models)[0]
    assert p["forecasts"]["context"] == {"p_up":None,"bias":"WAIT"}


def test_report_preserves_escaped_external_labels(tmp_path):
    target=tmp_path/'index.html'
    write_exact_report({"label":"</script><script>alert(1)</script>"},target)
    text=target.read_text(encoding='utf8')
    assert '</script><script>alert(1)' not in text
    assert 'Market Representative Compass' in text
