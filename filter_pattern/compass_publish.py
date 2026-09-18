"""Refresh the experimental D1 compass independently of scanner qualification."""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
from html import escape
import json
from pathlib import Path

from .compass import WARMUP
from .compass_context_data import validate_source
from .compass_research import outcome
from .compass_rotation_stable import MODELS, PROTOCOL, series
from .compass_review_page import PAGE
from .models import Candle
from .providers import load_vnstock_ohlcv_many, load_yahoo_ohlcv_many

# No broker-label substitution is hidden: the displayed gold name is a proxy.
SOURCES = {
    'XAUUSD': ('GC=F', 'GC=F · futures đại diện', True),
    'BTCUSD': ('BTC-USD', 'BTC/USD spot · Yahoo', False),
    'ETHUSD': ('ETH-USD', 'ETH/USD spot · Yahoo', False),
    'DXY': ('DX-Y.NYB', 'Chỉ số USD · Yahoo', False),
    'US500': ('^GSPC', 'S&P 500 cash index · Yahoo', False),
    'SPY': ('SPY', 'SPY ETF · Yahoo', False),
    'E1VFVN30': ('E1VFVN30', 'E1VFVN30 · VCI · nghìn VND', False),
}


def fetch_sources() -> dict[str, list[Candle] | Exception]:
    """Use production providers; catch failures per provider and retain missing rows."""
    import yfinance as yf
    # Keep provider cookie/timezone caches outside public/ and in the workspace.
    cache = Path('.cache/compass-yahoo')
    cache.mkdir(parents=True,exist_ok=True)
    yf.set_tz_cache_location(str(cache.resolve()))
    yahoo = [ticker for s,(ticker,_,_) in SOURCES.items() if s != 'E1VFVN30']
    print('Compass: refreshing six Yahoo D1 sources (10y)',flush=True)
    try:
        downloaded = load_yahoo_ohlcv_many(yahoo, period='10y', timeframe='D1')
    except Exception as exc:
        downloaded = dict.fromkeys(yahoo, exc)
    try:
        print('Compass: refreshing E1VFVN30 D1 from VCI (10y)',flush=True)
        vn = load_vnstock_ohlcv_many(['E1VFVN30'], period='10y', timeframe='D1', source='VCI')
    except Exception as exc:
        vn = {'E1VFVN30': exc}
    return {s:(vn if s == 'E1VFVN30' else downloaded).get(ticker, ValueError('No data returned'))
            for s,(ticker,_,_) in SOURCES.items()}


def build_payload(downloaded: dict, before: date, generated_at: str) -> dict:
    assets, errors = {}, {}
    for symbol,(ticker,label,proxy) in SOURCES.items():
        a = {'source':label, 'source_symbol':ticker, 'proxy':proxy, 'history':[],
             'last_date':None, 'stale':False}
        assets[symbol] = a
        try:
            cs = downloaded.get(symbol)
            if isinstance(cs, Exception):
                raise cs
            if not cs:
                raise ValueError('No candles returned')
            # Omit the current provider calendar date for every market, even if
            # an intraday download contains a still-open D1 bar.
            cs = [c for c in cs if c.datetime.date() < before]
            a['quality'] = validate_source(cs)
            a['last_date'] = cs[-1].datetime.date().isoformat()
            a['stale'] = (before-cs[-1].datetime.date()).days > 5
            for i,state in enumerate(series(cs)):
                if i < WARMUP or state['date'] < '2024-01-01':
                    continue
                a['history'].append({'index':i,'date':state['date'],'symbol':symbol,'close':cs[i].close,
                    'forecasts':{'wave':{k:v for k,v in state.items() if k not in ('date','original')},
                                 'original':state['original']},
                    'outcomes':{str(h):outcome(cs,i,h) for h in (5,10,20) if i+h < len(cs)}})
            if not a['history']:
                raise ValueError('No usable research-period candles after warmup')
        except Exception as exc:
            a['history'] = []
            a['last_date'] = None
            a['stale'] = False
            # Keep full exception diagnostics in CI, not arbitrary provider text in public HTML.
            print(f'Compass source failed for {symbol}: {type(exc).__name__}: {exc}', flush=True)
            errors[symbol] = 'Không tải được hoặc dữ liệu không đạt kiểm tra OHLC/lịch sử.'
    return {'generated_at':generated_at,'before':before.isoformat(),'models':MODELS,'assets':assets,
            'protocol':PROTOCOL,'errors':errors,'mode':'scheduled_d1_refresh',
            'scope':'Six instruments plus GC=F gold futures proxy; D1 research only; not setup authority'}


def publish(out: Path, downloaded: dict | None = None, before: date | None = None) -> dict:
    now = datetime.now(timezone.utc)
    before = before or now.date()
    payload = build_payload(fetch_sources() if downloaded is None else downloaded, before, now.isoformat())
    out.mkdir(parents=True,exist_ok=True)
    dates = [a['last_date'] for a in payload['assets'].values() if a['last_date']]
    manifest = {'generated_at':payload['generated_at'],'last_date':max(dates) if dates else None,
                'available':sum(bool(a['history']) for a in payload['assets'].values()),
                'total':len(SOURCES),'stale':[s for s,a in payload['assets'].items() if a['stale']],
                'missing':list(payload['errors']),'timeframe':'D1','experimental':True}
    encoded = json.dumps(payload,ensure_ascii=False,allow_nan=False)
    (out/'results.json').write_text(encoded,encoding='utf-8')
    status = ('<p class="notice">Cập nhật '+escape(payload['generated_at'])+' · Có dữ liệu '
              +str(manifest['available'])+'/7 mã · Nến có ngày từ '+escape(before.isoformat())
              +' trở đi chưa được sử dụng. La bàn D1 tự tải lại mỗi lần xuất bản.</p>')
    for symbol,a in payload['assets'].items():
        if symbol in payload['errors']:
            status += '<p class="notice">'+symbol+': '+escape(payload['errors'][symbol])+'</p>'
        elif a['stale']:
            status += '<p class="notice">'+symbol+': dữ liệu cũ, nến cuối '+a['last_date']+'.</p>'
    if dates:
        page = PAGE
        start = page.index('<details><summary>Cách đọc')
        end = page.index('</main>',start)
        page = page[:start]+('<p class="footer">Đánh giá hồi cứu từ 2024 trên dữ liệu đã được xem nhiều vòng. '
            'Tổng rổ chỉ gồm mã có dữ liệu, cân bằng tài sản; US500/SPY mỗi mã nửa trọng số. '
            'Thiếu một nguồn không chứng minh đủ cả rổ. Màu mô tả xu hướng, chưa được xác nhận dự báo đúng 70%.</p>'
            '<p class="footer"><a href="../index.html">Trang chính / Scanner / RRG</a> · '
            '<a href="results.json">Dữ liệu la bàn</a></p>')+page[end:]
        page = page.replace('<div id="cards" class="cards"></div>',status+'<div id="cards" class="cards"></div>')
        page = page.replace('__DATA__',encoded.replace('<','\\u003c'))
    else:
        page = '<!doctype html><html lang="vi"><meta charset="utf-8"><title>Market Compass D1</title><h1>Market Compass — thử nghiệm</h1>'+status+'<p>Chưa có dữ liệu D1 hợp lệ trong lần cập nhật này.</p><a href="../index.html">Trang chính</a></html>'
    (out/'index.html').write_text(page,encoding='utf-8')
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False),encoding='utf-8')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    args = parser.parse_args()
    print(json.dumps(publish(args.out),ensure_ascii=False))
