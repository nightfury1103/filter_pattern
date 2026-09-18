from datetime import datetime, timedelta
import math

from filter_pattern.compass_confidence70 import signals, metrics, prior_year, select, CANDIDATES
from filter_pattern.models import Candle


def test_signals_causal_with_nested_filters_and_no_repaint():
    cs = [Candle(datetime(2020, 1, 1)+timedelta(days=i), p, p+1, p-1, p, 1)
          for i in range(390) for p in [100+i*.03+10*math.sin(i/16)]]
    full = signals(cs, 'BTCUSD')
    assert signals(cs[:310], 'BTCUSD') == full[:110]
    changed = cs[:310] + [Candle(c.datetime, 200, 202, 198, 200, 1) for c in cs[310:]]
    assert signals(changed, 'BTCUSD')[:110] == full[:110]
    assert any(r['directions']['aligned'] > 0 for r in full)
    assert any(r['directions']['aligned'] < 0 for r in full)
    for row in full:
        d = row['directions']
        assert not d['bounded'] or d['bounded'] == d['confirmed'] == d['aligned'] == d['base']
        assert not d['confirmed'] or d['confirmed'] == d['aligned'] == d['base']


def row(symbol, day, value, sign=1, exit_date=None):
    return {'symbol': symbol, 'date': day, 'index': 200,
            'directions': {m: sign for m in CANDIDATES},
            'outcomes': {'10': {'return_pct': value, 'exit_date': exit_date or day}}}


def test_weighting_before_filter_and_flat_is_wrong():
    rows = [row('BTCUSD', '2024-01-01', 1), row('BTCUSD', '2024-01-02', 0, 0),
            row('US500', '2024-01-01', -1), row('SPY', '2024-01-01', -1)]
    m = metrics(rows, 'aligned')
    assert math.isclose(m['coverage'], .75)
    assert math.isclose(m['accuracy'], 1/3)
    assert m['wins'] == 1 and m['false_signals'] == 2
    flat = metrics([row('BTCUSD', '2024-01-01', 0)], 'aligned')
    assert flat['accuracy'] == 0 and not flat['evidence70']


def test_selection_purges_boundaries_and_never_sees_test_results():
    rows = []
    for year in (2022, 2023, 2024):
        for i in range(120):
            day = (datetime(year, 1, 1)+timedelta(days=i)).date().isoformat()
            sign = 1 if i % 2 else -1
            rows.append(row('BTCUSD', day, sign, sign))
    rows.append(row('BTCUSD', '2023-12-29', -1, exit_date='2024-01-05'))
    assert len(prior_year(rows, 2023)) == 120
    before = select(rows, 2024)
    assert before['chosen'] == 'aligned'
    for r in rows:
        if r['date'].startswith('2024'):
            r['outcomes']['10']['return_pct'] *= -1
    assert select(rows, 2024) == before
    for r in rows:
        if r['date'].startswith('2023'):
            r['outcomes']['10']['return_pct'] *= -1
    assert select(rows, 2024)['chosen'] is None


def test_empty_signals_do_not_claim_accuracy_or_evidence():
    m = metrics([row('BTCUSD', '2024-01-01', 1, 0)], 'aligned')
    assert m['signals'] == 0 and m['accuracy'] is None and m['ci95'] is None
    assert m['coverage'] == 0 and not m['evidence70']
