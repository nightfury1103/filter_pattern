"""One shared D1/closed-week compass for the exact screenshot roster."""
from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import math
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path

from .compass import _ema, _atr, efficiency_ratio, calculate_compass_series
from .models import Candle
from .compass_exact import GROUPS, SYMBOLS
from .compass_context_data import validate_source
from .compass_forecast import feature_rows, label_rows, summarize, probability_diagnostics, stability_summary, bias_from_probability
from .compass_research import load_research_data
from .rrg_comparison import quick, paired_comparison, signed_bias

CANDIDATES=('daily','weekly','forest')
NAMES={'selected':'La bàn chung: chọn bằng validation',
    **{m:n+' / 75%' for m,n in [('daily','Cây D1'),('weekly','Cây D1 + tuần đóng'),('forest','Rừng D1 + tuần đóng')]},
    **{m+'_direction':n+' / hướng mỗi ngày' for m,n in [('daily','Cây D1'),('weekly','Cây D1 + tuần đóng'),('forest','Rừng D1 + tuần đóng')]},
    'ema':'EMA','always_long':'Luôn Long'}
PROTOCOL={'version':'shared-1','symbols':SYMBOLS,'years':[2024,2025,2026],'horizon':10,
    'candidates':CANDIDATES,'threshold_grid':[.55,.60,.65,.70,.75,.80,.85],
    'selection':'One global model: minimum weighted validation Brier; choose highest-coverage threshold satisfying validation gate. No refit after validation.',
    'gate':'weighted accuracy>=.75, weighted coverage>=.10, >=100 signal rows, >=20 Long and >=20 Short; otherwise WAIT all test year',
    'split':'Train before Y-2; sigmoid calibrate Y-2; validate Y-1; test Y; purge labels across every boundary',
    'weekly':'Only ISO weeks strictly earlier than signal week; no partial week or future weekly close',
    'weights':'Equal exposure total per instrument; US500 and SPY half each. No symbol features or symbol-specific thresholds.',
    'reuse':'Previously inspected retrospective 2024-2026; not untouched validation or live readiness',
    'evidence':'same existing coverage/sample/CI criteria; all-seven coverage required; never auto-promote'}


def closed_week_features(candles: list[Candle]) -> tuple[list[date],list[list[float] | None]]:
    weeks={}
    for c in candles:
        d=c.datetime.date(); monday=date.fromisocalendar(d.isocalendar().year,d.isocalendar().week,1)
        weeks.setdefault(monday,[]).append(c)
    keys=sorted(weeks)
    bars=[]
    for k in keys:
        rows=weeks[k]
        bars.append(Candle(datetime.combine(k,datetime.min.time()),rows[0].open,max(c.high for c in rows),
            min(c.low for c in rows),rows[-1].close,sum(c.volume for c in rows)))
    prices=[c.close for c in bars]; e4,e10,atr=_ema(prices,4),_ema(prices,10),_atr(bars)
    trend=[(a-b)/max(float(v or 0),p*1e-8) for a,b,v,p in zip(e4,e10,atr,prices)]
    result=[]
    for i,c in enumerate(bars):
        if i<26:
            result.append(None);continue
        scale=max(float(atr[i] or 0),c.close*1e-8)
        lo=min(b.low for b in bars[i-12:i+1]);hi=max(b.high for b in bars[i-12:i+1])
        result.append([(c.close-prices[i-h])/(scale*math.sqrt(h)) for h in (1,4,13)]+[
            trend[i],trend[i]-trend[i-2],efficiency_ratio(prices[i-13:i+1]),
            (c.close-lo)/(hi-lo) if hi>lo else .5,(c.close-e4[i])/scale])
    return keys,result


def prepare(candles: list[Candle],symbol: str) -> list[dict]:
    keys,weekly=closed_week_features(candles)
    result=[]
    for row in label_rows(candles,feature_rows(candles)):
        day=date.fromisoformat(row['date'])
        monday=date.fromisocalendar(day.isocalendar().year,day.isocalendar().week,1)
        i=bisect.bisect_left(keys,monday)-1
        if i<0 or weekly[i] is None:
            continue
        result.append({**row,'symbol':symbol,'weekly_features':weekly[i],'weekly_start':keys[i].isoformat()})
    return result


def weights(rows: list[dict]):
    import numpy as np
    counts=Counter(r['symbol'] for r in rows)
    w=np.array([(.5 if r['symbol'] in ('US500','SPY') else 1.)/counts[r['symbol']] for r in rows])
    return w*len(w)/w.sum() if len(w) else w


