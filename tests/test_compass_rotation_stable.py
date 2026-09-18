import copy
from datetime import datetime,timedelta

from filter_pattern.compass_rotation_stable import hysteresis,series,stability,latency
from filter_pattern.models import Candle


def candles(prices):
    return [Candle(datetime(2020,1,1)+timedelta(days=i),p,p+1,p-1,p,100.) for i,p in enumerate(prices)]


def test_deadband_requires_opposite_boundary_not_zero_cross():
    assert hysteresis(1,-.09,.1)==1
    assert hysteresis(1,-.1,.1)==1
    assert hysteresis(1,-.10001,.1)==-1
    assert hysteresis(-1,.09,.1)==-1
    assert hysteresis(0,.05,.1)==0
    assert hysteresis(0,.11,.1)==1


def test_no_future_repaint_and_states_match_coordinates_outside_bands():
    prices=[100.]*210+[100.+i*.8 for i in range(60)]+[148.-i*.9 for i in range(70)]
    cs=candles(prices);result=series(cs)
    for end in [205,224,262,280,319]:assert series(cs[:end])==result[:end]
    changed=series(candles(prices[:280]+[80.+i*.1 for i in range(60)]))
    assert changed[:280]==result[:280]
    assert result[260]['phase']=='LEADING'
    assert result[-1]['phase'] in ('LAGGING','IMPROVING')
    for r in result[200:]:
        if not r['within_buffer']:assert r['phase']==r['raw_phase']
    assert all(r['trend_sign']==0 and r['momentum_sign']==0 for r in result[:200])


def test_flat_stays_unconfirmed_and_stability_counts_returns():
    assert {r['phase'] for r in series(candles([100.]*240))}=={'CENTER'}
    rows=[{'forecasts':{'wave':{'phase':s}}} for s in ['LEADING','WEAKENING','LEADING','LEADING']]
    assert stability(rows,'wave')=={'days':4,'changes':2,'median_run':1,'one_bar_runs':2,'back_next_day':1}


def test_latency_compares_same_events_and_counts_misses():
    cs=candles([100.]*210+[101.+i for i in range(40)]+[140.-i*2 for i in range(40)])
    signals=series(cs)
    result=latency(cs,signals,'2020-01-01')
    assert result['models']['wave']['events']==result['models']['original']['events']==2
    for model in ('wave','original'):
        s=result['models'][model]
        assert s['recognized_within10']+s['missed']==s['events']
    modified=copy.deepcopy(signals)
    for r in modified:r['trend_sign']=0
    missing=latency(cs,modified,'2020-01-01')
    assert missing['models']['wave']['missed']==2
    assert missing['paired_median_extra_bars'] is None
