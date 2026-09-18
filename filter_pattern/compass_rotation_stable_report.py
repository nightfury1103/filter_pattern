"""Truthful hysteresis display: real coordinates plus visible confirmation bands."""
from html import escape
from pathlib import Path

from .compass_rotation_report import write_report as write_rotation


def write_report(payload: dict, original_wave: dict, path: Path):
    write_rotation(payload,original_wave,path)
    page=path.read_text(encoding="utf-8")
    replacements={
        "Chu kỳ sóng giá D1 — 4 trạng thái":"Chu kỳ D1 — bản ổn định",
        "Chu kỳ sóng giá D1 — theo nguyên lý RRG":"Chu kỳ sóng giá D1 — giảm nhiễu khi chuyển trạng thái",
        "Giữ điểm xu hướng của bản sóng giá; biểu diễn sức mạnh và thay đổi động lượng bằng bốn trạng thái. Không ép chu kỳ phải đi đủ vòng và không tô lại màu quá khứ.":
            "Làm mượt xu hướng nền và động lượng, giữ trạng thái trong vùng đệm. Chọn bản cũ để so sánh trên cùng mã và ngày. Không tô lại màu quá khứ.",
        '<option value="wave">Chu kỳ xu hướng giá</option>':
            '<option value="wave">Bản ổn định — làm mượt + vùng đệm</option><option value="original">Bản cũ — đổi ô tại 0</option>',
        "Màu đồng bộ giữa đường giá, thẻ và vị trí trên la bàn. X là độ dốc EMA20 theo ATR; Y là thay đổi X qua 5 nến. Đây là chu kỳ xu hướng giá tuyệt đối, không phải sức mạnh so với benchmark.":
            "Màu là trạng thái đã xác nhận; tọa độ vẫn là giá trị thật. Bản ổn định giữ dấu xu hướng trong ±0,10 và dấu động lượng trong ±0,05, nên điểm có thể qua trục nhưng vẫn giữ màu cũ khi còn trong vùng đệm. Bản cũ đổi màu ngay khi qua 0.",
        "stats=(symbol==='ALL'?D:D.assets[symbol]).phase_stats[h]":
            "stats=(symbol==='ALL'?D:D.assets[symbol]).phase_stats_by_model[$('model').value][h]",
        "$('model').onchange=draw;": "$('model').onchange=()=>{draw();phaseStats();};",
        "<span style=\"color:#55dca3\">Leading: tăng, mạnh lên</span>":
            "<span style=\"color:#55dca3\">Leading: xu hướng tăng, động lượng dương đã xác nhận</span>",
        "<span style=\"color:#fb923c\">Weakening: tăng, yếu đi</span>":
            "<span style=\"color:#fb923c\">Weakening: xu hướng tăng, động lượng âm đã xác nhận</span>",
        "<span style=\"color:#f87171\">Lagging: giảm, mạnh thêm</span>":
            "<span style=\"color:#f87171\">Lagging: xu hướng giảm, động lượng âm đã xác nhận</span>",
        "<span style=\"color:#38bdf8\">Improving: giảm, yếu đi</span>":
            "<span style=\"color:#38bdf8\">Improving: xu hướng giảm, động lượng dương đã xác nhận</span>",
        "CENTER:'Trên trục trung tâm'":"CENTER:'Chưa xác nhận'",
        "f.phase==='CENTER'?'Trên trục'":"f.phase==='CENTER'?'Chưa xác nhận'",
    }
    for source,target in replacements.items():
        if source not in page:raise ValueError(f"Rotation template changed: {source}")
        page=page.replace(source,target)
    start=page.index(" $('axes').textContent=");end=page.index(" $('cards').replaceChildren();",start)
    page=page[:start]+''' $('axes').textContent=m==='wave'?'X = EMA5(độ dốc EMA20 qua 3 nến / ATR14); Y = EMA3(thay đổi X qua 5 nến). Dải xám: vùng giữ trạng thái ±0,10 trên X và ±0,05 trên Y. Màu theo dấu đã xác nhận, không dịch tọa độ để ép điểm vào ô cùng màu.':'Bản cũ: X = độ dốc EMA20 qua 3 nến / ATR14; Y = thay đổi X qua 5 nến. Đổi trạng thái tại 0, không có vùng đệm.';
'''+page[end:]
    anchor=" for(let i=-2;i<=2;i++){"
    band=''' if(m==='wave'){
 make('rect',{'class':'confirmation-band',x:x(-.1),y:T,width:x(.1)-x(-.1),height:B-T,fill:'#dce5f0',opacity:.10});
 make('rect',{'class':'confirmation-band',x:L,y:y(.05),width:R-L,height:y(-.05)-y(.05),fill:'#dce5f0',opacity:.10});
 for(const v of [-.1,.1])make('line',{x1:x(v),x2:x(v),y1:T,y2:B,stroke:'#8093ab','stroke-dasharray':'4 5',opacity:.65});
 for(const v of [-.05,.05])make('line',{x1:L,x2:R,y1:y(v),y2:y(v),stroke:'#8093ab','stroke-dasharray':'4 5',opacity:.65});
 }
'''
    if anchor not in page:raise ValueError("Missing grid")
    page=page.replace(anchor,band+anchor,1)
    page=page.replace("const f=r.forecasts[model];$('price-readout').textContent+=' · X '+f.score.toFixed(3)+' · Y '+f.momentum.toFixed(3);",
        "const f=r.forecasts[model];$('price-readout').textContent+=' · X '+f.score.toFixed(3)+' · Y '+f.momentum.toFixed(3)+(f.within_buffer?' · Trong vùng đệm, giữ dấu đã xác nhận':'');")
    def pct(v):return '—' if v is None else f'{100*v:.1f}%'
    def cellrow(cells):return '<tr>'+''.join('<td>'+escape(str(c))+'</td>' for c in cells)+'</tr>'
    table=[]
    for s in [s for _,ss in payload['groups'] for s in ss]:
        a=payload['assets'].get(s)
        if not a:table.append(cellrow([s,'Thiếu dữ liệu']+['—']*7));continue
        before=a['stability']['original']['last180'];after=a['stability']['wave']['last180']
        lag=a['latency'];old=lag['models']['original'];new=lag['models']['wave']
        table.append(cellrow([s,f"{before['changes']} → {after['changes']}",
            f"{before['back_next_day']} → {after['back_next_day']}",
            f"{before['median_run']} → {after['median_run']}",new['events'],
            f"{old['recognized_at_event']} → {new['recognized_at_event']}",
            f"{old['recognized_within10']} → {new['recognized_within10']}",
            f"{old['paired_median_bars']} → {new['paired_median_bars']}",
            lag['paired_median_extra_bars']]))
    old=payload['direction_overview']['original'];new=payload['direction_overview']['wave']
    block='''<section id="stability-comparison"><h2>Giảm nhiễu có làm chậm nhận diện?</h2>
<p>Mỗi ô là <b>bản cũ → bản ổn định</b>. Đổi màu và quay lại ngay hôm sau tính trên 180 nến cuối. Độ trễ tính toàn kỳ từ các lần phá đỉnh/đáy close 20 nến luân phiên; đây là mốc kỹ thuật, không phải đỉnh/đáy thực. Median chỉ dùng sự kiện cả hai bản nhận được trong 10 nến; số bỏ lỡ được thể hiện qua cột nhận được/tổng.</p>
<div class="scroll"><table><thead><tr><th>Mã</th><th>Đổi màu / 180 nến</th><th>Quay lại ngay hôm sau</th><th>Median độ dài đoạn</th><th>Tổng mốc phá vỡ</th><th>Nhận ngay tại mốc</th><th>Nhận được trong 10 nến</th><th>Median trễ, cùng mốc</th><th>Median trễ thêm, từng cặp</th></tr></thead><tbody>'''+''.join(table)+'''</tbody></table></div>
<p id="direction-check">Kiểm tra riêng dấu xu hướng nền với giá sau 10 nến, có trọng số toàn rổ: '''+pct(old['accuracy'])+' → '+pct(new['accuracy'])+'; độ phủ '+pct(old['coverage'])+' → '+pct(new['coverage'])+'''. Đây là chẩn đoán hướng nền, không chuyển bốn màu thành lệnh. Giảm đổi màu không tự chứng minh dự báo tốt hơn.</p></section>'''
    page=page.replace('<h2>Giá diễn biến thế nào sau từng trạng thái?</h2>',block+'<h2>Giá diễn biến thế nào sau từng trạng thái?</h2>')
    page=page.replace('<a href="results.json">','<a href="../compass-rotation-d1/index.html">Bản bốn trạng thái cũ</a> · <a href="results.json">')
    path.write_text(page,encoding="utf-8")
