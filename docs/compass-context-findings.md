# Kết quả la bàn D1 — bối cảnh liên thị trường, 17/09/2026

## Kết luận

Chưa có ứng viên chứng minh tỷ lệ đúng ít nhất 75% với độ phủ hữu ích.
Bối cảnh đang thử chưa cải thiện đủ để đưa la bàn vào vai trò định hướng
giao dịch. RRG và scanner giữ nguyên.

- Có bối cảnh: 57/101 ngày-tài sản đúng = 56,4%, độ phủ 2,5%.
  Trong đó 100 ngày là gold futures; một ngày ETH sai hướng.
- Chỉ giá, cùng cách kiểm tra tuần tự: 82/119 = 68,9%, độ phủ 3,0%.
- Quy tắc xác nhận: 385/809 = 47,6%, độ phủ 20,4%.

Các ngày có tương quan và cửa sổ chồng lấn, không phải giao dịch độc lập.
Không coi tổng gộp là kết quả áp dụng riêng cho mọi market.

## Đã thực hiện

16 nguồn bổ sung: 9 ETF ngành gốc, RSP/SPY, HYG/IEF/TLT, VIX/VIX3M.
DXY lấy từ cache mục tiêu đã kiểm tra; tổng 17 chuỗi tạo 14 đặc trưng
bối cảnh, bổ sung cho 15 đặc trưng giá. Độ tham gia ETF ngành là proxy Mỹ,
không phải breadth toàn bộ cổ phiếu hay độ rộng riêng của crypto/VN.

25 fold market/năm trong 2022–2026. Mỗi market có mô hình riêng: train
trước năm liền trước, hiệu chỉnh trong năm liền trước, test năm đang xét.
Hai mô hình có/không bối cảnh dùng cùng hàng train/calibration; loại nhãn
vượt ranh giới. Công thức, tham số và ngưỡng không đổi sau xem kết quả.

Giá mở T+1 làm mốc, hướng close T+10 là kỳ chính; đối chiếu 5/20 nến.
Bối cảnh chỉ dùng ngày nhỏ hơn ngày target, tối đa 5 ngày lịch. Mẫu chính
2024+ có 3.971 ngày-tài sản đủ nhãn 10 nến và không thiếu bối cảnh.
SPY không được tính thêm cạnh US500.

## Từng market, kỳ 10 nến từ 2024

Mỗi ô: **accuracy / số ngày phát hướng / độ phủ**. Dấu —: không có mẫu phát hướng.

| Market | Có bối cảnh | Chỉ giá | Quy tắc xác nhận |
| --- | --- | --- | --- |
| US500 | — / 0 / 0,0% | 65,6% / 64 / 9,6% | 61,2% / 147 / 22,0% |
| BTCUSD | — / 0 / 0,0% | 100,0% / 2 / 0,2% | 47,3% / 205 / 20,9% |
| ETHUSD | 0,0% / 1 / 0,1% | — / 0 / 0,0% | 44,3% / 192 / 19,6% |
| Gold futures | 57,0% / 100 / 14,9% | 100,0% / 3 / 0,4% | 48,6% / 177 / 26,4% |
| DXY | — / 0 / 0,0% | 70,0% / 50 / 7,5% | 30,7% / 88 / 13,1% |

Gold futures có bối cảnh: CI khối 95% khoảng 32,6–88,1%; chỉ 11 tín hiệu
trên lịch cố định 10 nến. DXY chỉ giá: CI khoảng 45,5–84,2%; 8 tín hiệu
trên lịch cố định. Không trường hợp nào đủ bằng chứng đạt ít nhất 75%.

Các tỷ lệ 100% ở 2 ngày BTC hoặc 3 ngày vàng là mẫu quá nhỏ. Không dùng
để quảng bá độ chính xác. Khoảng bootstrap để trống nếu <30 ngày phát
hướng hoặc mọi outcome giống nhau: resampling không thể suy ra những
thất bại chưa quan sát. Không hiển thị khoảng tin cậy 100–100%.

Brier gộp: có bối cảnh 0,25176; chỉ giá 0,25173 (thấp hơn tốt hơn).
Cải thiện nhỏ ở US500/DXY, xấu hơn BTC/ETH/vàng. Chưa kiểm định chênh lệch
có ý nghĩa thống kê và chưa chứng minh lợi thế giao dịch. Không hạ ngưỡng
75% khi US500 có dự báo cao nhất khoảng 74,5%.

## Chất lượng và giới hạn

- Lưu raw CSV, thời gian tải, checksum và audit cho nguồn bối cảnh.
- Một số high=close sau điều chỉnh giá lệch khoảng một đơn vị số thực máy.
  Cho phép tối đa 8 ULP, giữ nguyên mọi giá, đếm số dòng trong audit.
  Kiểm thử xác nhận sai OHLC có ý nghĩa vẫn bị từ chối.
- VN30_ETF vẫn bị loại vì đứt 812 ngày và chuỗi giá đứng yên. EURUSD,
  USDJPY chưa có nguồn hợp lệ trong cache; không tuyên bố đã test các mã đó.
- ETF điều chỉnh hiện tại không phải kho dữ liệu point-in-time. Phân ngành,
  thành phần ETF và quan hệ liên thị trường thay đổi theo thời gian.
- HYG/IEF không phải credit spread thuần; gold futures không phải XAUUSD spot.
- Target history từng được xem. Nguồn bối cảnh mới và cách kiểm tra tuần tự
  không biến lịch sử thành holdout mới; xác nhận tiếp cần dữ liệu phát sinh mới.
- Chưa có lịch sử RRG đầy đủ để kết luận hơn RRG.

## Kiểm tra và sản phẩm

72/72 test liên quan đạt: features nhân quả, join khác ngày, dữ liệu cũ,
nguồn thiếu, ranh giới nhãn, test không lọt vào train/calibration, quy tắc
Long/Short, độ phủ, sai số số thực, khoảng bất định và escape HTML.

Báo cáo qua kiểm tra 15 tổ hợp market/kỳ đo trên trình duyệt, đối chiếu
số liệu hiển thị, không lỗi JavaScript hoặc tràn ngang desktop/mobile.
Không chạy lại toàn bộ suite; lỗi Windows có sẵn đã ghi ở vòng trước.

- `reports/compass-context-d1/index.html`: báo cáo tương tác.
- `results.json`: từng năm/hướng, calibration, ổn định và lịch dự báo.
- `protocol.json`, `data-audit.json`, `context-sources.json`, `raw-context/`:
  quy trình, dữ liệu nguồn, khả năng chạy lại offline.
- `research-models.joblib`: model đóng băng từng market/năm; scanner không tải.
- `latest-research-snapshot.json`: snapshot nghiên cứu, không phải tín hiệu
  forward được ghi nhận đúng thời điểm có thể vào lệnh.

Giả thuyết và nguồn chính thức: [quy trình vòng 3](compass-context-protocol.md).
