# XAUUSD: sửa cách diễn giải nguồn dữ liệu trong repo

Ngày 18/09/2026. Repo có nguồn giá vàng dùng cho nhãn XAUUSD. Việc nói
“không có dữ liệu XAUUSD” trong các trao đổi trước là quá rộng. Đúng hơn:
các vòng sáu mã đã loại nguồn futures do đặt điều kiện OHLC spot, chứ
repo không hoàn toàn thiếu dữ liệu vàng.

## Đường đi của dữ liệu đã xác nhận

- `filter_pattern/universe.py`: nhãn XAUUSD, link TradingView OANDA:XAUUSD,
  nhưng ticker tải OHLC Yahoo là GC=F.
- `filter_pattern/providers.py`: scanner tải D1 qua `load_yahoo_ohlcv`,
  `auto_adjust=False`. Link TradingView không phải nguồn OHLC tải về.
- `filter_pattern/rrg_dashboard.py`: XAUUSD → `$GOLD` của StockCharts.
  Raw đã lưu chứa 1.057 dòng RRG với price/RS-ratio/RS-momentum, không
  chứa đủ open/high/low để chạy lại mô hình ATR với nhãn open T+1.
- `filter_pattern/scanner.py`: khi nguồn commodity không phù hợp có
  fallback PAXGUSDT/XAUTUSDT, kèm metadata proxy.
- Config có đường dẫn ví dụ `data/XAUUSD_D1.csv`, nhưng file này không
  tồn tại trong checkout đang làm việc. Tương tự file H4.

## Đã lấy và kiểm thử lại nguồn đang dùng trong repo

Tải mới GC=F bằng chính provider hiện tại, `period=10y`, `timeframe=D1`,
`auto_adjust=False`. Giữ cutoff trước 17/09/2026 để so với các vòng cũ.
Nhận 2.512 nến từ 19/09/2016 tới 16/09/2026; OHLC hợp lệ, không có gap
trên 14 ngày, streak zero-range dài nhất 1. Cache cũ cũng có 2.512 nến
GC=F nhưng dùng auto_adjust=True; báo cáo mới dùng bản tải mới theo scanner.

Nguồn lưu ở `reports/compass-gold-repo-d1/source.json`, khai báo proxy
rõ ràng; nghiên cứu dùng nhãn nội bộ GOLD_FUTURES. Không đổi GC=F thành
spot hoặc tuyên bố có OHLC OANDA:XAUUSD.

Chạy các quy tắc cố định của hai vòng gần nhất trên vàng và gộp thử với
sáu mã trước. Không chọn lại ngưỡng hoặc mô hình, không thay RRG/scanner.
Rổ gộp có bảy nguồn đại diện, chưa phải bảy symbol chính xác đều có spot.

| Quy tắc trên vàng | Đúng sau 10 nến | Độ phủ | Mẫu |
|---|---:|---:|---:|
| Bản ổn định | 57,53% | 100% | 671 |
| Xu hướng/momentum cùng chiều | 54,08% | 58,42% | 392 |
| Thêm EMA50 | 59,48% | 45,60% | 306 |
| Thêm giới hạn chạy xa | 70,59% | 5,07% | 34 |
| Hồi về EMA20 | 43,05% | 45,01% | 302 |
| Điều chỉnh theo xu hướng chậm | 77,36% | 7,90% | 53 |
| Hồi phục theo xu hướng chậm | 84,62% | 3,87% | 26 |
| Luôn tăng, đối chứng | 62,44% | 100% | 671 |

Các tỷ lệ vượt 70% riêng vàng vẫn không đạt điều kiện mẫu/độ phủ. Đặc
biệt hồi phục có 26 mẫu đều hướng tăng; điều chỉnh có 52 hướng tăng và
chỉ 1 hướng giảm. Không chứng minh một la bàn nhận diện đúng cả hai phía.

Sau bổ sung vàng futures, accuracy cả rổ: baseline 51,80%; cùng chiều
52,20%; thêm EMA50 53,12%; lọc chạy xa 52,50%; hồi về EMA20 46,01%; điều
chỉnh 51,82%; hồi phục 48,00%. Chưa có bằng chứng cả rổ đạt 70%.

## Báo cáo và kiểm tra

`reports/compass-gold-repo-d1/index.html` có bảng vàng riêng và cả rổ.
JSON có 5/10/20 nến, hai hướng, số mẫu, CI và hash nguồn. 6 kiểm tra prefix
khớp, tính lại 4.016 outcome của hai vòng từ OHLC, đối chiếu số thắng/mẫu,
hash nguồn hợp lệ. Trình duyệt không lỗi hoặc tràn trang mobile.

```powershell
.venv/Scripts/python.exe -X utf8 -m filter_pattern.compass_gold_repo
```

Lệnh dùng cache đã tải; thêm `--refresh` để tải lại bằng provider repo.
Các báo cáo sáu mã cũ giữ nguyên làm lịch sử so sánh. Từ vòng này trở đi
cần phân biệt rõ “có nguồn vàng đại diện” với “có OHLC XAUUSD spot”.
