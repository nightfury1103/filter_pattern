# Kết quả Market Compass D1 — vòng đầu, 17/09/2026

> Đính chính sau kiểm tra vòng 2: nguồn VN30_ETF có khoảng trống 812 ngày
> (24/10/2022 → 13/01/2025) và nhiều nến giá đứng yên. Các số liệu VN30_ETF
> bên dưới không hợp lệ để kết luận hiệu quả; bảng được giữ làm lịch sử kiểm
> toán. Vòng 2 loại toàn bộ nguồn này và bổ sung kiểm tra continuity. OHLC
> đúng cấu trúc chưa đủ chứng minh lịch sử đầy đủ hoặc có thể giao dịch.

## Kết luận

Chưa có mô hình/tài sản/hướng nào vượt toàn bộ tiêu chí bằng chứng đã định
trước tại kỳ chính 10 nến. Chưa có cơ sở để bật bộ lọc bắt buộc chỉ tìm Long
hoặc chỉ tìm Short. Không thay đổi RRG, detector hoặc direction authority.

Điều này không chứng minh mọi phương pháp trend đều vô ích. Nó cho thấy ba
công thức đang thử chưa đủ bằng chứng để đảm nhận vai trò người dùng yêu cầu.
Không điều chỉnh ngưỡng để làm đẹp chính giai đoạn kiểm tra này.

## Đã thực hiện

- Ba mô hình cố định: EMA20/50, EMA/ATR + thay đổi 5 nến, đồng thuận momentum
  20/60/120 nến chuẩn hóa biến động với bộ lọc efficiency.
- 7 tài sản có dữ liệu hợp lệ; yêu cầu lịch sử 10 năm nhưng công bố độ dài
  thực tế riêng từng tài sản. Điểm chia ngoài mẫu chung: 02/11/2023.
- Nến giá trước 17/09/2026; tín hiệu tại close T, đo open T+1 đến close T+h.
- Đánh giá 5/10/20 nến, tách Long/Short; độ phủ, tỷ lệ sai, lợi suất có dấu,
  diễn biến bất lợi/thuận lợi, số lần đổi trạng thái và độ trễ tham chiếu.
- Dữ liệu RRG đại diện được tải qua đúng logic hiện có cho 7 đại diện.
  Snapshot này chỉ phục vụ đối chiếu trực quan, không phải backtest RRG dài hạn.
- Báo cáo HTML tiếng Việt chạy offline, có bộ chọn tài sản/mô hình/kỳ kết quả,
  thanh xem lại lịch sử, đuôi Compass và RRG cạnh nhau.

## Một số kết quả của mô hình đồng thuận, kỳ 10 nến

Tỷ lệ đúng bên dưới tính trên các ngày phát tín hiệu (cửa sổ kết quả có
chồng lấn). Cột mẫu theo lịch cố định giúp thấy lượng quan sát không chồng
lấn nhỏ hơn nhiều. Các tài sản không được gộp thành một tỷ lệ thắng chung.

| Tài sản | Long đúng | Nền luôn Long | Short đúng | Mẫu lịch cố định Long / Short |
| --- | ---: | ---: | ---: | ---: |
| US500 / S&P 500 index | 66,0% | 64,9% | 25,0% | 30 / 3 |
| SPY ETF | 66,3% | 64,7% | 20,8% | 30 / 3 |
| E1VFVN30 ETF proxy | 56,9% | 62,0% | 20,0% | 12 / 6 |
| BTC/USD spot | 62,1% | 53,8% | 44,9% | 17 / 11 |
| ETH/USD spot | 56,7% | 49,6% | 48,7% | 19 / 18 |
| Gold futures proxy | 61,7% | 62,4% | 57,9% | 24 / 2 |
| US Dollar Index | 40,7% | 48,9% | 47,3% | 7 / 10 |

US500 Long có lợi suất trung bình +0,655% so với nền +0,766%: tỷ lệ đúng
khá cao nhưng chưa chứng minh lợi ích chọn lọc. BTC Long có trung bình
+3,053% so với nền +1,034%, nhưng CI bootstrap 95% của chênh lệch khoảng
[-0,98; +4,41] điểm phần trăm, vẫn bao gồm 0. Không gọi đây là lợi thế đã
được xác nhận. Tất cả là kết quả hướng giá, không phải P&L của setup sau phí.

## Giới hạn dữ liệu

- EURUSD và USDJPY bị loại vì nguồn Yahoo có OHLC không nhất quán trong
  lịch sử. Không sửa nến hoặc âm thầm bỏ ngày lỗi để tạo kết quả đẹp hơn.
- ETF VN30 không phải chỉ số VN30; gold futures không phải XAUUSD spot;
  BTC/ETH spot không phải hợp đồng perpetual. Nhãn nguồn ghi rõ trong UI.
- Lịch sử thành phần thị trường/breadth chưa được kiểm tra. Kết quả một
  đại diện không chứng minh bộ lọc đó hoạt động cho mọi mã trong thị trường.
- Chưa đánh giá chính các setup, entry, stop, target, phí và funding.
- Holdout đã được xem; các thay đổi công thức sau này phải được công bố là
  nghiên cứu tiếp theo, kiểm tra trên dữ liệu khác hoặc forward test.

## Kiểm tra kỹ thuật

- 18 test Compass đạt: chống nhìn trước, đối xứng hướng, bất biến đơn vị giá,
  giá sai, nến chưa đóng, cách tính Short, next-open, tách thời gian, baseline,
  độ trễ, replay, provenance, RRG snapshot và escape HTML.
- 43 test liên quan Compass, CLI và direction đạt.
- Chạy toàn bộ suite bằng Python UTF-8: 229 đạt, 6 lỗi. Cả 6 lỗi được tái
  hiện trên bản HEAD gốc: 5 lỗi đường dẫn ảnh trên Windows, 1 lỗi SIGALRM của
  VNStock trên Windows. Không phải lỗi mới từ Compass. Lần full-suite này
  diễn ra trước khi thêm test độ trễ thứ 18; nhóm liên quan đã chạy lại.
- Brave headless: kiểm tra bộ chọn, slider, bảng số liệu, RRG và kích thước
  desktop/mobile; không có JavaScript error hoặc tràn ngang toàn trang.

## Tái lập

```powershell
.venv\Scripts\python.exe -X utf8 -m filter_pattern.cli compass-research `
  --cache reports/compass-d1/candles.json `
  --rrg-results reports/compass-d1/rrg-snapshot.json `
  --before 2026-09-17 `
  --out reports/compass-replay
```

`results.json` chứa toàn bộ thống kê và hash mã triển khai; `candles.json`
chứa dữ liệu, nguồn và hash từng chuỗi; `protocol.md` lưu quy tắc thử nghiệm.
Các artifact nằm trong thư mục `reports/compass-d1`, được gitignore theo
quy ước dự án. Mã nguồn và hai tài liệu nghiên cứu là phần thay đổi cần lưu.