def split(rows: list[dict],year: int):
    cal,val,test,end=(f'{y}-01-01' for y in (year-2,year-1,year,year+1))
    groups={k:[] for k in ('train','calibration','validation','test')}
    for r in rows:
        if test<=r['date']<end:
            groups['test'].append(r);continue
        outcome=r['outcomes'].get('10')
        if not outcome:
            continue
        if val<=r['date']<test and outcome['exit_date']<test:
            groups['validation'].append(r) # Flat outcomes incorrect, retained in selection.
        elif outcome['return_pct']!=0:
            if r['date']<cal and outcome['exit_date']<cal: groups['train'].append(r)
            elif cal<=r['date']<val and outcome['exit_date']<val: groups['calibration'].append(r)
    return groups


def matrix(rows,weekly):
    import numpy as np
    return np.array([r['features']+(r['weekly_features'] if weekly else []) for r in rows],dtype=float)


def fit(groups):
    from sklearn.ensemble import HistGradientBoostingClassifier,RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    models={}
    manifest={k:{'rows':len(groups[k]),'symbols':dict(Counter(r['symbol'] for r in groups[k])),
        'first':min((r['date'] for r in groups[k]),default=None),'last':max((r['date'] for r in groups[k]),default=None),
        'last_label_exit':max((r['outcomes']['10']['exit_date'] for r in groups[k]),default=None)} for k in ('train','calibration','validation')}
    for k in ('train','calibration'):
        if len(groups[k])<500 or len({r['outcomes']['10']['return_pct']>0 for r in groups[k]})<2:
            return {},{**manifest,'status':'insufficient_'+k}
    for name in CANDIDATES:
        model=RandomForestClassifier(n_estimators=200,max_depth=8,min_samples_leaf=50,max_features=.7,random_state=17,n_jobs=2) if name=='forest' else HistGradientBoostingClassifier(max_depth=4,max_leaf_nodes=16,max_iter=150,learning_rate=.04,min_samples_leaf=100,l2_regularization=20.,early_stopping=False,random_state=17)
        model.fit(matrix(groups['train'],name!='daily'),[r['outcomes']['10']['return_pct']>0 for r in groups['train']],sample_weight=weights(groups['train']))
        calibrator=LogisticRegression(C=1.,max_iter=2000)
        calibrator.fit(raw_score(model,matrix(groups['calibration'],name!='daily')),
            [r['outcomes']['10']['return_pct']>0 for r in groups['calibration']],sample_weight=weights(groups['calibration']))
        models[name]=(model,calibrator)
        manifest[name]={'calibration_slope':float(calibrator.coef_[0,0])}
    return models,{**manifest,'status':'fitted'}


def raw_score(model,x):
    import numpy as np
    p=np.clip(model.predict_proba(x)[:,1],1e-6,1-1e-6)
    return np.log(p/(1-p)).reshape(-1,1)


def probabilities(rows,models):
    if not rows:return {}
    return {name:cal.predict_proba(raw_score(model,matrix(rows,name!='daily')))[:,1] for name,(model,cal) in models.items()}


def choose(rows,ps):
    import numpy as np
    if not rows or not ps:return {'model':None,'threshold':None,'status':'no_validation','trials':[]}
    w=weights(rows);y=np.array([r['outcomes']['10']['return_pct']>0 for r in rows])
    rets=np.array([r['outcomes']['10']['return_pct'] for r in rows])
    scores={m:float(np.average((p-y)**2,weights=w)) for m,p in ps.items()}
    winner=min(scores,key=scores.get);p=ps[winner];trials=[]
    for t in PROTOCOL['threshold_grid']:
        long=p>=t;short=p<=1-t;selected=long|short;count=int(selected.sum())
        accuracy=float(np.average(((rets>0)&long)|((rets<0)&short),weights=w*selected)) if count else None
        coverage=float(w[selected].sum()/w.sum())
        passed=count>=100 and int(long.sum())>=20 and int(short.sum())>=20 and coverage>=.1 and accuracy>=.75
        trials.append({'threshold':t,'signals':count,'long':int(long.sum()),'short':int(short.sum()),'accuracy':accuracy,'coverage':coverage,'passed':bool(passed)})
    passing=[r for r in trials if r['passed']]
    best=max(passing,key=lambda r:r['coverage']) if passing else None
    return {'model':winner,'threshold':best['threshold'] if best else None,'status':'active' if best else 'validation_gate_failed','brier':scores,'trials':trials}


