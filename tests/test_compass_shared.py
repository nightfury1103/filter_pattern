from datetime import date,datetime,timedelta

import numpy as np

from filter_pattern.models import Candle
from filter_pattern.compass_shared import prepare,split,weights,choose,forecast


def candles(n):
    start=datetime(2021,1,1)
    return [Candle(start+timedelta(days=i),100+i*.1,102+i*.1,99+i*.1,101+i*.1,100.) for i in range(n)]


def test_closed_week_features_do_not_use_future_or_current_week_close():
    full=candles(450)
    day=full[400].datetime.date()
    prefix=prepare(full[:401],'BTCUSD')[-1]
    longer=next(r for r in prepare(full,'BTCUSD') if r['date']==day.isoformat())
    assert prefix['features']==longer['features']
    assert prefix['weekly_features']==longer['weekly_features']
    assert date.fromisoformat(prefix['weekly_start'])<date.fromisocalendar(day.isocalendar().year,day.isocalendar().week,1)
    changed=list(full)
    for i,c in enumerate(changed):
        if i>400:changed[i]=Candle(c.datetime,c.open*3,c.high*3,c.low*3,c.close*3,c.volume)
    after=next(r for r in prepare(changed,'BTCUSD') if r['date']==day.isoformat())
    assert after['weekly_features']==prefix['weekly_features']


def test_split_purges_all_three_boundaries():
    rows=[]
    for day in ['2021-06-01','2021-12-28','2022-06-01','2022-12-28','2023-06-01','2023-12-28','2024-01-01']:
        rows.append({'date':day,'outcomes':{'10':{'return_pct':1.,'exit_date':(date.fromisoformat(day)+timedelta(days=10)).isoformat()}}})
    g=split(rows,2024)
    assert [r['date'] for r in g['train']]==['2021-06-01']
    assert [r['date'] for r in g['calibration']]==['2022-06-01']
    assert [r['date'] for r in g['validation']]==['2023-06-01']
    assert [r['date'] for r in g['test']]==['2024-01-01']


def test_shared_exposure_weights_do_not_double_count_spy_us500():
    rows=[{'symbol':'US500'}]*2+[{'symbol':'SPY'}]*4+[{'symbol':'BTCUSD'}]*8
    w=weights(rows)
    assert np.isclose(w[:2].sum(),w[2:6].sum())
    assert np.isclose(w[:6].sum(),w[6:].sum())


def validation_rows(n=200):
    return [{'symbol':'BTCUSD','outcomes':{'10':{'return_pct':1. if i%2 else -1.}}} for i in range(n)]


def test_selection_fails_unidirectional_even_if_accuracy_is_high():
    rows=validation_rows()
    for r in rows:r['outcomes']['10']['return_pct']=1.
    selected=choose(rows,{'daily':np.full(len(rows),.9)})
    assert selected['model']=='daily'
    assert selected['threshold'] is None
    assert selected['status']=='validation_gate_failed'


def test_selection_uses_validation_and_one_global_threshold():
    rows=validation_rows()
    good=np.array([.8 if i%2 else .2 for i in range(len(rows))])
    s=choose(rows,{'daily':np.full(len(rows),.5),'weekly':good})
    assert s['model']=='weekly' and s['threshold']==.55
    assert all(t['signals']<=len(rows) for t in s['trials'])
    bad=choose(rows,{'daily':np.full(len(rows),.5)})
    assert bad['threshold'] is None


def test_no_fit_no_probability_invented():
    r={'features':[0.]*15,'weekly_features':[0.]*8,'outcomes':{}}
    out=forecast([r],{}, {'model':None,'threshold':None,'status':'no_validation'})
    assert out[0]['forecasts']['selected']=={'p_up':None,'bias':'WAIT'}
