# Kết quả la bàn hướng D1 — vòng 2, 17/09/2026

## Kết luận

Chưa đạt mục tiêu la bàn định hướng đúng ít nhất 75%. Hai mô hình dự báo
(logistic và cây nông) đều không phát Long/Short ở ngưỡng xác suất 75% sau
khi kiểm tra chất lượng dữ liệu. Độ phủ 0% không đáp ứng nhu cầu định hướng;
không có mẫu phát hướng để tính accuracy. Không coi việc luôn Chưa rõ là
thành công, không hạ ngưỡng hoặc sửa công thức để làm đẹp kết quả này.

Đây là kết quả của hai mô hình và bộ đầu vào đang thử, không chứng minh
mọi cách xây dựng la bàn đều thất bại. Không thay RRG hoặc direction authority.

## Phạm vi và phương pháp

- La bàn độc lập với setup. Không detector, TP hoặc SL.
- Signal tại close T; giá mở T+1 làm mốc; hướng tại close T+10 là mục tiêu.
  Cùng signal được đối chiếu sau 5 và 20 nến. Không đảm bảo đường giá trong kỳ.
- Học trước 2022: 6.380 ngày-tài sản; hiệu chỉnh 2022–2023: 2.912 ngày-tài sản.
  Đây là hàng dữ liệu có tương quan, không phải số phép thử độc lập.
- Đánh giá từ 2024 đến các nhãn hoàn tất trước 17/09/2026. Giá giai đoạn này
  từng xuất hiện trong vòng một: kiểm tra thời gian hồi cứu, không phải holdout mới.
- 6 tài sản: US500, SPY, BTCUSD, ETHUSD, gold futures, DXY. SPY chỉ đối chiếu,
  không tham gia học hoặc gộp với US500. Mẫu gộp chính: 3.971 ngày-tài sản.
- Hai mô hình, tham số và ngưỡng cố định trước chạy; chuẩn hóa chỉ trên train,
  calibration ở giai đoạn riêng; loại nhãn vượt ranh giới; không random split.
- Đầu vào chuẩn hóa theo biến động: đà 1/5/20/60 nến, mức kéo giãn EMA,
  thay đổi trend, vùng giá, biến động và hình dạng nến. Không phụ thuộc setup.

## So sánh tham khảo trên cùng giai đoạn, kỳ 10 nến

Bảng này là mô hình momentum vòng một, được đánh giá lại đúng giai đoạn
2024+ của vòng hai. Gộp Long/Short trên ngày có hướng; các cửa sổ có chồng lấn.
Luôn Long là tỷ lệ tăng trên mọi ngày đủ nhãn, không phải cùng tập được chọn.

| Tài sản | Momentum đúng hướng | Ngày có hướng | Độ phủ | Nền luôn Long |
| --- | ---: | ---: | ---: | ---: |
| US500 | 60,7% | 300 | 44,8% | 63,7% |
| SPY — chỉ đối chiếu | 61,3% | 302 | 45,1% | 63,5% |
| BTCUSD | 54,6% | 271 | 27,7% | 52,3% |
| ETHUSD | 51,7% | 302 | 30,8% | 48,0% |
| Gold futures | 61,7% | 274 | 40,8% | 62,4% |
| DXY | 45,2% | 166 | 24,7% | 49,8% |

Hai mô hình dự báo mới đều phát 0 tín hiệu trong từng tài sản ở ngưỡng 75%.
Sau hiệu chỉnh, P(tăng) của mô hình cây nông nằm khoảng 50,7–54,0% trên
lịch sử đánh giá. Đây là xác suất mô hình, không phải accuracy thực tế.
Chưa có cơ sở kết luận tốt hơn RRG: không có lịch sử RRG tương ứng đầy đủ.

## Đính chính chất lượng dữ liệu

Lần chạy ban đầu có 5 ngày Long liên tiếp ở VN30_ETF với kết quả 5/5 đúng.
Kiểm tra phát hiện nguồn này có khoảng trống **812 ngày**, từ 24/10/2022
đến 13/01/2025, và chuỗi **164 nến OHLC đứng yên**. Năm tín hiệu xuất hiện
ngay đoạn nối. Không được coi đó là bằng chứng 100% hoặc 75% đáng tin.

Đã lưu lần chạy đó với tên `invalid-before-quality-audit.json`, bổ sung kiểm
tra continuity và loại toàn bộ nguồn VN30_ETF; giữ nguyên mô hình/ngưỡng/
chia thời gian rồi chạy lại. Dữ liệu gốc không bị sửa. EURUSD và USDJPY cũng
bị loại vì OHLC sai cấu trúc đã phát hiện từ vòng một.

Các kết quả VN30 trong báo cáo vòng một không còn hợp lệ để kết luận hiệu
quả; đã đánh dấu đính chính trong tài liệu và HTML lưu sẵn. Chưa kiểm nghiệm
được VN30 index hoặc XAUUSD spot chính xác. Kiểm tra cấu trúc và continuity
chưa thay thế đối chiếu nguồn giá độc lập hoặc lịch giao dịch chính thức.

## Kiểm tra và sản phẩm

- 60/60 test liên quan đạt: Compass, forecast, CLI, direction và backtest.
- Báo cáo chạy offline, bộ chọn tài sản/mô hình/5–10–20 nến hoạt động; không
  lỗi JavaScript, không tràn ngang trang ở desktop/mobile.
- Không chạy lại toàn bộ suite trong vòng này. Vòng trước đã xác nhận 6 lỗi
  có sẵn trên Windows; chi tiết trong `market-compass-findings.md`.
- Báo cáo: `reports/compass-forecast-d1/index.html`.
- Kết quả, khoảng bất định, calibration, ổn định, provenance: `results.json`.
- Quy trình và tham số: `protocol.json`; mô hình lưu riêng, scanner không tải.

Bước nghiên cứu tiếp cần giả thuyết và nguồn thông tin bổ sung có lý do,
chẳng hạn breadth hoặc bối cảnh liên thị trường, cùng lịch sử đủ chất lượng.
Không coi việc thử thêm chỉ báo trên cùng tập giá đến khi vượt 75% là xác nhận.
