import copy
from datetime import date,timedelta

import numpy as np
from sklearn.preprocessing import RobustScaler

from filter_pattern.compass_analog import matrix,fit_library,probabilities,split,confirm,forecast


def row(i=0,ret=1.,day='2020-01-01'):
    day=date.fromisoformat(day)+timedelta(days=i)
    return {'symbol':'BTCUSD','date':day.isoformat(),'index':200+i,'features':[0.]*15,'weekly_features':[0.]*8,
        'outcomes':{'10':{'return_pct':ret,'exit_date':(day+timedelta(days=10)).isoformat()}}}


def test_library_samples_every_ten_bars_only():
    refs=[row(i) for i in range(1200)]
    library,manifest=fit_library(refs)
    assert manifest['references']==120
    assert [r['index'] for r in library['references']]==list(range(200,1400,10))
    assert library['x'].shape==(120,12)
    none,status=fit_library(refs[:500])
    assert none is None and status['status']=='insufficient_reference_library'


def test_exact_neighbor_votes_and_query_labels_ignored():
    train=[row() for _ in range(100)]
    scaler=RobustScaler().fit(matrix(train))
    x=np.zeros((100,12));x[25:]=10
    library={'scaler':scaler,'x':x,'y':np.array([1.]*25+[0.]*75),'weights':np.ones(100)}
    query=[row()]
    p=probabilities(query,library)
    assert np.isclose(p['analog25'][0],26/27)
    assert np.isclose(p['analog50'][0],.5)
    assert np.isclose(p['analog100'][0],26/102)
    changed=copy.deepcopy(query);changed[0]['outcomes']['10']['return_pct']=-100
    after=probabilities(changed,library)
    for k in p:assert np.array_equal(p[k],after[k])


def test_split_purges_boundaries_retains_flat_selection_outcomes():
    rs=[row(day=d,ret=r) for d,r in [('2021-01-01',1),('2021-12-28',1),('2021-02-01',0),
        ('2022-03-01',0),('2022-12-28',1),('2023-04-01',0),('2023-12-28',1),('2024-01-01',1)]]
    g=split(rs,2024)
    assert [r['date'] for r in g['train']]==['2021-01-01']
    assert [r['date'] for r in g['calibration']]==['2022-03-01']
    assert [r['date'] for r in g['validation']]==['2023-04-01']
    assert [r['date'] for r in g['test']]==['2024-01-01']


def test_confirmation_rejects_without_searching_new_threshold():
    rows=[row(i,1 if i%2 else -1) for i in range(200)]
    selection={'model':'analog25','threshold':.7,'status':'active'}
    good=np.array([.8 if i%2 else .2 for i in range(200)])
    assert confirm(rows,{'analog25':good},selection)['status']=='active'
    failed=confirm(rows,{'analog25':1-good},selection)
    assert failed['status']=='confirmation_gate_failed'
    assert failed['threshold'] is None and failed['proposed_threshold']==.7
    assert selection['threshold']==.7


def test_no_library_no_invented_probability():
    output=forecast([row()],None,{'model':None,'threshold':None,'status':'no_validation'})
    assert output[0]['forecasts']['selected']=={'p_up':None,'bias':'WAIT'}
