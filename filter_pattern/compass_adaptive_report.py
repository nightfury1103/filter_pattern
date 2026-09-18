"""Comparison view for the monthly adaptive analog experiment."""
import csv
from html import escape
from pathlib import Path

from .compass_exact import SYMBOLS
from .compass_shared_report import write_report as write_base
from .compass_price_panel import add_price_panel


def write_report(payload: dict, path: Path) -> None:
    write_base(payload, path)
    page = path.read_text(encoding="utf-8")
    changes = {
        "La bàn chung D1: đúng bảy mã trong ảnh": "La bàn D1: thử nghiệm cập nhật thư viện theo tháng",
        "<title>La bàn chung D1</title>": "<title>La bàn D1 — analog cập nhật</title>",
        "Một mô hình và ngưỡng chung, chọn trước năm kiểm tra": "Xác nhận cùng ngưỡng 75% trước năm kiểm tra",
        "Chọn bằng năm validation trước test, không có cấu hình riêng cho từng market.":
            "Hiệu chỉnh bằng dự báo tuần tự năm Y−2, xác nhận ngưỡng cố định trên Y−1, kiểm tra năm Y. Thư viện cập nhật mỗi tháng theo quy tắc đã chốt; không có cấu hình riêng từng mã.",
        "không nối qua lần học lại đầu năm": "không nối qua lần cập nhật thư viện (mỗi tháng ở bản mới; mỗi năm ở bản cũ)",
        "a.date.slice(0,4)!==b.date.slice(0,4)": "a.epochs[model]!==b.epochs[model]",
        "Leading không tự động là Long. La bàn chính chỉ đưa hướng khi vượt ngưỡng đã chọn bằng validation; các ứng viên chẩn đoán dùng ngưỡng 75%.":
            "Leading không tự động là Long. La bàn chính dùng ngưỡng 75% đã qua xác nhận năm trước. Các ngưỡng 60–80% ở bảng là chẩn đoán, không phải phương án được chọn sau khi xem kết quả.",
        "<th>Train</th><th>Calibration</th>": "<th>Dữ liệu thư viện tháng 1 (sau đó cập nhật)</th><th>Hiệu chỉnh năm Y−2</th>",
        "../compass-exact-d1/index.html": "../compass-analog-d1/index.html",
    }
    for source, target in changes.items():
        if source not in page:
            raise ValueError(f"Report template changed: {source}")
        page = page.replace(source, target)
    note = ('<p class="notice">Giữ K=25 và 12 đặc trưng; thư viện bốn năm gần nhất cập nhật đầu tháng, '
            'chỉ dùng kết quả đã hoàn tất trước tháng. Bản raw là tần suất analog được làm trơn; '
            'bản hiệu chỉnh cũng cần được kiểm chứng, không bảo đảm độ chính xác. '
            'Mọi so sánh dùng cùng ngày và cùng kết quả giá. Không có dữ liệu kiểm thử mới chưa từng xem.</p>')
    page = page.replace('<label>Mô hình biểu đồ', note + '<label>Mô hình biểu đồ')

    def pct(value):
        return "—" if value is None else f"{100*value:.1f}%"

    rows = []
    for symbol in SYMBOLS:
        asset = payload["assets"].get(symbol)
        cells = [symbol]
        if asset:
            summaries = asset["summaries"]
            for model in ("old75", "raw75", "calibrated"):
                r = summaries[model]["10"]["ALL"]
                cells += [pct(r["accuracy"]), f'{r["wins"]}/{r["signals"]}', pct(r["coverage"])]
        else:
            cells += ["Thiếu dữ liệu"] + ["—"] * 8
        rows.append('<tr>' + ''.join('<td>' + escape(str(c)) + '</td>' for c in cells) + '</tr>')
    comparison = ('<details><summary>So sánh bản cũ và bản cập nhật trên các mã trong ảnh — 10 nến</summary>'
                  '<div class="scroll"><table id="comparison"><thead><tr><th>Mã</th>' +
                  ''.join(f'<th>{name}: đúng</th><th>Số đúng/tín hiệu</th><th>Độ phủ</th>'
                          for name in ('Bản cũ', 'Cập nhật tháng', 'Sau hiệu chỉnh')) +
                  '</tr></thead><tbody>' + ''.join(rows) + '</tbody></table></div></details>')
    page = page.replace('<details><summary>Số liệu kiểm tra từng mã', comparison + '<details><summary>Số liệu kiểm tra từng mã')
    page = page.replace('<a href="results.json">', '<a href="comparison.csv">CSV so sánh</a> · <a href="monthly-manifest.json">Lịch cập nhật thư viện</a> · <a href="results.json">')
    path.write_text(add_price_panel(page), encoding="utf-8")
    with (path.parent / "comparison.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["symbol", "model", "horizon", "eligible", "signals", "wins", "accuracy", "coverage", "false_signals", "scheduled_signals", "ci95_low", "ci95_high"])
        for symbol in SYMBOLS:
            asset = payload["assets"].get(symbol)
            if asset is None:
                writer.writerow([symbol, "missing"])
                continue
            for model, horizons in asset["summaries"].items():
                for horizon, sides in horizons.items():
                    r = sides["ALL"]
                    writer.writerow([symbol, model, horizon] + [r[k] for k in (
                        "eligible", "signals", "wins", "accuracy", "coverage", "false_signals", "scheduled_signals")]
                        + (r["block_ci95"] or [None, None]))
