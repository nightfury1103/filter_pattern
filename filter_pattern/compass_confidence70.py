"""Bounded shared filters for the frozen four-state compass; research only."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import html
import json
import math
from pathlib import Path

import numpy as np

from .compass import WARMUP, _ema, _atr, efficiency_ratio
from .compass_context_data import validate_source
from .compass_exact import SYMBOLS
from .compass_forecast import label_rows
from .compass_rotation_stable import series
from .compass_shared import weights
from .models import Candle

CANDIDATES = ('aligned', 'confirmed', 'bounded')
NAMES = {'base': 'Bản ổn định: mọi ngày', 'aligned': 'Xu hướng + động lượng',
         'confirmed': '+ Xác nhận EMA50', 'bounded': '+ Giới hạn chạy xa / nhiễu',
         'selected': 'Đạt kiểm tra hai năm trước', 'always_up': 'Tham chiếu: luôn tăng'}


def signals(candles: list[Candle], symbol: str) -> list[dict]:
    validate_source(candles)
    close = [c.close for c in candles]
    e20, e50, atr = _ema(close, 20), _ema(close, 50), _atr(candles)
    result = []
    for i, state in enumerate(series(candles)):
        if i < WARMUP:
            continue
        sign = state['trend_sign']
        aligned = sign != 0 and sign == state['momentum_sign']
        confirmed = aligned and all(v * sign > 0 for v in
            (close[i]-e50[i], e20[i]-e50[i], e50[i]-e50[i-5]))
        extension = abs(close[i]-e20[i]) / atr[i] if atr[i] else None
        bounded = confirmed and extension is not None and extension <= 1.5 and efficiency_ratio(close[i-20:i+1]) >= .25
        result.append({'index': i, 'date': state['date'], 'symbol': symbol, 'phase': state['phase'],
                       'directions': {'base': sign, 'aligned': sign if aligned else 0,
                                      'confirmed': sign if confirmed else 0, 'bounded': sign if bounded else 0,
                                      'always_up': 1}, 'extension_atr': extension})
    return result


def metrics(rows: list[dict], model: str, horizon: int = 10, bootstrap: bool = True) -> dict:
    eligible = [r for r in rows if str(horizon) in r['outcomes']]
    w = weights(eligible)
    signs = np.array([r['directions'][model] for r in eligible])
    returns = np.array([r['outcomes'][str(horizon)]['return_pct'] for r in eligible])
    mask = signs != 0
    correct = returns * signs > 0
    total = float(w[mask].sum())
    sides = {}
    for name, sign in (('up', 1), ('down', -1)):
        side = signs == sign
        sw = float(w[side].sum())
        sides[name] = {'signals': int(side.sum()), 'wins': int((side & correct).sum()),
                       'accuracy': float(w[side & correct].sum()/sw) if sw else None}
    scheduled = np.array([(r['index']-WARMUP) % horizon == 0 for r in eligible], dtype=bool) & mask
    ci = None
    days = sorted({r['date'] for r in eligible})
    if bootstrap and mask.sum() >= 30 and len(days) >= 120 and 0 < (mask & correct).sum() < mask.sum():
        positions = {d: i for i, d in enumerate(days)}
        totals, wins = np.zeros(len(days)), np.zeros(len(days))
        for i, r in enumerate(eligible):
            if mask[i]:
                j = positions[r['date']]
                totals[j] += w[i]
                wins[j] += w[i] * correct[i]
        rng = np.random.default_rng(1709)
        scores = []
        for _ in range(500):
            starts = rng.integers(0, len(days)-60+1, size=math.ceil(len(days)/60))
            draw = np.concatenate([np.arange(s, s+60) for s in starts])[:len(days)]
            denominator = totals[draw].sum()
            if denominator:
                scores.append(float(wins[draw].sum()/denominator))
        if len(scores) >= 450:
            ci = np.quantile(scores, [.025, .975]).tolist()
    coverage = total / float(w.sum()) if len(w) else 0.
    return {'eligible': len(eligible), 'signals': int(mask.sum()), 'wins': int((mask & correct).sum()),
            'false_signals': int((mask & ~correct).sum()), 'coverage': coverage,
            'accuracy': float(w[mask & correct].sum()/total) if total else None,
            'sides': sides, 'ci95': ci, 'scheduled_signals': int(scheduled.sum()),
            'scheduled_accuracy': float(w[scheduled & correct].sum()/w[scheduled].sum()) if scheduled.any() else None,
            'evidence70': bool(coverage >= .1 and scheduled.sum() >= 100 and ci is not None and ci[0] >= .70
                               and min(s['signals'] for s in sides.values()) >= 20)}


def prior_year(rows: list[dict], year: int) -> list[dict]:
    start, end = f'{year}-01-01', f'{year+1}-01-01'
    return [r for r in rows if start <= r['date'] < end and '10' in r['outcomes']
            and r['outcomes']['10']['exit_date'] < end]


def passes(m: dict) -> bool:
    return (m['accuracy'] is not None and m['accuracy'] >= .70 and m['coverage'] >= .10
            and m['signals'] >= 100 and min(s['signals'] for s in m['sides'].values()) >= 20)


def select(rows: list[dict], year: int) -> dict:
    development = {m: metrics(prior_year(rows, year-2), m, bootstrap=False) for m in CANDIDATES}
    confirmation = {m: metrics(prior_year(rows, year-1), m, bootstrap=False) for m in CANDIDATES}
    qualified = [m for m in CANDIDATES if passes(development[m])]
    candidate = max(qualified, key=lambda m: development[m]['coverage']) if qualified else None
    chosen = candidate if candidate and passes(confirmation[candidate]) else None
    return {'candidate': candidate, 'chosen': chosen, 'development': development, 'confirmation': confirmation}


def percent(x):
    return '—' if x is None else f'{100*x:.1f}%'


def write_report(payload: dict, out: Path):
    def table(stats):
        body = ''
        for key, m in stats.items():
            ci = '—' if m['ci95'] is None else ' – '.join(percent(v) for v in m['ci95'])
            body += '<tr>'+''.join(f'<td>{html.escape(str(v))}</td>' for v in
                (NAMES.get(key, key), percent(m['accuracy']), percent(m['coverage']), m['signals'],
                 m['false_signals'], percent(m['sides']['up']['accuracy']), percent(m['sides']['down']['accuracy']), ci))+'</tr>'
        return '<div class="scroll"><table><tr><th>Bộ lọc / mã</th><th>Đúng hướng</th><th>Độ phủ</th><th>Mẫu</th><th>Sai</th><th>Hướng tăng</th><th>Hướng giảm</th><th>CI95</th></tr>'+body+'</table></div>'
    content = '<h1>Market Compass D1 — kiểm tra mục tiêu 70%</h1><p>2024–16/09/2026; close T → open T+1 đến close T+10. Dữ liệu đã được xem ở các vòng trước, không phải holdout mới.</p>'
    content += '<p>Ba bộ lọc dùng chung cả rổ, giữ nguyên bốn trạng thái. Ngày bị lọc không đồng nghĩa đảo hướng. US500/SPY mỗi mã nửa trọng số. Các ngày-tài sản có tương quan.</p>'
    content += '<p><a href="../compass-rotation-stable-d1/index.html">Mở la bàn và biểu đồ giá hiện tại</a> · <a href="results.json">Số liệu đầy đủ, 5/10/20 nến</a></p>'
    content += '<h2>Kết quả chính — chưa chứng minh 70%</h2>' if not payload['all_roster_evidence70'] else '<h2>Cổng hồi cứu đạt; cần kiểm thử tương lai</h2>'
    content += table({m: v['10'] for m, v in payload['aggregate'].items()})
    content += '<p>Thiếu OHLC đủ chuẩn: '+html.escape(', '.join(payload['missing']))+'. Không suy rộng kết quả sáu mã thành đủ bảy mã.</p>'
    for m in ('base', *CANDIDATES):
        content += '<h2>'+NAMES[m]+' — từng mã, 10 nến</h2>'+table({s: a[m] for s, a in payload['assets'].items()})
    content += '<h2>Chọn bằng hai năm trước</h2><ul>'+''.join(f'<li>{y}: {html.escape(str(s["chosen"] or "không có bộ lọc vượt cổng"))}</li>' for y,s in payload['selection'].items())+'</ul>'
    content += '<p>Cổng: đúng ≥70%, độ phủ ≥10%, ≥100 mẫu và ≥20 mỗi hướng ở từng kỳ trước. Bằng chứng hồi cứu còn yêu cầu CI95 thấp nhất ≥70% và ≥100 mẫu theo lịch giãn 10 nến. Không gán xác suất 70% cho màu hoặc điểm số.</p>'
    out.write_text('<!doctype html><html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Compass 70%</title><style>body{background:#101827;color:#dce5f0;font:15px system-ui;margin:24px auto;padding:0 18px;max-width:1200px}a{color:#64caff}h2{margin-top:32px}table{border-collapse:collapse;width:100%}th,td{padding:10px;text-align:right;border-bottom:1px solid #334155}td:first-child,th:first-child{text-align:left}.scroll{overflow-x:auto}p{line-height:1.6}</style>'+content+'</html>', encoding='utf-8')


def run(cache: Path, out: Path):
    out.mkdir(parents=True, exist_ok=True)
    protocol = Path('docs/compass-confidence70-protocol.md')
    (out/'protocol.md').write_bytes(protocol.read_bytes())
    data = json.loads(cache.read_text(encoding='utf-8'))
    rows, audits = [], {}
    for symbol in SYMBOLS:
        if symbol not in data['instruments']:
            continue
        candles = [Candle(**{**c, 'datetime': datetime.fromisoformat(c['datetime'])})
                   for c in data['instruments'][symbol]['candles'] if c['datetime'][:10] < '2026-09-17']
        audits[symbol] = validate_source(candles)
        rows.extend(label_rows(candles, signals(candles, symbol)))
    selection = {str(y): select(rows, y) for y in (2024, 2025, 2026)}
    test = [r for r in rows if '2024-01-01' <= r['date'] < '2027-01-01']
    for r in test:
        chosen = selection[r['date'][:4]]['chosen']
        r['directions']['selected'] = r['directions'][chosen] if chosen else 0
    aggregate = {m: {str(h): metrics(test, m, h) for h in (5, 10, 20)} for m in NAMES}
    assets = {s: {m: metrics([r for r in test if r['symbol'] == s], m) for m in NAMES} for s in audits}
    by_year = {str(y): {m: metrics([r for r in test if r['date'].startswith(str(y))], m) for m in NAMES} for y in (2024, 2025, 2026)}
    missing = [s for s in SYMBOLS if s not in audits]
    dependencies = (cache, protocol, Path(__file__), Path(__file__).with_name('compass_rotation_stable.py'),
                    Path(__file__).with_name('compass_wave.py'), Path(__file__).with_name('compass.py'),
                    Path(__file__).with_name('compass_shared.py'), Path(__file__).with_name('compass_research.py'))
    payload = {'generated_at': datetime.now(timezone.utc).isoformat(), 'target': .70, 'missing': missing,
               'aggregate': aggregate, 'assets': assets, 'by_year': by_year, 'selection': selection,
               'data_audits': audits, 'all_roster_evidence70': not missing and all(a['selected']['evidence70'] for a in assets.values()),
               'hashes': {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in dependencies}, 'history': test}
    (out/'results.json').write_text(json.dumps(payload, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    write_report(payload, out/'index.html')
    print(json.dumps({m: v['10'] for m, v in aggregate.items()}, indent=2))
    print('Selection:', {y: s['chosen'] for y, s in selection.items()})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', type=Path, default=Path('reports/compass-exact-d1/candles.json'))
    parser.add_argument('--out', type=Path, default=Path('reports/compass-confidence70-d1'))
    args = parser.parse_args()
    run(args.cache, args.out)
