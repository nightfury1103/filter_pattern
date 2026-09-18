from datetime import datetime, timedelta
import math

from filter_pattern.compass_reversion import CANDIDATES, rules, select, signals
from filter_pattern.models import Candle


def test_rules_are_symmetric_and_respect_fixed_boundaries():
    for slow in (-1, 0, 1):
        for z in (-2., -1.5, -1., -.5, 0., .5, 1., 1.5, 2.):
            for previous in (-2., 0., 2.):
                result = rules(slow, z, previous)
                opposite = rules(-slow, -z, -previous)
                assert all(result[m] == -opposite[m] for m in CANDIDATES)
    assert rules(1, -1., -2.) == {'reversion': 1, 'pullback': 1, 'recovery': 1}
    assert rules(1, -.5, -.5) == {'reversion': 0, 'pullback': 1, 'recovery': 0}
    assert rules(1, 0., -1.)['recovery'] == 1
    assert rules(1, .001, -1.)['recovery'] == 0
    assert rules(1, -1.501, -2.)['recovery'] == 0
    assert rules(0, -2., -3.) == {'reversion': 1, 'pullback': 0, 'recovery': 0}
    assert rules(1, None, None) == dict.fromkeys(CANDIDATES, 0)


def test_no_future_repaint_or_signal_carryover():
    cs = [Candle(datetime(2020, 1, 1)+timedelta(days=i), p, p+1, p-1, p, 1)
          for i in range(450) for p in [100+i*.12+4*math.sin(i/6)]]
    full = signals(cs, 'BTCUSD')
    assert signals(cs[:330], 'BTCUSD') == full[:130]
    altered = cs[:330]+[Candle(c.datetime, 200, 202, 198, 200, 1) for c in cs[330:]]
    assert signals(altered, 'BTCUSD')[:130] == full[:130]
    assert any(r['directions']['pullback'] for r in full)
    assert any(r['directions']['recovery'] for r in full)
    for i,r in enumerate(full[3:], 3):
        expected = rules(r['slow_direction'], r['z'], full[i-3]['z'])
        assert {m:r['directions'][m] for m in CANDIDATES} == expected


def test_flat_prices_stay_unconfirmed():
    cs = [Candle(datetime(2020, 1, 1)+timedelta(days=i), 100, 101, 99, 100, 1) for i in range(270)]
    assert all(not r['directions'][m] for r in signals(cs, 'BTCUSD') for m in CANDIDATES)


def test_selection_ignores_future_results_and_requires_both_periods():
    rows = []
    for year in (2022, 2023, 2024):
        for i in range(120):
            day = (datetime(year, 1, 1)+timedelta(days=i)).date().isoformat()
            sign = 1 if i%2 else -1
            rows.append({'index':200+i, 'date':day, 'symbol':'BTCUSD',
                         'directions':dict.fromkeys(CANDIDATES, sign),
                         'outcomes':{'10':{'return_pct':sign,'exit_date':day}}})
    baseline = select(rows, 2024)
    assert baseline['chosen'] == 'reversion'
    for r in rows:
        if r['date'].startswith('2024'):
            r['outcomes']['10']['return_pct'] *= -1
    assert select(rows, 2024) == baseline
    for r in rows:
        if r['date'].startswith('2023'):
            r['outcomes']['10']['return_pct'] *= -1
    assert select(rows, 2024)['chosen'] is None
