# La bàn giá + RRG: thí nghiệm giới hạn trước khi chạy

Ngày 17/09/2026. Mục tiêu giữ nguyên: định hướng D1 độc lập setup, đo từ open
T+1 tới close T+10; 5/20 nến là chẩn đoán. Không TP/SL, không đổi RRG/scanner.
Rổ XAUUSD, BTCUSD, ETHUSD, DXY, US500, SPY, E1VFVN30. Không thay vàng spot bằng
futures. Sử dụng cache OHLC và tọa độ RRG thật đã kiểm tra ở vòng trước.

## Các giả thuyết cố định

1. Quy tắc giá: EMA20−EMA50 cùng dấu với return20; efficiency20>=0,2 và
   |close−EMA20|<=2 ATR. Long khi cả hai dương, Short khi cả hai âm, còn lại
   WAIT. Điều kiện efficiency loại thị trường thiếu hướng; giới hạn ATR tránh
   chỉ xác nhận sau khi giá đi quá xa. Đây là giả thuyết, chưa chứng minh.
2. Quy tắc kết hợp: giữ hướng quy tắc giá khi RRG X lệch 100 cùng hướng, hoặc
   dX qua 5 quan sát cùng hướng. Momentum Y chỉ điều chỉnh thông tin hiển thị,
   không tự đảo Long thành Short. SPY so với chính SPY nên tọa độ không có
   thông tin: quy tắc kết hợp WAIT, không đổi benchmark âm thầm.
3. Hai mô hình cố định logistic C=0,1 và cây nông depth=2, 100 vòng,
   learning_rate=0,05, min_leaf=50, L2=10. Mỗi mô hình có hai bộ đầu vào:
   15 đặc trưng giá cũ và bộ đó cộng RRG. Không chọn mô hình thắng trên test.
   Dùng sigmoid calibration C=1 trên năm trước test. Ngưỡng Long>=0,75,
   Short<=0,25; không hạ ngưỡng khi thiếu tín hiệu.

RRG thêm X−100, Y−100, dX1, dY1, dX5, dY5, số ngày lịch từ quan sát trước và
tương tác của X/Y với trend20/50. Tất cả chỉ dùng quan sát đến T. Không
forward-fill ngày thiếu, không nội suy cuối tuần. RRG năm 2024–2026 tải hồi
cứu không bảo đảm dữ liệu nguyên bản tại thời điểm T; không gọi đây là
kiểm chứng live. Mô hình dùng cùng ngày train/calibration/test cho cả hai
bộ đầu vào để đo lợi ích riêng của RRG.

## Phân chia thời gian và giới hạn dữ liệu

Test năm Y trong 2024/2025/2026. Train trước Y−1, calibration năm Y−1,
test năm Y; loại mọi nhãn 10 nến đi qua ranh giới. Cần >=200 train và >=120
calibration, mỗi phần có đủ hai lớp. Không đạt thì bỏ fold ML, không học bằng
test và không tự giảm yêu cầu. Quy tắc cố định vẫn có thể đánh giá riêng.

StockCharts bắt đầu 07/2022, Fialda 12/2023; dự kiến ML thiếu dữ liệu ở các
năm đầu. Không tải thêm để chọn một giai đoạn có kết quả đẹp. Mẫu so sánh
chính chỉ là ngày có dự báo của cả bốn mô hình; báo riêng kết quả quy tắc
2024+ và các fold bị bỏ. Các baseline RRG X/Y, EMA, luôn Long dùng cùng ngày.

Chẩn đoán hướng mỗi ngày P>0,5 / P<0,5 cũng được báo, nhưng không phải thay
thế ngưỡng 75%. Tỷ lệ đúng, số tín hiệu sai, độ phủ, Long/Short, từng năm,
block CI và ngày tín hiệu không chồng lấn theo lịch cố định; không gộp SPY và
US500. Thêm độ nhạy loại ngày giá RRG lệch OHLC >1%. Báo mức quá xa EMA20 và
các baseline trên ngày hai phương pháp cùng đưa hướng.

Tiêu chí bằng chứng giữ nguyên: độ phủ>=10%, >=100 tín hiệu theo lịch 10
nến không chồng lấn, cận dưới CI95%>=75%. Với lịch sử hiện có, không đạt cỡ
mẫu phải ghi thiếu bằng chứng kể cả tỷ lệ điểm >75%. Không gọi xác suất mô
hình là accuracy. Không tối ưu tiếp trên test sau khi có kết quả.

Toàn bộ 2024–2026 đã được xem trước. Đây là nghiên cứu hồi cứu; không có tập
test mới hoàn toàn. Không có mô hình được thăng cấp live. Lưu protocol, hash
input/code, mô hình và kết quả để tái lập, chuẩn bị kiểm chứng tương lai nếu
có ứng viên đủ triển vọng. Không dùng năm 2027 giả hoặc tự tạo dữ liệu mới.
