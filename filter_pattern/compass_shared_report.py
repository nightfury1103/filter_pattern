"""Reuse the research layout with explicit shared-model selection provenance."""
from html import escape
from pathlib import Path

from .compass_hybrid_report import write_report as write_base


def overall(payload: dict) -> dict:
    """Descriptive exposure-weighted basket scores; not independent trials."""
    from .compass_shared import weights
    available=payload.get('availability_model','daily')
    rows=[r for a in payload['assets'].values() for r in a['history'] if '10' in r['outcomes'] and r['forecasts'][available]['p_up'] is not None]
    w=weights(rows)
    result={}
    for model in payload['models']:
        selected=[i for i,r in enumerate(rows) if r['forecasts'][model]['bias']!='WAIT']
        correct=[i for i in selected if rows[i]['outcomes']['10']['return_pct']*(1 if rows[i]['forecasts'][model]['bias']=='LONG' else -1)>0]
        total=float(w[selected].sum())
        result[model]={'signals':len(selected),'wins':len(correct),'accuracy':float(w[correct].sum()/total) if total else None,
            'coverage':float(total/w.sum()) if len(w) else 0.,'long':sum(rows[i]['forecasts'][model]['bias']=='LONG' for i in selected),
            'short':sum(rows[i]['forecasts'][model]['bias']=='SHORT' for i in selected)}
    return result


