import copy
import math

from filter_pattern.compass_rotation import quadrant, phase_rows, summarize_phases


def test_quadrants_distinguish_direction_from_change():
    assert quadrant(1,1)=='LEADING'
    assert quadrant(1,-1)=='WEAKENING'
    assert quadrant(-1,-1)=='LAGGING'
    assert quadrant(-1,1)=='IMPROVING'
    assert quadrant(0,1)=='CENTER'
    assert quadrant(1,0)=='CENTER'
    assert quadrant(None,1)=='MISSING'
    assert quadrant(math.nan,1)=='MISSING'


def row(x,y,ret=1):
    return {'date':'2024-01-01','index':200,'symbol':'BTCUSD','close':100.,
            'forecasts':{'wave':{'score':x,'momentum':y}},'outcomes':{'10':{'return_pct':ret}}}


def test_phase_independent_of_future_outcome_and_never_forces_cycle():
    rows=[row(1,1),row(1,-1),row(1,1),row(-1,-1)]
    phases=phase_rows(rows)
    assert [r['forecasts']['wave']['phase'] for r in phases]==['LEADING','WEAKENING','LEADING','LAGGING']
    changed=copy.deepcopy(rows)
    for r in changed:r['outcomes']['10']['return_pct']=-999
    assert [r['forecasts'] for r in phase_rows(changed)]==[r['forecasts'] for r in phases]
    assert all('bias' not in r['forecasts']['wave'] for r in phases)


def test_stats_preserve_flat_missing_outcomes_and_empty_phases():
    rows=phase_rows([row(1,1,2),row(1,1,-1),row(1,1,0),row(1,-1,3)])
    future=row(-1,1);future['outcomes']={};rows+=phase_rows([future])
    stats=summarize_phases(rows,10)
    leading=stats['LEADING']
    assert leading['days']==3 and leading['up']==leading['down']==leading['flat']==1
    assert leading['coverage']==.75
    assert math.isclose(leading['mean_return_pct'],1/3)
    assert stats['IMPROVING']['days']==0 and stats['IMPROVING']['up_rate'] is None