def forecast(rows,models,selection):
    ps=probabilities(rows,models);result=[]
    for i,r in enumerate(rows):
        forecasts={}
        for m in CANDIDATES:
            p=float(ps[m][i]) if m in ps else None
            forecasts[m]={'p_up':p,'bias':bias_from_probability(p) if p is not None else 'WAIT'}
            forecasts[m+'_direction']={'bias':signed_bias(p,.5) if p is not None else 'WAIT'}
        chosen=selection['model'];p=forecasts[chosen]['p_up'] if chosen else None
        threshold=selection['threshold']
        forecasts['selected']={'p_up':p,'bias':bias_from_probability(p,threshold) if threshold is not None and p is not None else 'WAIT'}
        result.append({**r,'forecasts':forecasts,'selected_model':chosen,'selected_threshold':threshold,'gate_status':selection['status']})
    return result


def run(cache:Path,out:Path,before:str):
    import joblib
    from threadpoolctl import threadpool_limits
    out.mkdir(parents=True,exist_ok=True)
    (out/'protocol.json').write_text(json.dumps(PROTOCOL,ensure_ascii=False,indent=2),encoding='utf-8')
    data,metadata,errors=load_research_data(out,cache_path=cache,before=date.fromisoformat(before))
    rows=[]
    for s in SYMBOLS:
        if s not in data:continue
        validate_source(data[s]);rows.extend(prepare(data[s],s))
    history={s:[] for s in SYMBOLS if s in data};folds={};saved={}
    for year in PROTOCOL['years']:
        g=split(rows,year)
        print(f'Shared/{year}: '+str({k:len(v) for k,v in g.items()}),flush=True)
        with threadpool_limits(limits=2):
            models,manifest=fit(g)
            selection=choose(g['validation'],probabilities(g['validation'],models))
            predicted=forecast(g['test'],models,selection)
        folds[str(year)]={**manifest,'selection':selection};saved[str(year)]=models
        print(f'Selected {selection["model"]}, threshold={selection["threshold"]}, status={selection["status"]}',flush=True)
        for r in predicted:history[r['symbol']].append(r)
    payload={'generated_at':datetime.now(timezone.utc).isoformat(),'before':before,'protocol':PROTOCOL,'groups':GROUPS,
        'models':NAMES,'chart_models':{'selected':'La bàn chung được chọn','daily':'Chẩn đoán: cây D1','weekly':'Chẩn đoán: cây D1 + tuần','forest':'Chẩn đoán: rừng D1 + tuần'},
        'title':'La bàn chung D1 cho bảy mã','shared_folds':folds,'assets':{},
        'errors':{s:errors.get(s,'Missing validated exact-symbol D1 history') for s in SYMBOLS if s not in data},
        'hashes':{str(cache):hashlib.sha256(cache.read_bytes()).hexdigest(),__file__:hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}}
    for s,rs in history.items():
        ema=calculate_compass_series(data[s])['ema']
        for r in rs:r['forecasts'].update(ema={'bias':ema[r['index']]['bias']},always_long={'bias':'LONG'})
        matched=[r for r in rs if r['forecasts']['daily']['p_up'] is not None]
        print(f'Evaluate shared {s}',flush=True)
        summaries={m:{str(h):{side:summarize(matched,m,side,h) for side in (('ALL','LONG','SHORT') if h==10 else ('ALL',))} for h in (5,10,20)} for m in NAMES}
        pairs=[('weekly_direction','daily_direction'),('forest_direction','daily_direction'),('selected','always_long'),('selected','ema')]
        payload['assets'][s]={'metadata':metadata[s],'benchmark':'không dùng benchmark/RRG','folds':folds,
            'history':[{k:v for k,v in r.items() if k not in ('features','weekly_features')} for r in rs],
            'matched_dates':{'first':matched[0]['date'] if matched else None,'last':matched[-1]['date'] if matched else None,'count':len(matched)},
            'summaries':summaries,'rule_full_period':{},
            'yearly':{str(y):{m:quick([r for r in matched if r['date'].startswith(str(y))],m) for m in NAMES} for y in PROTOCOL['years']},
            'diagnostics':{m:probability_diagnostics(matched,m) for m in CANDIDATES},
            'stability':{m:stability_summary(matched,m) for m in NAMES},
            'price_clean_sensitivity':{m:quick(matched,m) for m in NAMES},
            'paired':[paired_comparison(matched,a,b) for a,b in pairs]}
    joblib.dump(saved,out/'research-models.joblib')
    (out/'results.json').write_text(json.dumps(payload,ensure_ascii=False,allow_nan=False),encoding='utf-8')
    from .compass_shared_report import write_report
    write_report(payload,out/'index.html')
    return payload


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cache',type=Path,default=Path('reports/compass-exact-d1/candles.json'))
    p.add_argument('--out',type=Path,default=Path('reports/compass-shared-d1'))
    p.add_argument('--before',default='2026-09-17')
    a=p.parse_args();run(a.cache,a.out,a.before)


if __name__=='__main__':main()
