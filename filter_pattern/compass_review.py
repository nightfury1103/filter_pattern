"""Standalone all-symbol review of the existing compass, including repo gold proxy."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from .compass_confidence70 import metrics
from .compass_context_data import validate_source
from .compass_exact import SYMBOLS
from .compass_research import outcome
from .compass_rotation_stable import series
from .models import Candle
from .compass_review_page import PAGE


def build(out: Path):
    stable_path = Path('reports/compass-rotation-stable-d1/results.json')
    gold_path = Path('reports/compass-gold-repo-d1/source.json')
    stable = json.loads(stable_path.read_text(encoding='utf-8'))
    gold = json.loads(gold_path.read_text(encoding='utf-8'))
    if gold['actual_source_symbol'] != 'GC=F' or gold['proxy'] is not True:
        raise ValueError('Gold source must explicitly identify GC=F proxy')
    cs = [Candle(**{**c, 'datetime':datetime.fromisoformat(c['datetime'])}) for c in gold['candles']
          if c['datetime'][:10] < stable['before']]
    validate_source(cs)
    states = series(cs)
    gold_rows = []
    for i,s in enumerate(states):
        if s['date'] < '2024-01-01':
            continue
        gold_rows.append({'index':i, 'date':s['date'], 'symbol':'XAUUSD', 'close':cs[i].close,
            'forecasts':{'wave':{k:v for k,v in s.items() if k not in ('date','original')}, 'original':s['original']},
            'outcomes':{str(h):outcome(cs,i,h) for h in (5,10,20) if i+h < len(cs)}})
    assets = {'XAUUSD':{'history':gold_rows, 'source':'GC=F · futures đại diện', 'proxy':True}}
    labels = {'BTCUSD':'BTC/USD spot', 'ETHUSD':'ETH/USD spot', 'DXY':'Chỉ số USD',
              'US500':'S&P 500 cash index', 'SPY':'SPY ETF', 'E1VFVN30':'ETF E1VFVN30'}
    for symbol in SYMBOLS:
        if symbol == 'XAUUSD':
            continue
        assets[symbol] = {'history':stable['assets'][symbol]['history'], 'source':labels[symbol], 'proxy':False}
    combined = []
    for symbol,a in assets.items():
        for r in a['history']:
            r['directions'] = {m:f['trend_sign'] for m,f in r['forecasts'].items()}
            r['directions']['always_up'] = 1
        a['metrics'] = {m:{str(h):metrics(a['history'],m,h) for h in (5,10,20)} for m in stable['models']}
        combined.extend(a['history'])
    payload = {'generated_at':datetime.now(timezone.utc).isoformat(), 'before':stable['before'],
        'groups':stable['groups'], 'models':stable['models'], 'assets':assets,
        'aggregate':{m:{str(h):metrics(combined,m,h) for h in (5,10,20)} for m in stable['models']},
        'scope':'Six exact researched instruments plus GC=F representing displayed XAUUSD; not XAUUSD spot',
        'hashes':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in
                  (stable_path,gold_path,Path(__file__),Path(__file__).with_name('compass_review_page.py'),
                   Path(__file__).with_name('compass_rotation_stable.py'),Path(__file__).with_name('compass_confidence70.py'))}}
    out.mkdir(parents=True,exist_ok=True)
    encoded = json.dumps(payload,ensure_ascii=False,allow_nan=False)
    (out/'results.json').write_text(encoded,encoding='utf-8')
    (out/'index.html').write_text(PAGE.replace('__DATA__',encoded.replace('<','\\u003c')),encoding='utf-8')
    print(json.dumps({'report':str(out/'index.html'),'symbols':list(assets),'aggregate10':payload['aggregate']['wave']['10']},indent=2))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,default=Path('reports/compass-review-d1'))
    build(parser.parse_args().out)
