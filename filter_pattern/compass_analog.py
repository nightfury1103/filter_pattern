"""Shared analog-state research with purged selection and confirmation years."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date,datetime,timezone
from pathlib import Path

from .compass import WARMUP,calculate_compass_series
from .compass_exact import GROUPS,SYMBOLS
from .compass_context_data import validate_source
from .compass_shared import prepare,weights,choose
from .compass_forecast import summarize,probability_diagnostics,stability_summary,bias_from_probability
from .compass_research import load_research_data
from .rrg_comparison import quick,paired_comparison,signed_bias

KS={'analog25':25,'analog50':50,'analog100':100}
DAILY=(2,3,4,5,6,7,8,9,10)
WEEKLY=(3,4,6)
NAMES={'selected':'La bàn analog: qua chọn và xác nhận',
    **{m:f'{k} giai đoạn tương tự / 75%' for m,k in KS.items()},
    **{m+'_direction':f'{k} giai đoạn tương tự / hướng mỗi ngày' for m,k in KS.items()},
    'ema':'EMA','always_long':'Luôn Long'}
PROTOCOL={'version':'analog-1','symbols':SYMBOLS,'years':[2024,2025,2026],'horizon':10,
    'neighbors':KS,'daily_features':DAILY,'weekly_features':WEEKLY,'scaler':'Train-library RobustScaler median/IQR; clip at +/-5',
    'sampling':'(index-WARMUP)%10==0; reference outcomes must finish before selection year',
    'vote':'Exposure weights normalized to K; Laplace smoothing (weighted up+1)/(K+2); not calibrated probability',
    'timing':'Library before Y-2; select in Y-2; confirm frozen K/threshold in Y-1; test Y; purged labels; no refit',
    'gate':'75% weighted accuracy, 10% weighted coverage, >=100 signals, >=20 Long and >=20 Short in both selection and confirmation',
    'threshold_grid':[.55,.60,.65,.70,.75,.80,.85],
    'reuse':'All 2024-2026 already inspected; retrospective only, not fresh holdout; no live promotion'}


def split(rows,year):
    selection,confirmation,test,end=(f'{y}-01-01' for y in (year-2,year-1,year,year+1))
    groups={k:[] for k in ('train','calibration','validation','test')}
    for r in rows:
        if test<=r['date']<end:groups['test'].append(r);continue
        label=r['outcomes'].get('10')
        if not label:continue
        if r['date']<selection and label['exit_date']<selection and label['return_pct']!=0:groups['train'].append(r)
        elif selection<=r['date']<confirmation and label['exit_date']<confirmation:groups['calibration'].append(r)
        elif confirmation<=r['date']<test and label['exit_date']<test:groups['validation'].append(r)
    return groups


def matrix(rows):
    import numpy as np
    return np.array([[r['features'][i] for i in DAILY]+[r['weekly_features'][i] for i in WEEKLY] for r in rows],dtype=float)


def fit_library(train):
    import numpy as np
    from sklearn.preprocessing import RobustScaler
    references=sorted([r for r in train if (r['index']-WARMUP)%10==0],key=lambda r:(r['date'],r['symbol']))
    if len(references)<max(KS.values()):return None,{'status':'insufficient_reference_library','references':len(references)}
    scaler=RobustScaler().fit(matrix(references))
    x=np.clip(scaler.transform(matrix(references)),-5,5)
    artifact={'scaler':scaler,'x':x,'y':np.array([r['outcomes']['10']['return_pct']>0 for r in references],dtype=float),
        'weights':weights(references),'references':[{'symbol':r['symbol'],'date':r['date'],'index':r['index'],
            'exit_date':r['outcomes']['10']['exit_date'],'return_pct':r['outcomes']['10']['return_pct']} for r in references]}
    return artifact,{'status':'fitted','references':len(references),'first':references[0]['date'],'last':references[-1]['date'],
        'last_label_exit':max(r['outcomes']['10']['exit_date'] for r in references)}


def probabilities(rows,library):
    import numpy as np
    if not rows or library is None:return {}
    x=np.clip(library['scaler'].transform(matrix(rows)),-5,5)
    output={m:[] for m in KS}
    # Stable sorting yields deterministic ties; small frozen libraries allow exact search.
    for start in range(0,len(rows),256):
        query=x[start:start+256]
        d=((query[:,None,:]-library['x'][None,:,:])**2).sum(axis=2)
        order=np.argsort(d,axis=1,kind='stable')[:,:max(KS.values())]
        for m,k in KS.items():
            neighbors=order[:,:k];w=library['weights'][neighbors]
            up=(w*library['y'][neighbors]).sum(axis=1)/w.sum(axis=1)
            output[m].extend(((up*k+1)/(k+2)).tolist())
    return {m:np.array(p) for m,p in output.items()}


def confirm(rows,ps,selection):
    import numpy as np
    if selection['threshold'] is None:return {**selection,'confirmation':None,'status':'selection_gate_failed'}
    p=ps[selection['model']];t=selection['threshold'];w=weights(rows)
    long=p>=t;short=p<=1-t;chosen=long|short
    ret=np.array([r['outcomes']['10']['return_pct'] for r in rows])
    n=int(chosen.sum());coverage=float(w[chosen].sum()/w.sum()) if len(w) else 0.
    accuracy=float(np.average(((ret>0)&long)|((ret<0)&short),weights=w*chosen)) if n else None
    passed=n>=100 and int(long.sum())>=20 and int(short.sum())>=20 and coverage>=.1 and accuracy>=.75
    return {**selection,'proposed_threshold':t,'threshold':t if passed else None,
        'status':'active' if passed else 'confirmation_gate_failed',
        'confirmation':{'signals':n,'long':int(long.sum()),'short':int(short.sum()),'accuracy':accuracy,'coverage':coverage,'passed':bool(passed)}}


def forecast(rows,library,selection):
    ps=probabilities(rows,library);out=[]
    for i,r in enumerate(rows):
        predictions={}
        for m in KS:
            p=float(ps[m][i]) if m in ps else None
            predictions[m]={'p_up':p,'bias':bias_from_probability(p) if p is not None else 'WAIT'}
            predictions[m+'_direction']={'bias':signed_bias(p,.5) if p is not None else 'WAIT'}
        m=selection['model'];p=predictions[m]['p_up'] if m else None;t=selection['threshold']
        predictions['selected']={'p_up':p,'bias':bias_from_probability(p,t) if p is not None and t is not None else 'WAIT'}
        out.append({**r,'forecasts':predictions,'selected_model':m,'selected_threshold':t,'gate_status':selection['status']})
    return out


def run(cache,out,before):
    import joblib
    out.mkdir(parents=True,exist_ok=True)
    (out/'protocol.json').write_text(json.dumps(PROTOCOL,ensure_ascii=False,indent=2),encoding='utf-8')
    data,metadata,errors=load_research_data(out,cache_path=cache,before=date.fromisoformat(before))
    rows=[]
    for symbol in SYMBOLS:
        if symbol in data:validate_source(data[symbol]);rows.extend(prepare(data[symbol],symbol))
    history={s:[] for s in SYMBOLS if s in data};folds={};libraries={}
    for year in PROTOCOL['years']:
        groups=split(rows,year)
        library,manifest=fit_library(groups['train'])
        selection=choose(groups['calibration'],probabilities(groups['calibration'],library))
        selection=confirm(groups['validation'],probabilities(groups['validation'],library),selection)
        predicted=forecast(groups['test'],library,selection)
        stages={stage:{'rows':len(groups[stage]),'first':min((r['date'] for r in groups[stage]),default=None),
            'last':max((r['date'] for r in groups[stage]),default=None),
            'last_label_exit':max((r['outcomes']['10']['exit_date'] for r in groups[stage]),default=None)} for stage in ('train','calibration','validation')}
        folds[str(year)]={**stages,'library':manifest,'selection':selection,'status':manifest['status']}
        libraries[str(year)]=library
        print(f'Analog/{year}: references={manifest["references"]}; {selection["model"]}; threshold={selection["threshold"]}; {selection["status"]}',flush=True)
        for r in predicted:history[r['symbol']].append(r)
    payload={'generated_at':datetime.now(timezone.utc).isoformat(),'before':before,'protocol':PROTOCOL,'groups':GROUPS,'models':NAMES,
        'availability_model':'analog25','chart_models':{'selected':'La bàn analog được chọn',**{m:f'Chẩn đoán: {k} giai đoạn tương tự' for m,k in KS.items()}},
        'shared_folds':folds,'assets':{},'errors':{s:errors.get(s,'Missing validated exact-symbol history') for s in SYMBOLS if s not in data},
        'hashes':{str(cache):hashlib.sha256(cache.read_bytes()).hexdigest(),**{name:hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest() for name in ('compass_analog.py','compass_shared.py','compass_forecast.py')}}}
    for symbol,rs in history.items():
        ema=calculate_compass_series(data[symbol])['ema']
        for r in rs:r['forecasts'].update(ema={'bias':ema[r['index']]['bias']},always_long={'bias':'LONG'})
        matched=[r for r in rs if r['forecasts']['analog25']['p_up'] is not None]
        print(f'Evaluate analog {symbol}',flush=True)
        summaries={m:{str(h):{side:summarize(matched,m,side,h) for side in (('ALL','LONG','SHORT') if h==10 else ('ALL',))} for h in (5,10,20)} for m in NAMES}
        pairs=[('selected','always_long'),('selected','ema'),('analog25_direction','always_long'),('analog50_direction','always_long'),('analog100_direction','always_long')]
        payload['assets'][symbol]={'metadata':metadata[symbol],'benchmark':'thư viện trạng thái dùng chung','folds':folds,
            'history':[{k:v for k,v in r.items() if k not in ('features','weekly_features')} for r in rs],
            'matched_dates':{'first':matched[0]['date'] if matched else None,'last':matched[-1]['date'] if matched else None,'count':len(matched)},
            'summaries':summaries,'rule_full_period':{},'yearly':{str(y):{m:quick([r for r in matched if r['date'].startswith(str(y))],m) for m in NAMES} for y in PROTOCOL['years']},
            'diagnostics':{m:probability_diagnostics(matched,m) for m in KS},'stability':{m:stability_summary(matched,m) for m in NAMES},
            'price_clean_sensitivity':{m:quick(matched,m) for m in NAMES},'paired':[paired_comparison(matched,a,b) for a,b in pairs]}
    joblib.dump(libraries,out/'reference-libraries.joblib')
    (out/'results.json').write_text(json.dumps(payload,ensure_ascii=False,allow_nan=False),encoding='utf-8')
    write_report(payload,out/'index.html')
    return payload


def write_report(payload,path):
    from .compass_shared_report import write_report as base
    base(payload,path)
    page=path.read_text(encoding='utf-8').replace('La bàn chung D1: đúng bảy mã trong ảnh','La bàn D1: đối chiếu các trạng thái tương tự')
    page=page.replace('Chọn bằng năm validation trước test, không có cấu hình riêng cho từng market.',
        'Chọn K/ngưỡng bằng năm Y−2, xác nhận cố định trên Y−1, rồi kiểm tra năm Y; không có cấu hình riêng từng market.')
    page=page.replace('Một mô hình và ngưỡng chung, chọn trước năm kiểm tra','Một thư viện đối chiếu và ngưỡng chung cho cả rổ')
    page=page.replace('<label>Mô hình biểu đồ','<p class="notice">Con số trên biểu đồ là tần suất tăng của những trạng thái lịch sử tương tự, đã làm trơn; chưa phải xác suất được hiệu chỉnh hoặc độ chính xác được bảo đảm. Các giai đoạn tương tự có thể tương quan với nhau. Thư viện chỉ lấy mỗi 10 nến trong quá khứ trước năm chọn mô hình.</p><label>Mô hình biểu đồ')
    page=page.replace('<th>Calibration</th>','<th>Năm chọn K/ngưỡng</th>')
    page=page.replace('../compass-exact-d1/index.html','../compass-shared-d1/index.html')
    path.write_text(page,encoding='utf-8')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cache',type=Path,default=Path('reports/compass-exact-d1/candles.json'))
    p.add_argument('--out',type=Path,default=Path('reports/compass-analog-d1'))
    p.add_argument('--before',default='2026-09-17')
    a=p.parse_args();run(a.cache,a.out,a.before)


if __name__=='__main__':main()
