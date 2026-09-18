# Kiểm tra mục tiêu 70% — chốt trước chạy

Ngày 18/09/2026. Giữ nguyên RRG và bản bốn trạng thái ổn định.
Một cấu hình chung cho đúng XAUUSD, BTCUSD, ETHUSD, DXY, US500, SPY,
E1VFVN30; mã thiếu dữ liệu ghi thiếu, không thay tài sản.

Đích chính: dấu return open T+1 → close T+10 trùng dấu xu hướng la bàn
tại close T. Flat là sai. 5/20 nến chỉ chẩn đoán. Không dùng TP/SL/setup.

Ba bộ lọc cố định, lồng nhau; không tìm thêm ngưỡng sau xem kết quả:

1. `aligned`: dấu xu hướng và momentum đã xác nhận cùng chiều (Leading/Lagging).
2. `confirmed`: thêm close và EMA20 ở cùng phía EMA50 với hướng la bàn,
   đồng thời EMA50 tăng/giảm trong 5 nến đúng hướng.
3. `bounded`: thêm abs(close−EMA20)/ATR14 ≤ 1,5 và efficiency20 ≥ 0,25.

Ngày không đạt điều kiện chỉ là không đủ xác nhận, không đổi bốn màu gốc.
So sánh baseline dấu xu hướng mỗi ngày và luôn tăng. Không đổi tham số theo mã.

Chọn trước năm Y: trong năm Y−2 chọn bộ lọc có độ phủ cao nhất trong số
đạt accuracy ≥70%, coverage ≥10%, ít nhất 100 ngày-tài sản, 20 hướng tăng
và 20 hướng giảm. Phải vượt lại đúng cổng trên năm Y−1; nếu không thì
không có bộ lọc đủ điều kiện trong năm Y. Loại nhãn kết thúc sang năm sau
ở cả hai kỳ. Kiểm tra Y=2024/2025/2026; công bố mọi bộ lọc, không chọn lại
theo kết quả Y. Dữ liệu 2024+ đã xem nhiều vòng: đây vẫn là hồi cứu,
không phải holdout mới dù có tách thời gian.

Tổng hợp bằng trọng số cân bằng tài sản; US500/SPY mỗi mã nửa trọng số.
Trọng số tính trên toàn bộ ngày đủ outcome trước khi lọc. Báo riêng hai
hướng, từng mã, từng năm, số sai và độ phủ. Bootstrap 500 lần, block 60
ngày giao dịch hợp nhất, cùng draw ngày cho mọi tài sản.

Cổng bằng chứng hồi cứu: coverage ≥10%, ít nhất 100 tín hiệu ở lịch lấy
mẫu mỗi 10 nến cố định theo từng mã, ít nhất 20 tín hiệu mỗi phía, cận dưới
CI95 ≥70%. Lịch giãn mẫu không khiến tài sản tương quan thành độc lập.
Không tuyên bố đạt trên toàn bộ rổ nếu thiếu một trong bảy mã. Không triển
khai live tự động. Đạt tỷ lệ điểm 70% chưa đồng nghĩa xác suất tương lai 70%.
