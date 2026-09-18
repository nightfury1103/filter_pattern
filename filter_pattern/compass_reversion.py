"""Frozen slow-trend / fast-reversion hypotheses, independent of entry setups."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from html import escape
import json
from pathlib import Path

from .compass import WARMUP, _atr, _ema
from .compass_confidence70 import metrics, passes, percent, prior_year
from .compass_context_data import validate_source
from .compass_exact import SYMBOLS
from .compass_forecast import label_rows
from .compass_rotation_stable import series
from .models import Candle

CANDIDATES = ('reversion', 'pullback', 'recovery')
NAMES = {'base': 'Bản ổn định: mọi ngày', 'aligned': 'Vòng trước: cùng chiều động lượng',
         'reversion': 'Hồi về EMA20', 'pullback': 'Điều chỉnh trong xu hướng chậm',
         'recovery': 'Hồi phục theo xu hướng chậm', 'selected': 'Vượt cổng hai năm trước',
         'always_up': 'Tham chiếu luôn tăng'}


def rules(slow: int, z: float | None, previous_z: float | None) -> dict:
    if z is None:
        return dict.fromkeys(CANDIDATES, 0)
    return {'reversion': (-1 if z > 0 else 1) if abs(z) >= 1 else 0,
            'pullback': slow if slow and slow*z <= -.5 else 0,
            'recovery': slow if slow and previous_z is not None and -1.5 <= slow*z <= 0
                        and slow*(z-previous_z) > 0 else 0}


def signals(candles: list[Candle], symbol: str) -> list[dict]:
    validate_source(candles)
    close = [c.close for c in candles]
    e20, e50, e200, atr = _ema(close, 20), _ema(close, 50), _ema(close, 200), _atr(candles)
    z = [(p-e)/a if a else None for p,e,a in zip(close, e20, atr)]
    result = []
    for i, state in enumerate(series(candles)):
        if i < WARMUP:
            continue
        slow = 1 if close[i] > e200[i] and e50[i] > e50[i-10] else -1 if close[i] < e200[i] and e50[i] < e50[i-10] else 0
        sign = state['trend_sign']
        result.append({'index': i, 'date': state['date'], 'symbol': symbol,
            'phase': state['phase'], 'slow_direction': slow, 'z': z[i],
            'directions': {'base': sign, 'aligned': sign if sign == state['momentum_sign'] else 0,
                           **rules(slow, z[i], z[i-3]), 'always_up': 1}})
    return result


def select(rows: list[dict], year: int) -> dict:
    development = {m: metrics(prior_year(rows, year-2), m, bootstrap=False) for m in CANDIDATES}
    confirmation = {m: metrics(prior_year(rows, year-1), m, bootstrap=False) for m in CANDIDATES}
    qualified = [m for m in CANDIDATES if passes(development[m])]
    candidate = max(qualified, key=lambda m: development[m]['coverage']) if qualified else None
    chosen = candidate if candidate and passes(confirmation[candidate]) else None
    return {'candidate': candidate, 'chosen': chosen, 'development': development, 'confirmation': confirmation}


def table(stats):
    body = ''
    for key, m in stats.items():
        ci = '—' if m['ci95'] is None else ' – '.join(percent(v) for v in m['ci95'])
        values = (NAMES.get(key, key), percent(m['accuracy']), percent(m['coverage']),
                  m['signals'], m['false_signals'],
                  f"{percent(m['sides']['up']['accuracy'])} / {m['sides']['up']['signals']}",
                  f"{percent(m['sides']['down']['accuracy'])} / {m['sides']['down']['signals']}", ci)
        body += '<tr>'+''.join(f'<td>{escape(str(v))}</td>' for v in values)+'</tr>'
    return '<div class="scroll"><table><tr><th>Quy tắc / mã</th><th>Đúng</th><th>Độ phủ</th><th>Mẫu</th><th>Sai</th><th>Tăng: đúng / mẫu</th><th>Giảm: đúng / mẫu</th><th>CI95</th></tr>'+body+'</table></div>'


def write_report(payload: dict, path: Path):
    body = '<h1>Compass D1 — xu hướng chậm và nhịp hồi</h1><p>Mục tiêu 70% đúng dấu return open T+1 → close T+10; không TP/SL, không setup. Kỳ kiểm tra 2024–16/09/2026. Dữ liệu đã được xem ở nhiều vòng, không phải holdout mới.</p>'
    body += '<p>Ba giả thuyết chung: hồi về EMA20 khi lệch ít nhất 1 ATR; điều chỉnh ngược xu hướng chậm; hồi phục theo xu hướng chậm. Màu la bàn gốc không đổi. Ngày không đạt điều kiện là chưa đủ xác nhận.</p>'
    body += '<p><a href="../compass-rotation-stable-d1/index.html">La bàn và biểu đồ giá hiện tại</a> · <a href="../compass-confidence70-d1/index.html">Vòng lọc trước</a> · <a href="protocol.md">Quy tắc chốt trước chạy</a> · <a href="results.json">Dữ liệu đầy đủ</a></p>'
    body += '<h2>'+('Vượt cổng hồi cứu; chưa xác nhận tương lai' if payload['all_roster_evidence70'] else 'Chưa chứng minh 70% trên toàn rổ')+'</h2>'
    body += '<p>Trọng số cân bằng tài sản; US500/SPY mỗi mã nửa trọng số. Mẫu là ngày-tài sản, có chồng lấn và tương quan. Tỷ lệ có trọng số không nhất thiết bằng tổng thắng/tổng mẫu.</p>'
    body += '<p>Thiếu dữ liệu đủ chuẩn: '+escape(', '.join(payload['missing']) or 'không')+'.</p>'
    for horizon in ('10', '5', '20'):
        body += f'<h2>{horizon} nến'+(' — mục tiêu chính' if horizon == '10' else ' — chẩn đoán')+'</h2>'
        body += table({m: hs[horizon] for m,hs in payload['aggregate'].items()})
    for m in CANDIDATES:
        body += '<h2>'+NAMES[m]+' — từng mã, 10 nến</h2>'+table({s:a[m] for s,a in payload['assets'].items()})
    for year, stats in payload['by_year'].items():
        body += f'<h2>Năm {year} — 10 nến</h2>'+table(stats)
    body += '<h2>Chọn bằng hai năm trước</h2><ul>'+''.join(f'<li>{y}: {escape(NAMES[s["chosen"]] if s["chosen"] else "không có quy tắc vượt cổng")}</li>' for y,s in payload['selection'].items())+'</ul>'
    body += '<p>Cổng chọn ở từng kỳ trước: accuracy ≥70%, coverage ≥10%, ≥100 mẫu, ≥20 mỗi hướng. Cổng bằng chứng còn yêu cầu ≥100 mẫu lịch giãn 10 nến và cận dưới CI95 ≥70%. Không tự triển khai live hay gán xác suất cho màu.</p>'
    path.write_text('<!doctype html><html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Compass — nhịp hồi</title><style>body{background:#101827;color:#dce5f0;font:15px system-ui;max-width:1280px;margin:24px auto;padding:0 18px}a{color:#64caff}h2{margin-top:32px}table{border-collapse:collapse;width:100%}th,td{padding:10px;text-align:right;border-bottom:1px solid #334155}td:first-child,th:first-child{text-align:left}.scroll{overflow-x:auto}p{line-height:1.6}</style>'+body+'</html>', encoding='utf-8')


def run(cache: Path, out: Path):
    out.mkdir(parents=True, exist_ok=True)
    protocol = Path('docs/compass-reversion-protocol.md')
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
    dependencies = [cache, protocol, Path(__file__)]+[Path(__file__).with_name(n+'.py') for n in
        ('compass', 'compass_confidence70', 'compass_rotation_stable', 'compass_wave', 'compass_shared',
         'compass_forecast', 'compass_context_data', 'compass_research', 'compass_rotation', 'compass_exact', 'models')]
    payload = {'generated_at': datetime.now(timezone.utc).isoformat(), 'target': .70, 'missing': missing,
        'aggregate': aggregate, 'assets': assets, 'by_year': by_year, 'selection': selection,
        'data_audits': audits, 'all_roster_evidence70': not missing and aggregate['selected']['10']['evidence70']
                            and all(a['selected']['evidence70'] for a in assets.values()),
        'hashes': {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in dependencies}, 'history': test}
    (out/'results.json').write_text(json.dumps(payload, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    write_report(payload, out/'index.html')
    print(json.dumps({m: v['10'] for m,v in aggregate.items()}, indent=2))
    print('Selection:', {y:s['chosen'] for y,s in selection.items()})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', type=Path, default=Path('reports/compass-exact-d1/candles.json'))
    parser.add_argument('--out', type=Path, default=Path('reports/compass-reversion-d1'))
    args = parser.parse_args()
    run(args.cache, args.out)