def write_report(payload: dict,path: Path) -> None:
    write_base(payload,path)
    page=path.read_text(encoding='utf-8')
    page=page.replace('La bàn D1: trạng thái giá + RRG','La bàn chung D1: đúng bảy mã trong ảnh')
    page=page.replace('<title>La bàn giá + RRG</title>','<title>La bàn chung D1</title>')
    start=page.index('<select id="model">');end=page.index('</select>',start)+len('</select>')
    options=''.join(f'<option value="{escape(k)}">{escape(v)}</option>' for k,v in payload['chart_models'].items())
    page=page[:start]+'<select id="model">'+options+'</select>'+page[end:]
    rows=[]
    for year,f in payload['shared_folds'].items():
        s=f['selection'];best=s.get('model') or '—';threshold=s.get('threshold')
        trials=s.get('trials',[])
        passing='Đạt sàng lọc validation' if threshold else 'Không đạt → Chưa rõ cả năm test'
        rows.append('<tr>'+''.join('<td>'+escape(str(v))+'</td>' for v in [year,best,threshold if threshold is not None else '—',passing])+'</tr>')
    block='<h2>Một mô hình và ngưỡng chung, chọn trước năm kiểm tra</h2><div class="scroll"><table><thead><tr><th>Năm test</th><th>Ứng viên được chọn</th><th>Ngưỡng</th><th>Kết quả sàng lọc quá khứ</th></tr></thead><tbody>'+''.join(rows)+'</tbody></table></div><p>Chọn bằng năm validation trước test, không có cấu hình riêng cho từng market. Kết quả chẩn đoán của các ứng viên không tự thay thế la bàn chính khi không qua điều kiện sàng lọc. Thiếu XAUUSD spot nên chưa đánh giá đủ cả rổ. Mọi năm test đã được xem ở các vòng trước: chưa có holdout mới.</p><p id="gate" class="notice"></p>'
    page=page.replace('<label>Mô hình biểu đồ',block+'<label>Mô hình biểu đồ')
    stats=overall(payload)
    import json
    (path.parent/'overview.json').write_text(json.dumps(stats,ensure_ascii=False,indent=2),encoding='utf-8')
    overview='<h2>Kiểm tra mục tiêu trên toàn rổ — 10 nến</h2><p>Đánh giá được '+str(len(payload['assets']))+'/7 mã; thiếu vàng spot. Tỷ lệ và độ phủ có trọng số cân bằng phơi nhiễm, US500/SPY mỗi mã nửa trọng số. Số ngày-tài sản dưới đây có tương quan và chồng lấn, không phải mẫu độc lập. Số tổng không thay thế kiểm tra từng mã.</p><div class="scroll"><table><thead><tr><th>Phương án chung</th><th>Tỷ lệ đúng có trọng số</th><th>Độ phủ</th><th>Ngày-tài sản</th><th>Long</th><th>Short</th></tr></thead><tbody>'
    for model,s in stats.items():
        cells=[payload['models'][model],'—' if s['accuracy'] is None else f"{100*s['accuracy']:.1f}%",f"{100*s['coverage']:.1f}%",s['signals'],s['long'],s['short']]
        overview+='<tr>'+''.join('<td>'+escape(str(c))+'</td>' for c in cells)+'</tr>'
    overview+='</tbody></table></div><details><summary>Số liệu kiểm tra từng mã — không có mô hình riêng</summary>'
    page=page.replace('<h2>Hiệu quả trên cùng ngày có đủ bốn dự báo ML</h2>',overview+'<h2>Hiệu quả trên cùng ngày có đủ bốn dự báo ML</h2>')
    page=page.replace('<p><a href="results.json">','</details><p><a href="results.json">')
    page=page.replace('qua 5 quan sát có RRG','qua 5 nến D1')
    page=page.replace('Đuôi 12 quan sát','Đuôi 12 nến')
    page=page.replace('Leading không tự động là Long; cần vượt ngưỡng 75%. Crypto chỉ có quan sát RRG theo lịch nguồn, không đủ bảy ngày/tuần.',
        'Leading không tự động là Long. La bàn chính chỉ đưa hướng khi vượt ngưỡng đã chọn bằng validation; các ứng viên chẩn đoán dùng ngưỡng 75%. Tuần đang chạy bị loại khỏi đặc trưng tuần.')
    page=page.replace('cùng ngày có đủ bốn dự báo ML','cùng ngày có đủ ba dự báo ứng viên')
    page=page.replace('Quy tắc cố định trên toàn kỳ 2024+ và kết quả từng năm','Kết quả từng năm')
    page=page.replace('<p>Phần quy tắc toàn kỳ có cả năm không đủ dữ liệu học ML. Không so trực tiếp tỷ lệ toàn kỳ này với ML ở kỳ ngắn hơn.</p>','')
    page=page.replace('Ngày giá khớp: đúng / tín hiệu','Đúng / tín hiệu trên kỳ chung')
    page=page.replace('<p>Khác feed/phiên giữa OHLC và RRG. Ngày giá khớp loại lệch >1%; không đổi kết quả chính. SPY vẫn dùng benchmark SPY nên RRG không có thông tin; không tự đổi benchmark. Ít đổi trạng thái do luôn WAIT/Long không chứng minh hướng ổn định.</p>',
        '<p>Dùng cùng mô hình cho mọi mã. Các biến tuần chỉ lấy tuần đã đóng trước tuần chứa ngày tín hiệu. US500/SPY mỗi mã nửa trọng số học để giảm đếm đôi. Không có mã thị trường trong đầu vào. Ít đổi trạng thái do luôn WAIT/Long không chứng minh hướng ổn định.</p>')
    page=page.replace("const asof=dates[Number($('range').value)],model=$('model').value;", "const asof=dates[Number($('range').value)],model=$('model').value;const f=D.shared_folds[asof?.slice(0,4)]?.selection;$('gate').textContent='Năm đang xem: '+(asof?.slice(0,4)||'—')+' · '+(f?.threshold?'Ngưỡng đã chọn: '+pct(f.threshold):'Không có ngưỡng qua sàng lọc — la bàn chính Chưa rõ toàn rổ')+(model!=='selected'?' · Bạn đang xem ứng viên chẩn đoán.':'');")
    page=page.replace("+' ngày dự báo · benchmark RRG '+a.benchmark+'. Các năm không đủ train/calibration không nằm trong bảng chính.'", "+' ngày dự báo · một phương pháp chung cho cả rổ. Kết quả từng mã chỉ dùng để kiểm tra, không tạo phương pháp riêng.'")
    path.write_text(page,encoding='utf-8')
