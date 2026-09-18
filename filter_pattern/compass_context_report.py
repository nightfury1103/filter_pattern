"""Offline review of context vs price-only walk-forward results."""
from __future__ import annotations

import json
from pathlib import Path


def write_context_report(payload: dict, path: Path) -> None:
    data = json.dumps(payload, ensure_ascii=False, allow_nan=False).replace("<", "\\u003c").replace("&", "\\u0026")
    page = '''<!doctype html><html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>La bàn D1 — bối cảnh liên thị trường</title><style>
:root{font:16px/1.6 system-ui;color-scheme:dark;background:#101923;color:#e5edf7}body{max-width:1200px;margin:auto;padding:26px}h1{font-size:28px}h2{font-size:21px;margin-top:32px}p{max-width:1000px}.muted{color:#adbed0}.notice{background:#292b30;border-left:4px solid #e7b35d;padding:16px}.controls{display:flex;gap:20px;flex-wrap:wrap;margin:22px 0}select{padding:8px;background:#233147;border:1px solid #75899d;border-radius:6px;color:inherit}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:14px}.card{background:#1b2a3b;border-radius:8px;padding:15px}.value{font-size:24px;font-weight:bold}.scroll{overflow:auto}table{border-collapse:collapse;width:100%;font-size:14px}td,th{padding:10px;text-align:left;border-bottom:1px solid #35495e;white-space:nowrap}th{color:#adbed0}svg{width:100%;background:#192636;border-radius:8px}a{color:#81cfff}details{margin-top:20px}li{margin-bottom:8px}.errors{overflow-wrap:anywhere}@media(max-width:600px){body{padding:14px}h1{font-size:23px}.cards{grid-template-columns:1fr 1fr}}
</style><h1>La bàn D1: thêm bối cảnh có giúp dự báo hướng?</h1>
<p class="muted">Độc lập với setup · Mục tiêu chính: hướng sau 10 nến · Kiểm tra tuần tự từng năm</p>
<div class="notice" id="verdict"></div>
<div class="controls"><label>Market <select id="asset"></select></label><label>Kỳ đối chiếu <select id="horizon"><option>10</option><option>5</option><option>20</option></select> nến</label></div>
<p id="source" class="muted"></p><div id="cards" class="cards"></div>
<h2>So sánh trên cùng các ngày từ 2024</h2><div class="scroll"><table><thead><tr><th>Phương pháp</th><th>Đúng / phát hướng</th><th>Accuracy</th><th>Độ phủ</th><th>CI95% theo khối</th><th>Sai hướng</th><th>Mẫu lịch không chồng lấn</th><th>Accuracy lịch đó</th></tr></thead><tbody id="comparison"></tbody></table></div>
<p class="muted">Không có tín hiệu thì accuracy để trống. “Chưa rõ” mọi ngày là độ phủ 0%, không phải thành công. Các ngày phát hướng liên tiếp có thể cùng một đợt thị trường.</p>
<h2>Long và Short riêng — kỳ chính 10 nến</h2><div class="scroll"><table><thead><tr><th>Phương pháp</th><th>Hướng</th><th>Đúng / phát hướng</th><th>Accuracy</th><th>Độ phủ</th><th>CI95%</th></tr></thead><tbody id="sides"></tbody></table></div>
<h2>Độ ổn định qua từng năm — kỳ 10 nến</h2><div class="scroll"><table><thead><tr><th>Năm</th><th>Có bối cảnh: đúng / mẫu</th><th>Accuracy</th><th>Chỉ giá: accuracy</th><th>Quy tắc: đúng / mẫu</th><th>Accuracy</th></tr></thead><tbody id="years"></tbody></table></div>
<h2>Xác suất mô hình ở 180 nến gần nhất</h2><p id="latest" class="muted"></p><p class="muted">Xanh: có bối cảnh · Cam: chỉ giá · Ngưỡng Long 75%, Short 25%. Đây là xác suất ước lượng, không phải accuracy được bảo đảm.</p>
<svg id="probability" viewBox="0 0 1000 240" role="img" aria-label="Xác suất tăng có và không có bối cảnh"></svg>
<h2>Kiểm tra xác suất bằng kết quả thực tế</h2><div class="scroll"><table><thead><tr><th>Phương pháp</th><th>Nhóm P(tăng)</th><th>Số ngày</th><th>P trung bình</th><th>Tăng thực tế</th></tr></thead><tbody id="calibration"></tbody></table></div>
<p id="diagnostics" class="muted"></p>
<details open><summary>Cách kiểm tra và giới hạn</summary><ul>
<li>Nhận hướng sau close T, đo open T+1 tới close T+h. Đúng ở cuối kỳ không bảo đảm giá đi một mạch, không phải tỷ lệ thắng của một setup.</li>
<li>Mỗi market/năm có mô hình riêng: train trước năm liền trước, calibration trong năm liền trước, test năm hiện tại. Loại nhãn vượt ranh giới; không chọn tham số dựa trên test.</li>
<li>Mô hình có/không bối cảnh dùng đúng cùng hàng train/calibration. Thiếu bối cảnh dẫn đến Chưa rõ và vẫn nằm trong mẫu số độ phủ.</li>
<li>Nguồn ngoài lấy ngày nhỏ hơn ngày nến đang xét, tối đa 5 ngày lịch. Proxy ngành Mỹ không phải breadth toàn thị trường hay độ rộng crypto/VN.</li>
<li>Quy tắc xác nhận là giả thuyết cố định, không xuất xác suất 75%. Hai mô hình xác suất giữ ngưỡng 75% qua mọi năm.</li>
<li>Ứng viên hồi cứu cần độ phủ ≥10%, ≥100 tín hiệu trên lịch không chồng lấn và cận dưới CI95% ≥75%. Không tự bật quyền định hướng live. Riêng cửa sổ 2024+ còn ngắn, tối đa mỗi market chỉ có khoảng 70–100 mẫu lịch 10 nến.</li>
<li>Dữ liệu target đã được xem trước đây. Bối cảnh mới và cách chia theo năm không biến lịch sử này thành holdout mới. Cần dữ liệu phát sinh sau khi đóng băng mô hình để xác nhận tương lai.</li>
<li>Giá ETF điều chỉnh hiện tại không phải kho dữ liệu point-in-time; thành phần ngành và chế độ thị trường thay đổi. HYG/IEF là proxy giá, không phải credit spread thuần. Gold futures khác XAUUSD spot.</li>
<li>Chưa đủ dữ liệu VN30/Forex hợp lệ trong cache. SPY không được tính thêm cạnh US500. Chưa có lịch sử RRG đầy đủ để tuyên bố thắng RRG.</li>
</ul></details>
<details><summary>Nguồn bối cảnh</summary><div class="scroll"><table><thead><tr><th>Nguồn</th><th>Provider</th><th>Số nến</th><th>Từ</th><th>Đến</th></tr></thead><tbody id="sources"></tbody></table></div>
<p><a href="https://www.cboe.com/tradable-products/vix/vix-historical-data">Cboe: lịch sử VIX</a> · <a href="https://www.invesco.com/us/financial-products/etfs/product-detail?ticker=RSP">Invesco: RSP</a></p></details>
<p id="errors" class="muted errors"></p><p><a href="results.json">Kết quả đầy đủ</a> · <a href="protocol.json">Quy trình cố định</a> · <a href="data-audit.json">Kiểm tra dữ liệu</a> · <a href="latest-research-snapshot.json">Snapshot nghiên cứu</a></p>
<script id="data" type="application/json">__DATA__</script><script>
const D=JSON.parse(document.getElementById('data').textContent),$=x=>document.getElementById(x),pct=x=>x==null?'—':(100*x).toFixed(1)+'%';
const names={context:'Có bối cảnh',price_only:'Chỉ giá',confirmation:'Quy tắc xác nhận',ema:'EMA20/50',always_long:'Luôn Long — nền'},models=Object.keys(names),sides={LONG:'Long',SHORT:'Short',WAIT:'Chưa rõ'};
function row(parent,values){const r=document.createElement('tr');for(const v of values){const e=document.createElement('td');e.textContent=v;r.append(e)}parent.append(r)}
for(const s of Object.keys(D.history)){const o=document.createElement('option');o.value=s;o.textContent=s;$('asset').append(o)}
const pass=Object.keys(D.history).filter(s=>D.summaries[s].context['10'].ALL.evidence==='retrospective_candidate');
$('verdict').textContent=pass.length?'Ứng viên hồi cứu: '+pass.join(', ')+'. Chưa xác nhận bằng dữ liệu tương lai; RRG giữ nguyên.':'Chưa có market chứng minh được mục tiêu 75% cho mô hình có bối cảnh. Kết quả dưới đây là nghiên cứu hồi cứu; RRG giữ nguyên.';
for(const[s,v]of Object.entries(D.source_metadata))row($('sources'),[s,v.provider,v.bars,v.first||v.first_date,v.last||v.last_date]);
$('errors').textContent='Nguồn bị loại / thiếu: '+Object.entries({...D.target_errors,...D.context_errors}).map(([s,e])=>s+': '+e).join(' · ');
function draw(){const s=$('asset').value,h=$('horizon').value,stats=D.summaries[s],main=stats.context[h].ALL,last=D.latest[s];
$('source').textContent=D.metadata[s].label+' · Mẫu chính từ 2024 · '+D.missing_context_days[s]+' ngày thiếu bối cảnh · Mọi hướng live vẫn chưa được xác nhận.';
$('cards').replaceChildren();for(const[t,v]of [['Có bối cảnh: đúng',pct(main.accuracy)+' ('+main.signals+' ngày)'],['Có bối cảnh: độ phủ',pct(main.coverage)],['Chỉ giá: đúng',pct(stats.price_only[h].ALL.accuracy)+' ('+stats.price_only[h].ALL.signals+' ngày)'],['Quy tắc: đúng',pct(stats.confirmation[h].ALL.accuracy)+' ('+stats.confirmation[h].ALL.signals+' ngày)']]){const e=document.createElement('div');e.className='card';const a=document.createElement('div');a.textContent=t;const b=document.createElement('div');b.className='value';b.textContent=v;e.append(a,b);$('cards').append(e)}
$('comparison').replaceChildren();for(const m of models){const r=stats[m][h].ALL;row($('comparison'),[names[m],r.wins+' / '+r.signals,pct(r.accuracy),pct(r.coverage),r.block_ci95?r.block_ci95.map(pct).join('–'):'Chưa đủ mẫu',r.false_signals,r.scheduled_signals,pct(r.scheduled_accuracy)])}
$('sides').replaceChildren();for(const m of ['context','price_only','confirmation'])for(const side of ['LONG','SHORT']){const r=stats[m]['10'][side];row($('sides'),[names[m],sides[side],r.wins+' / '+r.signals,pct(r.accuracy),pct(r.coverage),r.block_ci95?r.block_ci95.map(pct).join('–'):'Chưa đủ mẫu'])}
$('years').replaceChildren();for(const[y,r]of Object.entries(D.yearly[s]))row($('years'),[y,r.context.wins+' / '+r.context.signals,pct(r.context.accuracy),pct(r.price_only.accuracy)+' ('+r.price_only.wins+'/'+r.price_only.signals+')',r.confirmation.wins+' / '+r.confirmation.signals,pct(r.confirmation.accuracy)]);
$('calibration').replaceChildren();for(const m of ['context','price_only'])for(const b of D.probability_diagnostics[s][m].bins)row($('calibration'),[names[m],b.range.map(pct).join('–'),b.count,pct(b.mean_p_up),pct(b.actual_up)]);
const svg=$('probability');svg.replaceChildren();function shape(t,a){const e=document.createElementNS('http://www.w3.org/2000/svg',t);for(const[k,v]of Object.entries(a))e.setAttribute(k,v);svg.append(e);return e}
for(const p of [.25,.5,.75]){const y=215-p*190;shape('line',{x1:50,x2:975,y1:y,y2:y,stroke:'#65768a','stroke-dasharray':'5 5'});shape('text',{x:2,y:y+4,fill:'#adbed0','font-size':14}).textContent=pct(p)}
const tail=D.history[s].slice(-180);for(const[m,color]of [['context','#7cd7fc'],['price_only','#efb269']]){let points=[];const flush=()=>{if(points.length)shape('polyline',{points:points.join(' '),fill:'none',stroke:color,'stroke-width':2});points=[]};tail.forEach((r,i)=>{const p=r.forecasts[m].p_up;if(p==null){flush();return}points.push((50+i/Math.max(1,tail.length-1)*925)+','+(215-p*190))});flush()}
$('latest').textContent='Target: '+last.date+' · Bối cảnh: '+last.context_date+' · P(tăng) có bối cảnh: '+pct(last.experimental_forecasts.context.p_up)+' · Hướng thử nghiệm: '+sides[last.experimental_forecasts.context.bias]+(last.data_age_days>5?' · DỮ LIỆU CŨ':'');
const diag=D.probability_diagnostics[s],st=D.stability[s].context;$('diagnostics').textContent='Brier (thấp hơn tốt hơn): có bối cảnh '+(diag.context.brier?.toFixed(4)??'—')+'; chỉ giá '+(diag.price_only.brier?.toFixed(4)??'—')+'. Đây là chỉ số tổng hợp, không đo riêng calibration. Mô hình bối cảnh đổi trạng thái '+st.state_switches+' lần; '+st.opposite_within_5_bars+' ngày có hướng đối nghịch trong 5 nến sau.';
}
$('asset').addEventListener('change',draw);$('horizon').addEventListener('change',draw);draw();
</script></html>'''
    from .compass_overview import decorate_compass_overview
    path.write_text(decorate_compass_overview(page.replace("__DATA__", data)), encoding="utf-8")
