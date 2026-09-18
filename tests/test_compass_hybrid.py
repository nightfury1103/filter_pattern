import copy
from datetime import date,timedelta

import numpy as np

from filter_pattern.compass_hybrid import join_features,rule,split,fit,predict


def row(day='2024-01-01',ret=1.):
    return {'date':day,'index':100,'features':[0.,0.,1.,0.,.5,1.,0.,.3,1.,.5,.5,1.,1.,0.,.5],
        'rrg_features':[1.,-2.,0.,0.,.1,0.,1.,1.,-2.], 'close':100.,'extension_atr':.5,
        'outcomes':{'10':{'return_pct':ret,'exit_date':(date.fromisoformat(day)+timedelta(days=10)).isoformat()}},
        'forecasts':{}}


def test_price_and_rrg_rule_dont_turn_weakening_into_short():
    r=row()
    assert rule(r)=='LONG'
    assert rule(r,True)=='LONG' # negative RRG Y is not a short instruction
    r['rrg_features'][0]=-1;r['rrg_features'][4]=-.1
    assert rule(r,True)=='WAIT'
    r['rrg_features'][4]=.1
    assert rule(r,True)=='LONG'
    r['features'][4]=2.01
    assert rule(r)=='WAIT'
    r['features'][4]=.5;r['features'][7]=.19
    assert rule(r)=='WAIT'
    r=row();r['features'][2]=-1;r['features'][5]=-1;r['rrg_features'][0]=-1
    assert rule(r,True)=='SHORT'


def test_self_benchmark_rrg_cannot_create_confirming_signal():
    r=row();r['rrg_features']=[0.]*9
    assert rule(r)=='LONG'
    assert rule(r,True)=='WAIT'


def test_rrg_features_causal_no_forward_fill():
    points=[{'date':f'2024-01-{i:02d}','x':100+i,'y':101.,'price':100.} for i in range(1,9)]
    rows=[row(f'2024-01-{i:02d}') for i in range(1,10)]
    full=join_features(rows,points)
    assert [r['date'] for r in full]==['2024-01-06','2024-01-07','2024-01-08']
    prefix=join_features(rows[:6],points[:6])
    assert prefix[0]==full[0]
    changed=copy.deepcopy(points);changed[-1]['x']=999
    assert join_features(rows,changed)[0]==full[0]
    assert full[0]['rrg_features'][4]==5


def test_split_purges_boundaries_flat_labels_and_keeps_pending_test():
    rows=[row('2022-12-01'),row('2022-12-28'),row('2023-06-01'),row('2023-12-28'),row('2023-06-02',0),row('2024-01-01')]
    rows[-1]['outcomes']={}
    g=split(rows,2024)
    assert [r['date'] for r in g['train']]==['2022-12-01']
    assert [r['date'] for r in g['calibration']]==['2023-06-01']
    assert g['test'][0]['outcomes']=={}
    models,manifest=fit(g)
    assert models=={} and manifest['status']=='insufficient_train'
    assert predict(g['test'],models)[0]['forecasts']['hybrid_tree2']=={'p_up':None,'bias':'WAIT'}


def test_test_outcomes_do_not_affect_models_or_predictions():
    from threadpoolctl import threadpool_limits
    rng=np.random.default_rng(17)
    def build(start,n):
        rows=[]
        for i in range(n):
            r=row((date.fromisoformat(start)+timedelta(days=i)).isoformat(),1. if i%3 else -1.)
            r['features']=rng.normal(size=15).tolist();r['rrg_features']=rng.normal(size=9).tolist()
            rows.append(r)
        return rows
    g={'train':build('2021-01-01',210),'calibration':build('2022-01-01',130),'test':build('2023-01-01',8)}
    with threadpool_limits(limits=2):
        models,manifest=fit(g)
        predicted=predict(g['test'],models)
        altered=copy.deepcopy(g)
        for r in altered['test']: r['outcomes']['10']['return_pct']*=-1
        changed,other_manifest=fit(altered)
        other=predict(altered['test'],changed)
    assert manifest==other_manifest
    assert [r['forecasts'] for r in predicted]==[r['forecasts'] for r in other]


def test_report_escapes_embedded_script(tmp_path):
    from filter_pattern.compass_hybrid_report import write_report
    p=tmp_path/'index.html'
    write_report({'hostile':'</script><script>alert(1)</script>'},p)
    html=p.read_text(encoding='utf-8')
    assert '</script><script>alert(1)' not in html
    assert '\\u003c/script>' in html
