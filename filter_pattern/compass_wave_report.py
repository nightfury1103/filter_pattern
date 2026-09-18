"""Trend-state compass with genuine Long/Short price colours, no fake probability."""
import json
from html import escape
from pathlib import Path

from .compass_exact import SYMBOLS
from .compass_price_panel import add_price_panel


def write_report(payload: dict, path: Path):
    def pct(v):
        return "—" if v is None else f"{v*100:.1f}%"

    overall = []
    for m, r in payload["overview"].items():
        cells = [payload["models"][m], pct(r["accuracy"]), pct(r["coverage"]), r["signals"], r["long"], r["short"]]
        overall.append('<tr>' + ''.join('<td>'+escape(str(v))+'</td>' for v in cells) + '</tr>')
    detail = []
    for symbol in SYMBOLS:
        a = payload["assets"].get(symbol)
        if not a:
            cells = [symbol, "Thiếu dữ liệu"] + ["—"]*7
        else:
            h = a["summaries"]["wave"];r = h["10"]["ALL"]
            ci = r["block_ci95"]
            cells = [symbol, pct(a["recognition"]["wave"]["agreement"]), pct(h["5"]["ALL"]["accuracy"]),
                     pct(r["accuracy"]), pct(h["20"]["ALL"]["accuracy"]),
                     f'{r["wins"]}/{r["signals"]}', pct(r["coverage"]), ' → '.join(map(pct,ci)) if ci else 'Chưa đủ mẫu',
                     a["stability"]["wave"]["state_switches"]]
        detail.append('<tr>'+''.join('<td>'+escape(str(v))+'</td>' for v in cells)+'</tr>')
    view = {**payload, "price_default_symbol": "BTCUSD", "phase_description": "Sóng giá/EMA: X là điểm xu hướng theo ATR, Y là thay đổi qua 5 nến. Analog: X là điểm tăng so với 50%, Y là thay đổi qua 5 nến cùng thư viện. Quadrant không thay thế hướng Long/Short đã lưu."}
    page = '''<!doctype html><html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>La bàn D1 — hướng sóng giá</title><style>
body{margin:0;padding:20px;background:#0b1220;color:#e0e9f5;font:14px system-ui}main{max-width:1360px;margin:auto}h1{font-size:24px}h2{font-size:19px}p{color:#afc1d8;line-height:1.6}a{color:#73cfff}select{background:#17243b;border:1px solid #526884;color:#e0e9f5;padding:8px;margin:4px}table{width:100%;border-collapse:collapse}td,th{padding:10px;border-bottom:1px solid #2b3d54;text-align:left;white-space:nowrap}th{color:#9db7d5}.scroll{overflow:auto}.notice{background:#302519;border:1px solid #906b35;border-radius:7px;padding:14px}.cards{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:8px;margin-top:15px}.card{border:1px solid #344155;border-radius:6px;padding:10px;background:#111c2c}.card b{display:block;margin-bottom:8px}.asset{margin:5px 0}.asset span{display:block;font-size:12px;margin-top:4px}svg{width:100%;background:#0b1424;border:1px solid #334155;border-radius:6px;margin-top:12px}#range{width:35%;vertical-align:middle}summary{padding:16px 0;cursor:pointer}#scope{font-size:12px}@media(max-width:850px){.cards{grid-template-columns:repeat(3,minmax(0,1fr))}}@media(max-width:500px){body{padding:10px}.cards{grid-template-columns:repeat(2,minmax(0,1fr))}}
</style><main><h1>La bàn D1 — nhận diện hướng sóng giá</h1>
<p>Long khi giá vượt EMA20 + 0,5 ATR và EMA20 dốc lên; Short khi ngược lại. Trong vùng đệm, giữ hướng trước. Một quy tắc cho toàn bộ các mã; màu không được tô lại từ đáy/đỉnh.</p>
<p class="notice">Đây là trạng thái xu hướng, không phải xác suất đúng 75%. Nhận diện sóng đang chạy có thể trễ ở điểm đảo chiều. Khả năng dự báo giá tương lai được kiểm tra riêng phía dưới; RRG gốc giữ nguyên.</p>
<label>Mô hình <select id="model"><option value="wave">Sóng giá EMA20 + vùng đệm ATR</option><option value="ema">EMA20/50 cũ</option><option value="adaptive">Analog cập nhật / hướng mỗi ngày</option></select></label>
<label>Ngày <input id="range" type="range" min="0" step="1"><span id="asof"></span></label>
<div id="cards" class="cards"></div><svg id="compass" viewBox="0 0 1200 520" role="img" aria-label="La bàn xu hướng và thay đổi xu hướng"></svg><p id="axes"></p>
<h2>Kiểm tra mục tiêu trên toàn rổ — 10 nến</h2>
<p>Tỷ lệ dự báo từ open T+1 đến close T+10, cùng ngày 2024–2026. Có trọng số cân bằng tài sản, US500/SPY mỗi mã nửa trọng số. Sáu mã có dữ liệu, XAUUSD chưa kiểm thử. Số tín hiệu có chồng lấn; chưa là dữ liệu mới chưa từng xem.</p>
<div class="scroll"><table><thead><tr><th>Phương án</th><th>Đúng tương lai</th><th>Độ phủ</th><th>Ngày-tài sản</th><th>Long</th><th>Short</th></tr></thead><tbody>__OVERVIEW__</tbody></table></div>
<details><summary>Kiểm tra trên đúng các mã trong ảnh</summary>
<p>“Khớp 10 nến đã qua” chỉ đo mức bám giá hiện tại, không phải dự báo. Các cột sau 5/10/20 nến mới đo hướng tương lai. Chưa xác nhận mục tiêu 75%.</p>
<div class="scroll"><table><thead><tr><th>Mã</th><th>Khớp 10 nến đã qua</th><th>Sau 5 nến</th><th>Sau 10 nến</th><th>Sau 20 nến</th><th>Đúng/tín hiệu 10 nến</th><th>Độ phủ</th><th>CI95% 10 nến</th><th>Đổi trạng thái</th></tr></thead><tbody>__DETAIL__</tbody></table></div></details>
<details><summary>Long/Short, từng năm và đối chứng</summary><label>Mã <select id="detail-symbol"></select></label><div class="scroll"><table><thead><tr><th>Phương án</th><th>Hướng</th><th>Đúng/tín hiệu 10 nến</th><th>Tỷ lệ đúng</th><th>Đảo hướng trong 5 nến</th></tr></thead><tbody id="sides"></tbody></table><table><thead><tr><th>Năm</th><th>Phương án</th><th>Đúng/tín hiệu</th><th>Tỷ lệ đúng</th></tr></thead><tbody id="years"></tbody></table></div></details>
<p><a href="results.json">Kết quả và hash</a> · <a href="protocol.json">Quy tắc cố định</a> · <a href="../compass-adaptive-d1/index.html">Bản analog trước</a> · <a href="../rrg-comparison-d1/index.html">Đối chiếu RRG gốc</a></p></main>
<script>
const D=__DATA__,$=id=>document.getElementById(id),names=D.models,pct=v=>v==null?'—':(100*v).toFixed(1)+'%';
const dates=[...new Set(Object.values(D.assets).flatMap(a=>a.history.map(r=>r.date)))].sort();
$('range').max=dates.length-1;$('range').value=dates.length-1;
const colors={LONG:'#55dca3',SHORT:'#fa789a',WAIT:'#8794aa'};
function draw(){
 const asof=dates[Number($('range').value)],m=$('model').value,paths=[];$('asof').textContent=asof;
 $('axes').textContent=m==='wave'?'X = (EMA20 − EMA20 cách 3 nến) / ATR14; Y = thay đổi X qua 5 nến. Màu đường giá bên dưới là hướng theo vùng đệm, không phải màu quadrant.':m==='ema'?'X = (EMA20 − EMA50) / ATR14; Y = thay đổi X qua 5 nến.':'X = 10 × (điểm tăng − 50%); Y = 10 × thay đổi điểm qua 5 nến. Hướng mỗi ngày là chẩn đoán trên/dưới 50%.';
 $('cards').replaceChildren();
 for(const[group,symbols]of D.groups){
  const card=document.createElement('div');card.className='card';const b=document.createElement('b');b.textContent=group;card.append(b);
  for(const s of symbols){const history=(D.assets[s]?.history||[]).filter(r=>r.date<=asof),last=history.at(-1),f=last?.forecasts[m];
   const el=document.createElement('div');el.className='asset';el.textContent=s;const label=document.createElement('span');label.textContent=f?(f.bias==='WAIT'?'Chờ':f.bias)+' · '+last.date:'Thiếu dữ liệu';label.style.color=colors[f?.bias]||'#8794aa';el.append(label);card.append(el);
   let tail=[];for(const r of history.slice(-12)){const q=r.forecasts[m];if(!Number.isFinite(q.score)||!Number.isFinite(q.momentum)||r.epochs[m]!==last.epochs[m]){tail=[];continue;}tail.push({x:q.score,y:q.momentum});}
   if(tail.length)paths.push({symbol:s,tail,bias:f.bias});
  }$('cards').append(card);
 }
 const svg=$('compass');svg.replaceChildren();const L=70,R=1130,T=30,B=465,CX=600,CY=247.5;
 const xmax=Math.max(.5,...paths.flatMap(a=>a.tail.map(p=>Math.abs(p.x)*1.2))),ymax=Math.max(.2,...paths.flatMap(a=>a.tail.map(p=>Math.abs(p.y)*1.3)));
 const x=v=>CX+v/xmax*530,y=v=>CY-v/ymax*217.5;
 const make=(tag,attrs,parent=svg)=>{const e=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const[k,v]of Object.entries(attrs))e.setAttribute(k,v);parent.append(e);return e;};
 const text=(value,attrs)=>{make('text',attrs).textContent=value;};
 for(const[xx,yy,c]of [[L,T,'#122b43'],[CX,T,'#103326'],[L,CY,'#311a28'],[CX,CY,'#35291d']])make('rect',{x:xx,y:yy,width:530,height:217.5,fill:c});
 for(let i=-2;i<=2;i++){make('line',{x1:x(i*xmax/2),x2:x(i*xmax/2),y1:T,y2:B,stroke:i===0?'#9aaec5':'#293e55'});make('line',{x1:L,x2:R,y1:y(i*ymax/2),y2:y(i*ymax/2),stroke:i===0?'#9aaec5':'#293e55'});text((i*xmax/2).toFixed(2),{x:x(i*xmax/2),y:490,fill:'#9aafc9','text-anchor':'middle','font-size':12});text((i*ymax/2).toFixed(2),{x:60,y:y(i*ymax/2)+4,fill:'#9aafc9','text-anchor':'end','font-size':12});}
 for(const[t,xx,yy]of [['IMPROVING',85,55],['LEADING',1030,55],['LAGGING',85,447],['WEAKENING',1010,447]])text(t,{x:xx,y:yy,fill:'#e0e9f5','font-size':14});
 const defs=make('defs',{});paths.forEach((a,i)=>{const c=['#f5ca62','#47c7ff','#ad92ff','#fca765','#68dba1','#f28db4'][i%6],p=a.tail.at(-1);const marker=make('marker',{id:'wave-arrow'+i,viewBox:'0 0 10 10',refX:9,refY:5,markerWidth:7,markerHeight:7,orient:'auto'},defs);make('path',{d:'M0 0 L10 5 L0 10 Z',fill:c},marker);make('polyline',{points:a.tail.map(p=>x(p.x)+','+y(p.y)).join(' '),fill:'none',stroke:c,'stroke-width':2,opacity:.6});if(a.tail.length>1){const q=a.tail.at(-2);make('line',{x1:x(q.x),y1:y(q.y),x2:x(p.x),y2:y(p.y),stroke:c,'stroke-width':3,'marker-end':'url(#wave-arrow'+i+')'});}make('circle',{cx:x(p.x),cy:y(p.y),r:4,fill:c});text(a.symbol,{x:Math.min(1045,x(p.x)+8),y:y(p.y)-8+(i%2)*18,fill:c,'font-size':14});});
}
for(const s of Object.keys(D.assets))$('detail-symbol').add(new Option(s,s));
function details(){const a=D.assets[$('detail-symbol').value];for(const id of ['sides','years'])$(id).replaceChildren();const row=(id,vs)=>{const tr=document.createElement('tr');for(const v of vs){const td=document.createElement('td');td.textContent=v;tr.append(td);}$(id).append(tr);};for(const m of Object.keys(names))for(const side of ['LONG','SHORT']){const r=a.summaries[m]['10'][side];row('sides',[names[m],side,r.wins+'/'+r.signals,pct(r.accuracy),a.stability[m].opposite_within_5_bars]);}for(const[y,ms]of Object.entries(a.yearly))for(const[m,r]of Object.entries(ms))row('years',[y,names[m],r.wins+'/'+r.signals,pct(r.accuracy)]);}
$('range').oninput=draw;$('model').onchange=draw;$('detail-symbol').onchange=details;draw();details();
</script></html>'''
    page = page.replace('__OVERVIEW__', ''.join(overall)).replace('__DETAIL__', ''.join(detail))
    page = page.replace('__DATA__', json.dumps(view, ensure_ascii=False, allow_nan=False).replace('<', '\\u003c'))
    path.write_text(add_price_panel(page, default_color="signal"), encoding="utf-8")
