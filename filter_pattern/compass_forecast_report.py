"""Standalone Vietnamese review UI for the forecasting experiment."""
from __future__ import annotations

import json
from pathlib import Path


def write_forecast_report(payload: dict, path: Path) -> None:
    encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False).replace("<", "\\u003c").replace("&", "\\u0026")
    page = '''<!doctype html><html lang="vi"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>La bàn hướng D1 — kiểm nghiệm</title>
<style>
:root{color-scheme:dark;font:16px/1.55 system-ui;background:#101721;color:#e3eaf3}body{max-width:1180px;margin:auto;padding:24px}h1{font-size:28px}h2{font-size:21px}p{max-width:950px}.muted{color:#a9b8ca}.notice{border-left:4px solid #edbb63;padding:14px 20px;background:#202632}.controls{display:flex;gap:14px;flex-wrap:wrap;margin:24px 0}select{padding:9px;background:#233043;color:inherit;border:1px solid #53657c;border-radius:5px}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:14px}.card{padding:16px;background:#1b2737;border-radius:8px}.big{font-size:25px;font-weight:650}.scroll{overflow-x:auto}table{width:100%;border-collapse:collapse;font-size:14px}td,th{padding:11px;text-align:left;border-bottom:1px solid #344258;white-space:nowrap}th{color:#a9b8ca}svg{width:100%;height:auto;background:#172231;border-radius:8px}a{color:#80c9ff}summary{cursor:pointer}li{margin:8px 0}@media(max-width:600px){body{padding:14px}h1{font-size:23px}.cards{grid-template-columns:1fr 1fr}}
</style>
<h1>La bàn hướng D1</h1><p class="muted">Định hướng từng market, độc lập với setup · Long / Short / Chưa rõ · Không dùng TP/SL</p>
<div class="notice"><strong id="verdict"></strong><br>Nghiên cứu hồi cứu. Xác suất mô hình không phải cam kết tỷ lệ đúng; RRG và bộ lọc giao dịch vẫn giữ nguyên.</div>
<div class="controls"><label>Tài sản <select id="asset"></select></label><label>Mô hình <select id="model"><option value="boosted">Cây nông — chính</option><option value="logistic">Logistic — đối chứng</option><option value="ema">EMA20/50</option><option value="ema_atr">EMA/ATR + momentum</option><option value="multi_horizon">Momentum 20/60/120</option><option value="always_long">Luôn Long — nền</option></select></label><label>Kỳ đo <select id="horizon"><option>10</option><option>5</option><option>20</option></select> nến</label></div>
<p id="source" class="muted"></p><div class="cards" id="cards"></div>
<h2>Kết quả từng hướng</h2><div class="scroll"><table><thead><tr><th>Hướng</th><th>Đúng / phát hướng</th><th>Tỷ lệ đúng</th><th>Độ phủ</th><th>CI 95% theo khối thời gian</th><th>Mẫu lịch không chồng lấn</th><th>Đúng trên lịch đó</th><th>Nền cùng tỷ trọng hướng</th></tr></thead><tbody id="metrics"></tbody></table></div>
<p class="muted">Ngày liền nhau có kết quả chồng lấn. Lịch cố định lấy mỗi h nến, độc lập tín hiệu; tài sản vẫn có thể tương quan. Khoảng bất định lấy cùng khối ngày cho mọi tài sản. Số ngày phát hướng không phải số cơ hội độc lập.</p>
<h2>Xác suất tăng trong 180 ngày có dữ liệu gần nhất</h2><p id="chartnote" class="muted"></p><svg id="chart" viewBox="0 0 1000 250" role="img" aria-label="Xác suất tăng và ngưỡng Long Short"></svg>
<h2>Mức dự báo có khớp thực tế?</h2><div class="scroll"><table><thead><tr><th>Nhóm P(tăng)</th><th>Số ngày</th><th>Xác suất trung bình</th><th>Tăng thực tế sau 10 nến</th></tr></thead><tbody id="calibration"></tbody></table></div>
<h2>Tính ổn định và nguy cơ đuổi giá</h2><p id="stability"></p>
<details open><summary>Đọc kết quả đúng phạm vi</summary><ul>
<li>Quyết định sau đóng nến T. Long đúng khi close T+10 cao hơn open T+1; Short đúng khi thấp hơn. Đi ngang chính xác tính sai cho cả hai. Hướng ở cuối kỳ không đảm bảo giá đi một mạch.</li>
<li>Học trước 2022, hiệu chỉnh 2022–2023, đánh giá từ 2024. Loại nhãn vượt ranh giới. Kỳ 5/20 kiểm tra cùng dự báo 10 nến, không huấn luyện lại.</li>
<li>Long khi P(tăng) ≥75%; Short khi ≤25%; còn lại Chưa rõ. Không chỉnh ngưỡng theo kết quả đánh giá. Mô hình có thể không phát hướng nào.</li>
<li>Ứng viên hồi cứu cần độ phủ ≥10%, ≥100 tín hiệu trên lịch không chồng lấn và cận dưới CI 95% ≥75%. Vẫn cần dữ liệu mới; chưa bật quyền định hướng live.</li>
<li>Dữ liệu 2024+ đã có trong vòng trước: đây không phải holdout hoàn toàn chưa xem. Hai mô hình và ngưỡng cố định trước lần chạy này.</li>
<li>SPY không tham gia học/gộp khi có US500. BTC và ETH vẫn tương quan. ETF VN30 và gold futures là proxy, không phải VN30 index và XAUUSD spot. Đại diện không chứng minh hiệu quả cho mọi mã thành phần.</li>
<li>Chưa có lịch sử RRG đầy đủ để kết luận thắng RRG. <a href="../compass-d1/index.html">Báo cáo trước: Compass và snapshot RRG</a>.</li>
</ul></details><p id="errors" class="muted"></p><p class="muted"><a href="results.json">Dữ liệu chi tiết</a> · <a href="protocol.json">Quy trình cố định</a></p>
<script id="data" type="application/json">__PAYLOAD__</script>
<script>
const D=JSON.parse(document.getElementById('data').textContent),$=id=>document.getElementById(id);
const pct=x=>x==null?'—':(x*100).toFixed(1)+'%', num=x=>x==null?'—':x.toFixed(2), labels={ALL:'Tổng',LONG:'Long',SHORT:'Short',WAIT:'Chưa rõ'};
for(const s of Object.keys(D.history)){const o=document.createElement('option');o.value=s;o.textContent=s;$('asset').append(o)}
const pooled=document.createElement('option');pooled.value='POOLED';pooled.textContent='Gộp tham khảo (bỏ SPY)';$('asset').append(pooled);
const proven=Object.keys(D.history).filter(s=>D.summaries[s].boosted['10'].ALL.evidence==='retrospective_candidate');
$('verdict').textContent=proven.length?'Ứng viên hồi cứu: '+proven.join(', ')+' — chưa xác nhận forward.':'Chưa chứng minh được mục tiêu đúng hướng ít nhất 75% cho mô hình chính.';
$('errors').textContent='Nguồn bị loại: '+Object.entries(D.errors).map(([k,v])=>k+': '+v).join(' · ');
function cellRow(parent,values){const tr=document.createElement('tr');for(const val of values){const td=document.createElement('td');td.textContent=val;tr.append(td)}parent.append(tr)}
function draw(){const s=$('asset').value,m=$('model').value,h=$('horizon').value,stats=D.summaries[s][m][h],a=stats.ALL;
$('source').textContent=s==='POOLED'?'Tổng gộp chỉ tham khảo; xem từng tài sản và Long/Short riêng.':D.metadata[s].label+' · '+D.metadata[s].first_date+' → '+D.metadata[s].last_date+' · '+(D.excluded_from_fit_and_pool.includes(s)?'Không tham gia học/gộp':'Có tham gia học');
$('cards').replaceChildren();for(const [title,val] of [['Đúng hướng',pct(a.accuracy)],['Thời gian có hướng',pct(a.coverage)],['Ngày phát hướng',String(a.signals)],['Ngày sai hướng',String(a.false_signals)]]){const e=document.createElement('div');e.className='card';const t=document.createElement('div');t.textContent=title;const v=document.createElement('div');v.className='big';v.textContent=val;e.append(t,v);$('cards').append(e)}
$('metrics').replaceChildren();for(const side of ['ALL','LONG','SHORT']){const r=stats[side];cellRow($('metrics'),[labels[side],r.wins+' / '+r.signals,pct(r.accuracy),pct(r.coverage),r.block_ci95?r.block_ci95.map(pct).join(' – '):'Chưa đủ mẫu',r.scheduled_signals,pct(r.scheduled_accuracy),pct(r.side_mix_baseline)])}
const diag=D.probability_diagnostics[s]?.[m];$('calibration').replaceChildren();if(diag){for(const b of diag.bins)cellRow($('calibration'),[b.range.map(pct).join(' – '),b.count,pct(b.mean_p_up),pct(b.actual_up)])}else cellRow($('calibration'),['Đối chứng không xuất xác suất','—','—','—']);
const rows=s==='POOLED'?[]:D.history[s].slice(-180),svg=$('chart');svg.replaceChildren();function shape(tag,attrs){const e=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const[k,v]of Object.entries(attrs))e.setAttribute(k,v);svg.append(e);return e}
if(rows.length&&diag){for(const p of [.25,.5,.75]){const y=220-p*190;shape('line',{x1:50,x2:970,y1:y,y2:y,stroke:'#65758a','stroke-dasharray':'5 5'});shape('text',{x:3,y:y+5,fill:'#a9b8ca','font-size':14}).textContent=pct(p)}const points=rows.map((r,i)=>(50+i/Math.max(1,rows.length-1)*920)+','+(220-r.forecasts[m].p_up*190)).join(' ');shape('polyline',{points,fill:'none',stroke:'#7dd3fc','stroke-width':2});const last=rows.at(-1),current=D.latest[s];$('chartnote').textContent=rows[0].date+' → '+last.date+' · P(tăng) mới nhất: '+pct(last.forecasts[m].p_up)+' · Hướng thử nghiệm: '+labels[last.forecasts[m].bias]+(current.display_state==='STALE'?' · DỮ LIỆU CŨ':'')+' · Hướng đã xác nhận: chưa có.'}else{$('chartnote').textContent='Chọn một tài sản và mô hình dự báo để xem đồ thị xác suất.'}
const st=D.stability[s]?.[m];$('stability').textContent=(st?'Trong '+st.days+' ngày: đổi trạng thái '+st.state_switches+' lần; hướng ngược trong 5 nến sau '+st.opposite_within_5_bars+' ngày phát hướng. ':'')+'Cách EMA20 trung bình khi phát hướng: '+num(a.mean_abs_extension_at_signal)+' ATR; tỷ lệ cách trên 2 ATR: '+pct(a.extended_over_2atr_fraction)+'. Đây là mức kéo giãn giá, không phải độ trễ tính từ đáy/đỉnh đã biết trước.';
}
for(const id of ['asset','model','horizon'])$(id).addEventListener('change',draw);draw();
</script></html>'''
    path.write_text(page.replace("__PAYLOAD__", encoded), encoding="utf-8")
