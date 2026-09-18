from datetime import datetime, timedelta

from filter_pattern.compass_wave import advance, wave_series
from filter_pattern.models import Candle


def candles(prices):
    return [Candle(datetime(2020, 1, 1)+timedelta(days=i), p, p+1, p-1, p, 100.) for i,p in enumerate(prices)]


def test_buffer_holds_previous_direction_and_requires_matching_slope():
    assert advance("LONG", 99.5, 100, 101, 2) == "LONG"
    assert advance("LONG", 98, 100, 101, 2) == "SHORT"
    assert advance("SHORT", 102, 100, 99, 2) == "LONG"
    assert advance("WAIT", 102, 100, 101, 2) == "WAIT"
    assert advance("LONG", 99, 100, 101, 2) == "LONG"  # strict boundary
    assert advance("LONG", 90, 100, 101, 0) == "LONG"


def test_states_follow_sustained_rise_and_fall_without_backdating():
    prices=[100.]*220+[100.+i for i in range(1,51)]+[150.-i for i in range(1,61)]
    output=wave_series(candles(prices))
    assert all(r['bias']=='WAIT' for r in output[:220])
    assert output[269]['bias']=='LONG'
    assert output[-1]['bias']=='SHORT'
    first_short=next(i for i,r in enumerate(output) if r['bias']=='SHORT')
    assert first_short>270  # no claim to know the top as it happened
    assert all(r['p_up'] is None for r in output)


def test_prefix_invariance_prevents_repainting_when_future_changes():
    prices=[100.]*220+[100.+i*.5 for i in range(80)]
    original=wave_series(candles(prices))
    for end in [201,223,251,280]:
        assert wave_series(candles(prices[:end]))==original[:end]
    changed=wave_series(candles(prices[:260]+[90.-i*.1 for i in range(40)]))
    assert changed[:260]==original[:260]


def test_constant_price_and_empty_history_are_safe():
    assert wave_series([])==[]
    assert {r['bias'] for r in wave_series(candles([100.]*250))}=={'WAIT'}
