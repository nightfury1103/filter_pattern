"""Standalone, offline Vietnamese research report with causal signal replay."""
from __future__ import annotations

import json
from pathlib import Path


def write_compass_report(payload: dict, output_path: str | Path) -> Path:
    # Escape script boundaries even for user-provided instrument names/metadata.
    encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False).replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    html = TEMPLATE.replace("__PAYLOAD__", encoded)
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    return path


TEMPLATE = r'''<!doctype html>
<html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Market Compass · Nghiên cứu D1</title><style>
:root{font-family:system-ui,sans-serif;color:#e7edf6;background:#0c1220;color-scheme:dark}
*{box-sizing:border-box}body{margin:0}main{max-width:1440px;margin:auto;padding:32px 24px 64px}
h1{font-size:34px;letter-spacing:-1px;margin:10px 0}h2{font-size:19px;margin:0 0 14px}
p{line-height:1.65}.muted,small{color:#a4b2c8}.eyebrow{color:#75b5ff;letter-spacing:2px;font-size:12px}
.notice{border-left:3px solid #e8b755;padding:12px 18px;background:#22202a;line-height:1.7}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(235px,1fr));gap:12px;margin:24px 0}
.card,.panel{border:1px solid #293448;border-radius:12px;background:#131d2e;padding:18px}
.card{cursor:pointer;text-align:left;color:inherit;font:inherit}.card.active{border-color:#75b5ff}
.card strong{font-size:18px;display:block;margin-bottom:7px}.badge{display:inline-block;border-radius:5px;padding:4px 8px;font-size:12px;font-weight:650}
.LONG{background:#143e36;color:#6fe3b1}.SHORT{background:#481f31;color:#ff94ad}.WAIT{background:#333743;color:#c4cedc}
.row{display:flex;gap:15px;align-items:center;flex-wrap:wrap;margin:16px 0}.row label{display:flex;gap:8px;align-items:center}
select,input{font:inherit;background:#172438;border:1px solid #3b4a63;border-radius:5px;padding:7px;color:inherit}
.split{display:grid;grid-template-columns:1.5fr 1fr;gap:16px}.panel{margin-bottom:16px;overflow:hidden}
svg{width:100%;display:block}svg text{fill:#aebcd0;font-size:12px}#date-range{flex:1;min-width:150px}
table{border-collapse:collapse;width:100%;font-size:13px;white-space:nowrap}th,td{padding:11px 10px;border-bottom:1px solid #293448;text-align:right}
th:first-child,td:first-child{text-align:left}th{color:#a8b8cd;font-weight:500}.scroll{overflow:auto}
a{color:#8dbfff}.details{line-height:1.7}details{margin:16px 0}.stats{display:flex;gap:28px;flex-wrap:wrap}.stats b{display:block;font-size:23px}
button:focus-visible{outline:2px solid #fff}footer{margin-top:25px;color:#a4b2c8;font-size:13px}
@media(max-width:850px){.split{grid-template-columns:1fr}main{padding:20px 14px}h1{font-size:27px}}
</style></head><body><main>
<div class="eyebrow">FILTER PATTERN / D1 RESEARCH</div>
<h1>Thị trường đang ủng hộ hướng nào?</h1>
<p class="muted">Long khi hướng tăng đồng thuận. Short khi hướng giảm đồng thuận. Chờ khi chưa rõ hoặc chưa đủ bằng chứng.</p>
<div class="notice">Bản thử nghiệm chọn hướng, chưa tự động lọc setup hoặc thay đổi RRG. Nhãn <b>“Có triển vọng”</b> chỉ là bằng chứng lịch sử sơ bộ; không phải xác suất thắng hay kết quả giao dịch sau phí.</div>
<p id="conclusion"></p>
<p id="period" class="muted"></p><div id="cards" class="grid"></div>
<div class="row"><label>Tài sản <select id="asset"></select></label><label>Mô hình <select id="model">
<option value="multi_horizon">Đồng thuận 20 / 60 / 120</option><option value="ema">EMA20 / EMA50 — mốc so sánh</option><option value="ema_atr">EMA / ATR + thay đổi 5 nến</option></select></label>
<label>Kết quả sau <select id="horizon"><option>5</option><option selected>10</option><option>20</option></select> nến</label></div>
<div class="panel"><h2 id="asset-title"></h2><div class="stats" id="stats"></div><p id="source" class="muted"></p></div>
<div class="panel"><h2>Giá thực tế và hướng được nhận biết tại từng thời điểm</h2>
<p class="muted">Xanh: Long · Đỏ: Short · Xám: Chờ. Mỗi tín hiệu chỉ dùng dữ liệu đã có tại nến đó. Đường giá dùng thang log.</p>
<svg id="price" viewBox="0 0 1000 300" role="img" aria-label="Lịch sử giá và tín hiệu"></svg>
<div class="row"><label for="date-range">Xem đến ngày</label><input id="date-range" type="range" min="200" step="1"><span id="date-label"></span></div>
<p id="historical-state"></p></div>
<div class="split"><div class="panel"><h2>Hướng và thay đổi gần đây</h2><p class="muted">X: điểm hướng · Y: thay đổi điểm sau 5 nến. Đuôi 12 nến; mũi tên là di chuyển đã xảy ra. Trục tự co giãn; không so độ dốc với RRG.</p>
<svg id="compass" viewBox="0 0 550 330" role="img" aria-label="Đuôi Market Compass"></svg></div>
<div class="panel"><h2>RRG hiện tại — đối chiếu riêng</h2><p id="rrg-note" class="muted"></p>
<svg id="rrg" viewBox="0 0 550 330" role="img" aria-label="RRG gốc nếu được cung cấp"></svg>
<p class="muted">RRG giữ benchmark và ngày dữ liệu gốc. Phần này không phải backtest A/B lịch sử.</p></div></div>
<div class="panel"><h2>So sánh ngoài mẫu — không chọn công thức theo kết quả này</h2>
<p id="table-note" class="muted"></p><div class="scroll"><table><thead><tr><th>Mô hình / Hướng</th><th>Bằng chứng 10 nến</th><th>Độ phủ</th><th>Đúng hướng</th><th>Sai hướng</th><th>Mẫu lịch cố định / đúng</th><th>TB có dấu</th><th>Trung vị</th><th>Chênh với nền</th><th>CI 95% chênh</th><th>Bất lợi TB</th></tr></thead><tbody id="metrics"></tbody></table></div>
<p class="muted">Đúng hướng = lợi suất có dấu &gt; 0; bằng 0 tính vào sai. Mẫu hằng ngày chồng lấn. Mẫu lịch cố định cách nhau h nến không chồng lấn trong cùng tài sản, nhưng vẫn có thể phụ thuộc. Chênh với nền = lợi suất chọn lọc trừ luôn giữ cùng hướng trên mọi ngày đủ dữ liệu.</p>
<p id="stability" class="muted"></p><p id="reaction" class="muted"></p></div>
<details class="panel"><summary>Công thức và cách đọc bằng chứng</summary><div class="details">
<p><b>Đồng thuận:</b> log-return 20/60/120 nến, chia cho độ lệch chuẩn log-return 60 nến × √kỳ. Ba hướng phải đồng thuận, điểm trung bình vượt ±0,5 và efficiency 20 nến ≥0,20. Điểm này không phải phần trăm xác suất.</p>
<p><b>EMA/ATR:</b> (EMA20−EMA50)/ATR14 vượt ±0,5, đồng thời thay đổi 5 nến cùng hướng. <b>Mốc EMA:</b> chỉ dùng dấu EMA20−EMA50.</p>
<p><b>Có triển vọng:</b> ở kỳ chính 10 nến, tối thiểu 30 mẫu lịch cố định; cận dưới bootstrap của lợi suất và chênh với nền đều dương; lợi suất trung bình ở cả hai nửa holdout đều dương. Nhiều phép thử chưa hiệu chỉnh; cần kiểm chứng tiếp trên dữ liệu mới và chính setup giao dịch.</p>
<p><b>Chưa chứng minh:</b> đủ mẫu nhưng không đạt toàn bộ tiêu chí trên. <b>Thiếu mẫu:</b> chưa có 30 mẫu theo lịch cố định.</p>
<p>Tín hiệu ở close T, đo từ open T+1 đến close T+h. Loại nhãn phát triển chạm giai đoạn kiểm tra. Không tối ưu lại ngưỡng sau khi xem holdout.</p>
</div></details>
<div id="errors"></div><footer><a href="results.json">Kết quả đầy đủ</a> · <a href="candles.json">Dữ liệu và SHA256</a> · <a href="protocol.md">Quy tắc thử nghiệm</a><p id="limitations"></p></footer>
</main><script id="research-data" type="application/json">__PAYLOAD__</script><script>
'use strict';
const data=JSON.parse(document.getElementById('research-data').textContent);
const $=id=>document.getElementById(id), names={multi_horizon:'Đồng thuận',ema:'EMA cơ bản',ema_atr:'EMA/ATR'};
const evidence={promising:'Có triển vọng',insufficient:'Thiếu mẫu',not_demonstrated:'Chưa chứng minh',no_direction:'Chưa có hướng đồng thuận'};
const colors={LONG:'#55dca3',SHORT:'#fa789a',WAIT:'#69768d'};
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num=(v,d=2)=>v===null||v===undefined?'—':Number(v).toFixed(d);
const pct=v=>v===null||v===undefined?'—':num(v*100,1)+'%';
const symbols=Object.keys(data.assets);
const promising=symbols.flatMap(s=>Object.entries(data.assets[s].models).flatMap(([m,r])=>Object.entries(r.evidence).filter(([side,status])=>status==='promising').map(([side])=>`${s} / ${names[m]} / ${side}`)));
$('conclusion').textContent=promising.length?`Bằng chứng sơ bộ ở kỳ chính 10 nến: ${promising.join('; ')}. Cần xác nhận tiếp trên dữ liệu mới và setup thực tế.`:'Kết luận vòng thử nghiệm: chưa có mô hình / tài sản / hướng nào đạt toàn bộ tiêu chí bằng chứng ở kỳ chính 10 nến. Chưa đủ cơ sở để dùng làm bộ lọc Long/Short bắt buộc.';
$('period').textContent=`D1 hoàn tất trước ${data.before} · Holdout từ ${data.holdout_start} · ${symbols.length} tài sản có dữ liệu · Kỳ đánh giá chính: 10 nến`;
$('asset').innerHTML=symbols.map(s=>`<option value="${esc(s)}">${esc(s)}</option>`).join('');
$('cards').innerHTML=symbols.map(s=>{const a=data.assets[s],b=a.latest.bias;return `<button class="card" data-symbol="${esc(s)}"><strong>${esc(s)}</strong><span class="badge ${b}">${b==='WAIT'?'CHỜ':b}</span><p>${esc(evidence[a.latest.historical_evidence])}</p><small>${esc(a.metadata.last_date)} · ${a.metadata.proxy?'Proxy':'Dữ liệu nguồn'}</small></button>`}).join('');
$('cards').querySelectorAll('button').forEach(b=>b.onclick=()=>{$('asset').value=b.dataset.symbol;update(true)});
$('errors').innerHTML=Object.keys(data.errors).length?'<div class="notice"><b>Dữ liệu không khả dụng — không suy diễn hướng</b><ul>'+Object.entries(data.errors).map(([s,e])=>`<li>${esc(s)}: ${esc(e)}</li>`).join('')+'</ul></div>':'';
$('limitations').textContent=data.limitations.join(' ');
function plotTail(id,points,labelX,labelY){
 const el=$(id),w=550,h=330,cx=275,cy=160;
 if(!points.length){el.innerHTML='<text x="130" y="160">Không có dữ liệu để vẽ</text>';return}
 const sx=205/Math.max(.25,...points.map(p=>Math.abs(p[0]))),sy=110/Math.max(.10,...points.map(p=>Math.abs(p[1])));
 const xy=p=>[cx+p[0]*sx,cy-p[1]*sy];
 let out=`<defs><marker id="arrow-${id}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0 0L10 5L0 10" fill="#81b9ff"/></marker></defs><path d="M45 ${cy}H515 M${cx} 35V290" stroke="#47576e"/><text x="50" y="25">${id==='rrg'?'Improving':'Giảm đang hồi'}</text><text x="365" y="25">${id==='rrg'?'Leading':'Tăng mạnh lên'}</text><text x="50" y="310">${id==='rrg'?'Lagging':'Giảm mạnh lên'}</text><text x="365" y="310">${id==='rrg'?'Weakening':'Tăng đang yếu đi'}</text>`;
 points.slice(1).forEach((p,i)=>{const a=xy(points[i]),b=xy(p),last=i===points.length-2;out+=`<path d="M${a[0]} ${a[1]}L${b[0]} ${b[1]}" stroke="#81b9ff" opacity="${last?1:.18+.5*i/points.length}" stroke-width="${last?3:1.5}" ${last?`marker-end="url(#arrow-${id})"`:''}/>`});
 const last=xy(points.at(-1));out+=`<circle cx="${last[0]}" cy="${last[1]}" r="4" fill="#c9e1ff"/><text x="50" y="285">${esc(labelX)} ${num(points.at(-1)[0])} · ${esc(labelY)} ${num(points.at(-1)[1])}</text>`;el.innerHTML=out;
}
function update(reset=false){
 const symbol=$('asset').value,model=$('model').value,horizon=$('horizon').value,a=data.assets[symbol],m=a.models[model];
 document.querySelectorAll('.card').forEach(c=>c.classList.toggle('active',c.dataset.symbol===symbol));
 $('asset-title').textContent=a.metadata.label;
 const latest=a.history.at(-1)[model],b=a.latest.data_age_days>5?'WAIT':latest.bias;
 $('stats').innerHTML=`<div><small>Hướng mô hình hiện tại</small><b style="color:${colors[b]}">${b}</b></div><div><small>Bằng chứng cho hướng này</small><b style="font-size:17px">${esc(evidence[m.evidence[b]]||'Chưa có hướng')}</b></div><div><small>Độ phủ Long / Short (holdout)</small><b style="font-size:17px">${pct(m.horizons[horizon].holdout.LONG.coverage)} / ${pct(m.horizons[horizon].holdout.SHORT.coverage)}</b></div>`;
 $('source').textContent=`${a.metadata.provider}: ${a.metadata.source} · ${a.metadata.first_date} → ${a.metadata.last_date} · ${a.metadata.bars} nến.${a.latest.data_age_days>5?' DỮ LIỆU CŨ: chỉ xem lịch sử, chờ dữ liệu mới.':''}`;
 $('date-range').max=a.history.length-1;if(reset)$('date-range').value=a.history.length-1;
 const end=Number($('date-range').value),window=a.history.slice(Math.max(200,end-179),end+1),last=window.at(-1);
 $('date-label').textContent=last.date;
 $('historical-state').textContent=`Tại ${last.date}: ${last[model].bias} · Điểm hướng ${num(last[model].score)} · Thay đổi 5 nến ${num(last[model].momentum)} · Efficiency ${num(last[model].efficiency)}. Đây là tín hiệu lịch sử; bằng chứng holdout phía dưới chỉ được tính sau toàn bộ giai đoạn.`;
 const logs=window.map(r=>Math.log(r.close)),lo=Math.min(...logs),hi=Math.max(...logs),span=Math.max(hi-lo,.001),x=i=>60+i*900/Math.max(1,window.length-1),y=v=>260-(v-lo)*220/span;
 let svg='';for(let j=0;j<5;j++){const v=lo+span*j/4;svg+=`<path d="M60 ${y(v)}H965" stroke="#26344a"/><text x="2" y="${y(v)+4}">${num(Math.exp(v),2)}</text>`}
 window.slice(1).forEach((r,i)=>{svg+=`<path d="M${x(i)} ${y(logs[i])}L${x(i+1)} ${y(logs[i+1])}" stroke="${colors[r[model].bias]}" stroke-width="2"/>`});
 svg+=`<text x="60" y="292">${window[0].date}</text><text x="870" y="292">${last.date}</text>`;$('price').innerHTML=svg;
 plotTail('compass',window.slice(-12).map(r=>[r[model].score,r[model].momentum]),'Điểm','Thay đổi');
 const refs=data.rrg_comparison?.reference?.market_representatives||[];
 const map={BTCUSD:'BTCUSDT',ETHUSD:'ETHUSDT',VN30_ETF:'E1VFVN30',GOLD_FUTURES:'XAUUSD'};
 const ref=refs.find(r=>r.symbol===(map[symbol]||symbol));
 const points=(ref?.rrg?.series||ref?.rrg?.rrg_series||[]).map(p=>[Number(p.x)-100,Number(p.y)-100]).filter(p=>p.every(Number.isFinite));
 plotTail('rrg',points.slice(-12),'RS−100','Mom−100');
 const lastRrg=ref?.rrg?.latest||{};
 $('rrg-note').textContent=ref?`RRG snapshot: ${ref.symbol}, benchmark ${ref.rrg?.benchmark||'không rõ'}; nến cuối ${lastRrg.end||lastRrg.start||'không rõ ngày'}; lấy lúc ${data.rrg_comparison.generated_at||'không rõ'}. ${map[symbol]?'Lưu ý: ký hiệu/nguồn giữa hai bảng khác nhau.':''} Không chạy lùi theo thanh thời gian.`:'Chưa cung cấp RRG cho tài sản này. Có thể dùng --rrg-results với results.json hiện có; không tự tạo dữ liệu RRG thay thế.';
 $('table-note').textContent=`${symbol} · Tín hiệu từ ${data.holdout_start} · Kết quả sau ${horizon} nến · Bằng chứng luôn chấm ở kỳ chính 10 nến.`;
 $('metrics').innerHTML=Object.entries(a.models).flatMap(([key,value])=>['LONG','SHORT'].map(side=>{const r=value.horizons[horizon].holdout[side];return `<tr><td>${esc(names[key])} / ${side}</td><td>${esc(evidence[value.evidence[side]])}</td><td>${pct(r.coverage)}</td><td>${pct(r.hit_rate)}<br><small>Nền: ${pct(r.baseline_hit_rate)}</small></td><td>${pct(r.false_direction_rate)}</td><td>${r.scheduled_samples} / ${pct(r.scheduled_hit_rate)}</td><td>${num(r.mean_return_pct)}%</td><td>${num(r.median_return_pct)}%</td><td>${num(r.lift_pct)} đ.%</td><td>${r.lift_ci95?r.lift_ci95.map(v=>num(v)).join(' … '):'—'}</td><td>${num(r.mean_adverse_pct)}%</td></tr>`})).join('');
 const s=m.stability;$('stability').textContent=`${names[model]}: ${num(s.changes_per_100_bars)} lần đổi trạng thái / 100 nến; ${s.opposite_within_5_bars} đợt đảo sang hướng đối diện trong 5 nến; Chờ ${pct(s.wait_coverage)} thời gian. Độ ổn định không tự chứng minh độ chính xác.`;
 const lag=m.reaction_delay;$('reaction').textContent=`Mốc phản ứng: giá đóng cửa phá đỉnh/đáy 20 nến, chỉ đếm khi hướng phá vỡ đổi phía. ${lag.events} sự kiện; nhận đúng hướng trong 10 nến: ${lag.recognized_within_10}; chưa nhận: ${lag.missed_within_10}; độ trễ trung vị của nhóm đã nhận: ${num(lag.median_delay_bars,1)} nến. Mốc này không khẳng định đó là đảo chiều thật.`;
}
$('asset').onchange=()=>update(true);$('model').onchange=()=>update();$('horizon').onchange=()=>update();$('date-range').oninput=()=>update();update(true);
</script></body></html>'''
