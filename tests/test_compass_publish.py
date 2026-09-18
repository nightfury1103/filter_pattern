from datetime import date, datetime, timedelta
import json
from pathlib import Path

from filter_pattern import compass_publish as cp
from filter_pattern.compass_navigation import compass_panel
from filter_pattern.report import write_html_payload, write_site_index, validate_published_site
from filter_pattern.models import Candle


def candles():
    return [Candle(datetime(2023,1,1)+timedelta(days=i),100+i*.1,102+i*.1,99+i*.1,101+i*.1,1)
            for i in range(800)]


def test_completed_d1_only_missing_source_and_no_old_data_reuse(tmp_path):
    cs=candles(); cutoff=date(2025,1,15)
    inputs={s:cs for s in cp.SOURCES}
    payload=cp.build_payload(inputs,cutoff,'2025-01-15T12:00:00Z')
    assert len(payload['assets'])==7
    gold=payload['assets']['XAUUSD']
    assert gold['proxy'] and gold['source_symbol']=='GC=F'
    for a in payload['assets'].values():
        assert a['last_date']=='2025-01-14'
        assert all(r['date']<'2025-01-15' for r in a['history'])
        assert all(o['exit_date']<'2025-01-15' for r in a['history'] for o in r['outcomes'].values())
    cp.publish(tmp_path/'compass',inputs,cutoff)
    inputs['XAUUSD']=ValueError('Provider unavailable')
    manifest=cp.publish(tmp_path/'compass',inputs,cutoff)
    saved=json.loads((tmp_path/'compass/results.json').read_text(encoding='utf-8'))
    assert manifest['available']==6 and manifest['missing']==['XAUUSD']
    assert saved['assets']['XAUUSD']['history']==[]
    assert 'Provider unavailable' not in (tmp_path/'compass/index.html').read_text(encoding='utf-8')


def test_all_failed_refresh_replaces_previous_page_with_status(tmp_path):
    cp.publish(tmp_path,{s:ValueError('unavailable') for s in cp.SOURCES},date(2025,1,15))
    text=(tmp_path/'index.html').read_text(encoding='utf-8')
    assert 'Chưa có dữ liệu D1 hợp lệ' in text
    assert '<script>' not in text


def test_navigation_added_after_rrg_and_relative_paths(tmp_path):
    assert compass_panel(tmp_path/'d1/index.html')==''
    cp.publish(tmp_path/'compass',{s:candles() for s in cp.SOURCES},date(2025,1,15))
    p={'timeframe':'D1','config':{'timeframe':'D1'},'candidates':[],'rejected':[]}
    source=tmp_path/'d1/results.json'; source.parent.mkdir()
    source.write_text(json.dumps(p))
    write_html_payload(p,source.with_name('index.html'))
    write_site_index([source],tmp_path/'index.html')
    child=source.with_name('index.html').read_text()
    root=(tmp_path/'index.html').read_text()
    assert 'href="../compass/index.html"' in child and 'src="../compass/index.html"' in child
    assert 'href="compass/index.html"' in root
    assert 'Market Compass — thử nghiệm' in child
    assert validate_published_site(tmp_path)['total_bytes']>0


def test_fetch_uses_existing_daily_providers_and_isolates_failure(monkeypatch):
    calls=[]
    def yahoo(symbols,**kw):
        calls.append(('yahoo',symbols,kw));return {s:[] for s in symbols}
    def vn(symbols,**kw):
        calls.append(('vn',symbols,kw));raise RuntimeError('unavailable')
    monkeypatch.setattr(cp,'load_yahoo_ohlcv_many',yahoo)
    monkeypatch.setattr(cp,'load_vnstock_ohlcv_many',vn)
    result=cp.fetch_sources()
    assert set(result)==set(cp.SOURCES)
    assert isinstance(result['E1VFVN30'],RuntimeError)
    assert calls[0][2]=={'period':'10y','timeframe':'D1'}
    assert 'GC=F' in calls[0][1] and 'BTC-USD' in calls[0][1]
    assert calls[1][2]['source']=='VCI'


def test_workflow_refreshes_before_combined_reports_and_validation():
    text=Path('.github/workflows/scanner-pages-v2.yml').read_text()
    step='python -m filter_pattern.compass_publish --out public/compass'
    assert text.index(step)<text.index('name: Build combined D1 report')
    assert text.index(step)<text.index('name: Build combined H4 report')
    assert text.index(step)<text.index('name: Validate Pages size')
    assert "python -m pip install -e '.[vnstock]'" in text
