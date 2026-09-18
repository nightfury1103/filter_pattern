"""Four-quadrant view derived from the wave layout, with phase-only semantics."""
import json
from pathlib import Path

from .compass_wave_report import write_report as write_wave_report


def write_report(payload: dict, original_wave: dict, path: Path):
    write_wave_report(original_wave,path)
    page=path.read_text(encoding="utf-8")
    view={**payload,"phase_only":True,"price_default_symbol":"BTCUSD",
          "phase_description":"Màu đồng bộ giữa đường giá, thẻ và vị trí trên la bàn. X là độ dốc EMA20 theo ATR; Y là thay đổi X qua 5 nến. Đây là chu kỳ xu hướng giá tuyệt đối, không phải sức mạnh so với benchmark."}
    start=page.index("const D=")+len("const D=");end=page.index(",$=id=>",start)
    page=page[:start]+json.dumps(view,ensure_ascii=False,allow_nan=False).replace('<','\\u003c')+page[end:]
    replacements={
        "La bàn D1 — hướng sóng giá":"Chu kỳ sóng giá D1 — 4 trạng thái",
        "La bàn D1 — nhận diện hướng sóng giá":"Chu kỳ sóng giá D1 — theo nguyên lý RRG",
        '<p>Long khi giá vượt EMA20 + 0,5 ATR và EMA20 dốc lên; Short khi ngược lại. Trong vùng đệm, giữ hướng trước. Một quy tắc cho toàn bộ các mã; màu không được tô lại từ đáy/đỉnh.</p>':
            '<p>Giữ điểm xu hướng của bản sóng giá; biểu diễn sức mạnh và thay đổi động lượng bằng bốn trạng thái. Không ép chu kỳ phải đi đủ vòng và không tô lại màu quá khứ.</p>',
        '<p class="notice">Đây là trạng thái xu hướng, không phải xác suất đúng 75%. Nhận diện sóng đang chạy có thể trễ ở điểm đảo chiều. Khả năng dự báo giá tương lai được kiểm tra riêng phía dưới; RRG gốc giữ nguyên.</p>':
            '<p class="notice">Vận dụng nguyên lý strength + momentum của RRG lên <b>giá tuyệt đối</b>; không phải JdK RRG so với benchmark. Bốn màu mô tả chu kỳ, không bảo đảm giá tương lai. <a href="https://chartschool.stockcharts.com/table-of-contents/chart-analysis/chart-types/relative-rotation-graphs-rrg-charts">Lý thuyết RRG</a> · <a href="../compass-wave-d1/index.html">So sánh bản hướng sóng trước</a></p><div class="phase-guide"><span style="color:#55dca3">Leading: tăng, mạnh lên</span><span style="color:#fb923c">Weakening: tăng, yếu đi</span><span style="color:#f87171">Lagging: giảm, mạnh thêm</span><span style="color:#38bdf8">Improving: giảm, yếu đi</span></div>',
        '<label>Mô hình <select id="model"><option value="wave">Sóng giá EMA20 + vùng đệm ATR</option><option value="ema">EMA20/50 cũ</option><option value="adaptive">Analog cập nhật / hướng mỗi ngày</option></select></label>':
            '<label>Phương pháp <select id="model"><option value="wave">Chu kỳ xu hướng giá</option></select></label>',
        "const colors={LONG:'#55dca3',SHORT:'#fa789a',WAIT:'#8794aa'};":
            "const colors={LEADING:'#55dca3',WEAKENING:'#fb923c',LAGGING:'#f87171',IMPROVING:'#38bdf8',CENTER:'#8794aa',MISSING:'#536174'};",
        "label.textContent=f?(f.bias==='WAIT'?'Chờ':f.bias)+' · '+last.date:'Thiếu dữ liệu';label.style.color=colors[f?.bias]||'#8794aa';":
            "label.textContent=f?(f.phase==='CENTER'?'Trên trục':f.phase)+' · '+last.date:'Thiếu dữ liệu';label.style.color=colors[f?.phase]||'#8794aa';el.dataset.phase=f?.phase||'MISSING';",
        "paths.push({symbol:s,tail,bias:f.bias})":"paths.push({symbol:s,tail,phase:f.phase})",
        "const c=['#f5ca62','#47c7ff','#ad92ff','#fca765','#68dba1','#f28db4'][i%6],p=a.tail.at(-1);":
            "const c=colors[a.phase],p=a.tail.at(-1);",
        "const defs=make('defs',{});paths.forEach":
            "const occupied=[];const defs=make('defs',{});paths.forEach",
        "text(a.symbol,{x:Math.min(1045,x(p.x)+8),y:y(p.y)-8+(i%2)*18,fill:c,'font-size':14});":
            "const lx=Math.min(1045,Math.max(85,x(p.x)+8));let ly=Math.min(435,Math.max(75,y(p.y)-8));let attempts=0;while(occupied.some(q=>Math.abs(q.x-lx)<100&&Math.abs(q.y-ly)<20)&&attempts++<12)ly=ly+22>435?75:ly+22;occupied.push({x:lx,y:ly});if(Math.abs(ly-y(p.y))>20)make('line',{x1:x(p.x),y1:y(p.y),x2:lx,y2:ly-4,stroke:c,opacity:.5});text(a.symbol,{x:lx,y:ly,fill:c,'font-size':14,'paint-order':'stroke',stroke:'#0b1424','stroke-width':3});",
        "Màu đường giá bên dưới là hướng theo vùng đệm, không phải màu quadrant.":
            "Màu đồng bộ theo bốn ô; đường tâm X=0 và Y=0. Đây không phải JdK RS-Ratio/RS-Momentum.",
    }
    for source,target in replacements.items():
        if source not in page:
            raise ValueError(f"Wave template changed: {source}")
        page=page.replace(source,target)
    start=page.index('<h2>Kiểm tra mục tiêu trên toàn rổ — 10 nến</h2>');end=page.index('</main>',start)
    page=page[:start]+'''<h2>Giá diễn biến thế nào sau từng trạng thái?</h2>
<p>Tỷ lệ tăng/giảm sau 5/10/20 nến là thống kê hồi cứu theo màu tại ngày T, không phải độ chính xác của lệnh. Tính từ open T+1 đến close T+h. Tổng rổ cân bằng trọng số mã, US500/SPY mỗi mã nửa trọng số; số ngày có chồng lấn. XAUUSD thiếu dữ liệu.</p>
<label>Phạm vi <select id="phase-symbol"><option value="ALL">Cả rổ có dữ liệu</option></select></label>
<label>Sau <select id="phase-horizon"><option>5</option><option selected>10</option><option>20</option></select> nến</label>
<div class="scroll"><table><thead><tr><th>Trạng thái tại T</th><th>Số ngày</th><th>Tỷ trọng</th><th>Giá tăng sau đó</th><th>Giá giảm sau đó</th><th>Không đổi</th><th>Return trung bình</th></tr></thead><tbody id="phase-stats"></tbody></table></div>
<p>Improving chưa đồng nghĩa giá đã tăng; Weakening chưa đồng nghĩa giá đã giảm. Không ép các trạng thái quay theo thứ tự cố định. Dữ liệu 2024–2026 đã được xem ở các vòng trước, chưa xác nhận hiệu quả 75%.</p>
<p><a href="results.json">Kết quả và chuyển trạng thái</a> · <a href="protocol.json">Quy tắc cố định</a> · <a href="../compass-wave-d1/index.html">Bản sóng giá trước</a> · <a href="../rrg-comparison-d1/index.html">Đối chiếu RRG gốc</a></p>'''+page[end:]
    start=page.index("for(const s of Object.keys(D.assets))$('detail-symbol')");end=page.index('</script>',start)
    page=page[:start]+'''for(const s of Object.keys(D.assets))$('phase-symbol').add(new Option(s,s));
function phaseStats(){const symbol=$('phase-symbol').value,h=$('phase-horizon').value,stats=(symbol==='ALL'?D:D.assets[symbol]).phase_stats[h];$('phase-stats').replaceChildren();for(const[s,r]of Object.entries(stats)){const tr=document.createElement('tr');tr.dataset.phase=s;for(const v of [s,r.days,pct(r.coverage),pct(r.up_rate),pct(r.down_rate),pct(r.flat_rate),r.mean_return_pct==null?'—':r.mean_return_pct.toFixed(2)+'%']){const td=document.createElement('td');td.textContent=v;tr.append(td);}tr.firstChild.style.color=colors[s];$('phase-stats').append(tr);}}
$('range').oninput=draw;$('model').onchange=draw;$('phase-symbol').onchange=phaseStats;$('phase-horizon').onchange=phaseStats;draw();phaseStats();
'''+page[end:]
    page=page.replace('</style>','[hidden]{display:none!important}.phase-guide{display:flex;gap:16px;flex-wrap:wrap;margin:16px 0;font-size:13px}</style>',1)
    path.write_text(page,encoding="utf-8")
