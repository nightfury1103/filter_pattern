"""Audit the repo's XAUUSD -> GC=F source without relabelling futures as spot."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from dataclasses import asdict
import hashlib
from html import escape
import json
from pathlib import Path

from . import compass_confidence70 as confidence
from . import compass_reversion as reversion
from .compass_context_data import validate_source
from .compass_forecast import label_rows
from .models import Candle
from .providers import load_yahoo_ohlcv


def run(out: Path, refresh: bool = False):
    out.mkdir(parents=True, exist_ok=True)
    source = out/'source.json'
    if refresh or not source.exists():
        cs = [c for c in load_yahoo_ohlcv('GC=F', period='10y', timeframe='D1')
              if c.datetime.date().isoformat() < '2026-09-17']
        validate_source(cs)
        source.write_text(json.dumps({'retrieved_at':datetime.now(timezone.utc).isoformat(),
            'symbol':'XAUUSD', 'actual_source_symbol':'GC=F', 'proxy':True, 'auto_adjust':False,
            'provider':'filter_pattern.providers.load_yahoo_ohlcv', 'before':'2026-09-17',
            'candles':[{**asdict(c), 'datetime':c.datetime.isoformat()} for c in cs]}, allow_nan=False), encoding='utf-8')
    data = json.loads(source.read_text(encoding='utf-8'))
    if data['actual_source_symbol'] != 'GC=F' or data['proxy'] is not True or data['auto_adjust'] is not False:
        raise ValueError('Expected explicit GC=F futures proxy, auto_adjust=False, as used by scanner')
    cs = [Candle(**{**c, 'datetime':datetime.fromisoformat(c['datetime'])}) for c in data['candles']]
    if any(c.datetime.date().isoformat() >= '2026-09-17' for c in cs):
        raise ValueError('Source contains bars beyond the frozen comparison cutoff')
    audit = validate_source(cs)
    versions = {}
    dependencies = [source, Path(__file__), Path('filter_pattern/providers.py'), Path('filter_pattern/universe.py')]
    for name, module, old_path in (
        ('confidence70', confidence, Path('reports/compass-confidence70-d1/results.json')),
        ('reversion', reversion, Path('reports/compass-reversion-d1/results.json'))):
        old = json.loads(old_path.read_text(encoding='utf-8'))
        gold = [r for r in label_rows(cs, module.signals(cs, 'GOLD_FUTURES')) if r['date'] >= '2024-01-01']
        combined = old['history']+gold
        models = [m for m in module.NAMES if m != 'selected']
        versions[name] = {'names':module.NAMES, 'gold_history':gold,
            'gold':{m:{str(h):confidence.metrics(gold,m,h) for h in (5,10,20)} for m in models},
            'basket_with_gold_proxy':{m:{str(h):confidence.metrics(combined,m,h) for h in (5,10,20)} for m in models},
            'old_six_asset_basket':{m:old['aggregate'][m] for m in models}}
        dependencies.extend([old_path,Path(module.__file__)])
    dependencies.extend(Path('filter_pattern')/(name+'.py') for name in
                        ('compass','compass_rotation_stable','compass_wave','compass_shared','compass_forecast','compass_research','compass_context_data'))
    payload = {'generated_at':datetime.now(timezone.utc).isoformat(),
        'source':{k:v for k,v in data.items() if k != 'candles'}, 'data_audit':audit,
        'bars':len(cs), 'first':cs[0].datetime.date().isoformat(), 'last':cs[-1].datetime.date().isoformat(),
        'spot_xauusd_tested':False, 'selection_rerun':False,
        'note':'Fixed-rule diagnostics only; seven exposures with gold futures proxy, not seven exact spot symbols.',
        'versions':versions, 'hashes':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in dependencies}}
    (out/'results.json').write_text(json.dumps(payload,ensure_ascii=False,allow_nan=False),encoding='utf-8')
    def table(stats, names):
        rows=''
        for m,s in stats.items():
            vals=(names[m],confidence.percent(s['accuracy']),confidence.percent(s['coverage']),s['signals'],
                  f"{confidence.percent(s['sides']['up']['accuracy'])} / {s['sides']['up']['signals']}",
                  f"{confidence.percent(s['sides']['down']['accuracy'])} / {s['sides']['down']['signals']}")
            rows+='<tr>'+''.join('<td>'+escape(str(v))+'</td>' for v in vals)+'</tr>'
        return '<div class="scroll"><table><tr><th>Quy tắc</th><th>Đúng</th><th>Độ phủ</th><th>Mẫu</th><th>Tăng: đúng / mẫu</th><th>Giảm: đúng / mẫu</th></tr>'+rows+'</table></div>'
    body='<h1>XAUUSD trong repo — nguồn giá vàng đã xác minh</h1>'
    body+='<p>Repo có dữ liệu vàng. Scanner ánh xạ nhãn XAUUSD → Yahoo GC=F (gold futures); RRG ánh xạ XAUUSD → StockCharts $GOLD. Các báo cáo trước thiếu OHLC spot, không phải repo hoàn toàn thiếu giá vàng.</p>'
    body+=f'<p>Đã lấy lại bằng provider hiện tại, auto_adjust=False: <strong>{len(cs):,} nến D1</strong>, {payload["first"]} → {payload["last"]}. Đây là futures đại diện, chưa phải OHLC OANDA:XAUUSD.</p>'
    body+='<p>Không thay nguồn ngầm: nhãn nội bộ GOLD_FUTURES. Giữ nguyên quy tắc và cách chấm open T+1 → close T+10. Bảng gộp bổ sung một nguồn vàng đại diện vào sáu mã cũ; không tuyên bố kiểm thử đủ bảy mã chính xác. Không chọn lại tham số hoặc mô hình theo kết quả vàng.</p>'
    body+='<p><a href="source.json">OHLC từ provider repo</a> · <a href="results.json">Kết quả đầy đủ 5/10/20 nến và CI95</a></p>'
    for name,v in versions.items():
        title='Các bộ lọc xác nhận' if name=='confidence70' else 'Xu hướng chậm và nhịp hồi'
        body+='<h2>'+title+' — riêng vàng GC=F, 10 nến</h2>'+table({m:s['10'] for m,s in v['gold'].items()},v['names'])
        body+='<h2>'+title+' — rổ sáu mã + vàng đại diện</h2>'+table({m:s['10'] for m,s in v['basket_with_gold_proxy'].items()},v['names'])
    body+='<p>Không quy tắc nào đủ bằng chứng 70% cho cả rổ trong lần kiểm tra này. Những tỷ lệ cao riêng vàng phải đọc cùng độ phủ và mẫu mỗi hướng; trường hợp toàn hướng tăng không chứng minh khả năng nhận biết cả tăng/giảm.</p>'
    body+='<p>Kết quả hồi cứu; các giai đoạn này đã được xem nhiều vòng. Không coi giá futures, token vàng hoặc tọa độ RRG là OHLC spot. Các báo cáo sáu mã cũ được giữ để đối chiếu.</p>'
    (out/'index.html').write_text('<!doctype html><html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Gold source audit</title><style>body{background:#101827;color:#dce5f0;font:15px system-ui;max-width:1200px;margin:24px auto;padding:0 18px}p{line-height:1.6}a{color:#64caff}h2{margin-top:32px}table{border-collapse:collapse;width:100%}td,th{padding:10px;border-bottom:1px solid #334155;text-align:right}td:first-child,th:first-child{text-align:left}.scroll{overflow-x:auto}</style>'+body+'</html>',encoding='utf-8')
    print(json.dumps({'bars':len(cs),'audit':audit,'gold_10':{n:{m:hs['10'] for m,hs in v['gold'].items()} for n,v in versions.items()}},indent=2))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,default=Path('reports/compass-gold-repo-d1'))
    parser.add_argument('--refresh',action='store_true')
    args=parser.parse_args()
    run(args.out,args.refresh)
