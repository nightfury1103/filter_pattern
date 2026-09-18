"""Bounded, offline price-state + actual RRG experiment; never a live gate."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path

from .compass import calculate_compass_series
from .compass_context_data import validate_source
from .compass_exact import new_candidate, GROUPS
from .compass_forecast import (feature_rows, label_rows, bias_from_probability,
    summarize, probability_diagnostics, stability_summary)
from .compass_research import load_research_data
from .rrg_comparison import (SOURCES, normalize_points, make_signals, signed_bias,
    paired_comparison, quick)
from .rrg_dashboard import _series_from_fialda, _series_from_stockcharts

ML = ('price_logistic', 'hybrid_logistic', 'price_tree2', 'hybrid_tree2')
NAMES = {'price_rule':'Quy tắc trạng thái giá', 'hybrid_rule':'Trạng thái giá + RRG',
    **{m:('Giá + RRG' if m.startswith('hybrid') else 'Chỉ giá')+' / '+m.split('_')[1]+' / 75%' for m in ML},
    **{m+'_direction':('Giá + RRG' if m.startswith('hybrid') else 'Chỉ giá')+' / '+m.split('_')[1]+' / hướng mỗi ngày' for m in ML},
    'rrg_x':'RRG trục X', 'rrg_y':'RRG trục Y', 'ema':'EMA', 'always_long':'Luôn Long'}
PROTOCOL = {'version':'hybrid-1','years':[2024,2025,2026], 'horizon':10, 'threshold':.75,
    'split':'train before Y-1; sigmoid calibrate Y-1; test Y; purge 10-bar labels crossing each boundary',
    'minimum_train':200,'minimum_calibration':120,'candidates':['logistic','tree2'],
    'selection':'None: all four fixed ablation models reported; no test tuning',
    'rules':'price trend and return20 aligned; efficiency20>=.2; abs(EMA20 extension)<=2 ATR; hybrid additionally RRG X or dX5 aligned; constant self-benchmark WAIT',
    'rrg_features':['x-100','y-100','dx1','dy1','dx5','dy5','calendar_gap','x_times_trend','y_times_trend'],
    'reuse':'Retrospective, already inspected 2024-2026; no untouched or prospective validation',
    'evidence':'coverage>=10%, >=100 fixed-schedule signals, block CI95 lower>=75%; never auto-promote',
    'timing':'same-date completed own price and provider daily RRG; missing dates never filled; provider retrospective revision possible'}


def join_features(price_rows: list[dict], points: list[dict], scale: float = 1.) -> list[dict]:
    """Build RRG differences causally; five provider observations, not five crypto bars."""
    lookup = {}
    signals = make_signals(points)
    for i in range(5,len(points)):
        p, prev, old = points[i], points[i-1], points[i-5]
        lookup[p['date']] = (p, [p['x']-100,p['y']-100,p['x']-prev['x'],p['y']-prev['y'],
            p['x']-old['x'],p['y']-old['y'],(date.fromisoformat(p['date'])-date.fromisoformat(prev['date'])).days])
    rows=[]
    for r in price_rows:
        if r['date'] not in lookup:
            continue
        p, features = lookup[r['date']]
        trend=r['features'][5]
        ext=features+[features[0]*trend,features[1]*trend]
        diff=abs(p['price']*scale/r['close']-1) if p['price'] is not None else None
        rows.append({**r,'rrg_features':ext,'rrg':p,'rrg_price_difference':diff,
            'forecasts':{m:{'bias':signals[r['date']][m]} for m in ('rrg_x','rrg_y')}})
    return rows


def rule(row: dict, hybrid: bool = False) -> str:
    f=row['features']
    if f[7]<.2 or abs(f[4])>2:
        return 'WAIT'
    direction=1 if f[5]>0 and f[2]>0 else -1 if f[5]<0 and f[2]<0 else 0
    if not direction:
        return 'WAIT'
    r=row['rrg_features']
    if hybrid and not (r[0]*direction>0 or r[4]*direction>0):
        return 'WAIT'
    return 'LONG' if direction>0 else 'SHORT'


def split(rows: list[dict], year: int) -> dict[str,list[dict]]:
    cal,start,end=f'{year-1}-01-01',f'{year}-01-01',f'{year+1}-01-01'
    groups={'train':[],'calibration':[],'test':[]}
    for r in rows:
        if start<=r['date']<end:
            groups['test'].append(r)
            continue
        outcome=r['outcomes'].get('10')
        if not outcome or outcome['return_pct']==0:
            continue
        if r['date']<cal and outcome['exit_date']<cal:
            groups['train'].append(r)
        elif cal<=r['date']<start and outcome['exit_date']<start:
            groups['calibration'].append(r)
    return groups


def matrix(rows: list[dict], hybrid: bool):
    import numpy as np
    return np.array([r['features']+(r['rrg_features'] if hybrid else []) for r in rows],dtype=float)


def fit(groups: dict) -> tuple[dict,dict]:
    from sklearn.linear_model import LogisticRegression
    manifest={k:{'rows':len(groups[k]),'first':min((r['date'] for r in groups[k]),default=None),
        'last':max((r['date'] for r in groups[k]),default=None),
        'last_label_exit':max((r['outcomes']['10']['exit_date'] for r in groups[k]),default=None)} for k in ('train','calibration')}
    for k,minimum in [('train',200),('calibration',120)]:
        if len(groups[k])<minimum or len({r['outcomes']['10']['return_pct']>0 for r in groups[k]})<2:
            return {},{**manifest,'status':'insufficient_'+k}
    models={}
    for m in ML:
        hybrid=m.startswith('hybrid')
        model=new_candidate(m.split('_')[1])
        model.fit(matrix(groups['train'],hybrid),[r['outcomes']['10']['return_pct']>0 for r in groups['train']])
        calibrator=LogisticRegression(C=1.,max_iter=2000)
        calibrator.fit(model.decision_function(matrix(groups['calibration'],hybrid)).reshape(-1,1),
            [r['outcomes']['10']['return_pct']>0 for r in groups['calibration']])
        models[m]=(model,calibrator)
        manifest[m]={'calibration_slope':float(calibrator.coef_[0,0])}
    return models,{**manifest,'status':'fitted'}


def predict(rows: list[dict], models: dict) -> list[dict]:
    values={}
    for m,(model,cal) in models.items():
        if rows:
            values[m]=cal.predict_proba(model.decision_function(matrix(rows,m.startswith('hybrid'))).reshape(-1,1))[:,1]
    result=[]
    for i,r in enumerate(rows):
        forecasts={**r['forecasts'],'price_rule':{'bias':rule(r)},'hybrid_rule':{'bias':rule(r,True)}}
        for m in ML:
            p=float(values[m][i]) if m in values else None
            forecasts[m]={'p_up':p,'bias':bias_from_probability(p) if p is not None else 'WAIT'}
            forecasts[m+'_direction']={'bias':signed_bias(p,.5) if p is not None else 'WAIT'}
        result.append({**r,'forecasts':forecasts})
    return result


def run(cache: Path,sources: Path,out: Path,before: str) -> dict:
    import joblib
    from threadpoolctl import threadpool_limits
    from importlib.metadata import version
    out.mkdir(parents=True,exist_ok=True)
    protocol=json.dumps(PROTOCOL,ensure_ascii=False,indent=2,sort_keys=True)
    (out/'protocol.json').write_text(protocol,encoding='utf-8')
    data,metadata,errors=load_research_data(out,cache_path=cache,before=date.fromisoformat(before))
    payload={'generated_at':datetime.now(timezone.utc).isoformat(),'before':before,'protocol':PROTOCOL,
        'protocol_sha256':hashlib.sha256(protocol.encode()).hexdigest(),'groups':GROUPS,'models':NAMES,
        'assets':{},'errors':{},'input_sha256':{str(cache):hashlib.sha256(cache.read_bytes()).hexdigest()},
        'versions':{p:version(p) for p in ('numpy','scikit-learn','scipy')},
        'implementation_sha256':{n:hashlib.sha256(Path(__file__).with_name(n).read_bytes()).hexdigest() for n in
            ('compass_hybrid.py','compass_forecast.py','compass_exact.py','rrg_comparison.py')}}
    saved={}
    for symbol,(filename,code,benchmark) in SOURCES.items():
        if symbol not in data:
            payload['errors'][symbol]=errors.get(symbol,'Missing validated exact-symbol OHLC')
            continue
        path=sources/f'{filename}-raw.json'
        if not path.exists():
            payload['errors'][symbol]='Missing actual RRG source history'
            continue
        audit=validate_source(data[symbol])
        raw=json.loads(path.read_text(encoding='utf-8'))
        parser=_series_from_fialda if filename=='fialda' else _series_from_stockcharts
        points=normalize_points(parser(raw,[code]).get(code,[]),before)
        payload['input_sha256'][str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
        base=label_rows(data[symbol],feature_rows(data[symbol]))
        rows=join_features(base,points,1000 if filename=='fialda' else 1)
        history,folds=[],{}
        ema=calculate_compass_series(data[symbol])['ema']
        for year in PROTOCOL['years']:
            groups=split(rows,year)
            print(f'{symbol}/{year}: train={len(groups["train"])}, calibration={len(groups["calibration"])}, test={len(groups["test"])}',flush=True)
            with threadpool_limits(limits=2):
                models,folds[str(year)]=fit(groups)
                history.extend(predict(groups['test'],models))
            saved[f'{symbol}/{year}']=models
        for r in history:
            r['forecasts']['ema']={'bias':ema[r['index']]['bias']}
            r['forecasts']['always_long']={'bias':'LONG'}
        matched=[r for r in history if all(r['forecasts'][m]['p_up'] is not None for m in ML)]
        print(f'Evaluate {symbol}: matched ML dates={len(matched)}',flush=True)
        summaries={m:{str(h):{side:summarize(matched,m,side,h) for side in (('ALL','LONG','SHORT') if h==10 else ('ALL',))} for h in (5,10,20)} for m in NAMES}
        clean=[r for r in matched if r['rrg_price_difference'] is not None and r['rrg_price_difference']<=.01]
        pairs=[('hybrid_rule','price_rule'),('hybrid_rule','rrg_y'),('hybrid_rule','always_long')]
        for name in ('logistic','tree2'):
            for suffix in ('','_direction'):
                pairs.extend([(f'hybrid_{name}{suffix}',f'price_{name}{suffix}'),(f'hybrid_{name}{suffix}','rrg_y'),(f'hybrid_{name}{suffix}','always_long')])
        payload['assets'][symbol]={'benchmark':benchmark,'metadata':metadata[symbol],'audit':audit,'folds':folds,
            'history':[{k:v for k,v in r.items() if k not in ('features','rrg_features')} for r in history],
            'matched_dates':{'first':matched[0]['date'] if matched else None,'last':matched[-1]['date'] if matched else None,'count':len(matched)},
            'summaries':summaries,'rule_full_period':{m:{str(h):quick(history,m,h) for h in (5,10,20)} for m in ('price_rule','hybrid_rule','rrg_x','rrg_y','ema','always_long')},
            'yearly':{str(y):{m:quick([r for r in matched if r['date'].startswith(str(y))],m) for m in NAMES} for y in PROTOCOL['years']},
            'diagnostics':{m:probability_diagnostics(matched,m) for m in ML},
            'stability':{m:stability_summary(matched,m) for m in NAMES},
            'price_clean_sensitivity':{m:quick(clean,m) for m in NAMES},
            'paired':[paired_comparison(matched,a,b) for a,b in pairs]}
    joblib.dump(saved,out/'research-models.joblib')
    (out/'results.json').write_text(json.dumps(payload,ensure_ascii=False,allow_nan=False),encoding='utf-8')
    from .compass_hybrid_report import write_report
    write_report(payload,out/'index.html')
    return payload


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache',type=Path,default=Path('reports/compass-exact-d1/candles.json'))
    parser.add_argument('--sources',type=Path,default=Path('reports/rrg-comparison-d1'))
    parser.add_argument('--out',type=Path,default=Path('reports/compass-hybrid-d1'))
    parser.add_argument('--before',default='2026-09-17')
    a=parser.parse_args()
    run(a.cache,a.sources,a.out,a.before)


if __name__=='__main__':
    main()
