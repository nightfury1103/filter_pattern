# Hướng sóng giá D1 — quy tắc trước chạy

Ngày 18/09/2026. Người dùng muốn Long trong sóng tăng và Short trong sóng
giảm. Vòng này tách nhận diện xu hướng đang diễn ra khỏi dự báo return
tương lai. Không dùng kết quả nhìn lại để tô lại màu. RRG và các thử nghiệm
cũ giữ nguyên; đúng bảy mã trong ảnh, XAUUSD vẫn thiếu OHLC spot hợp lệ.

Một cấu hình cho toàn rổ, không tìm tham số: EMA20, ATR14 Wilder, độ dốc
EMA20 qua 3 nến, vùng đệm 0,5 ATR. Sau 200 nến warmup:

- Long khi close > EMA20 + 0,5 ATR và EMA20 > EMA20 cách 3 nến.
- Short khi close < EMA20 − 0,5 ATR và EMA20 < EMA20 cách 3 nến.
- Nếu chưa đủ điều kiện đổi hướng thì giữ hướng trước; ban đầu Chờ.
- Bằng ngưỡng không đổi hướng; ATR bằng 0 thì giữ hướng. Không dùng pivot
  cần nến tương lai, không đặt màu từ đầu sóng đã biết sau này.

Đây là nhận diện xu hướng có độ trễ và có thể giữ hướng cũ quá lâu khi
đảo chiều; không là xác suất thắng. Giữ trạng thái giúp giảm nhiễu nhưng
không khẳng định mọi nhịp điều chỉnh là tiếp diễn. Công thức không được
tối ưu sau khi nhìn biểu đồ BTC.

Đánh giá cùng ngày 2024–2026 với bản analog cập nhật: EMA20/50, hướng analog
mỗi ngày, luôn Long. Giữ kiểm thử chính close T → open T+1 đến close T+10;
5/20 nến phụ, flat sai cả hai. Accuracy, coverage, Long/Short, CI, đổi
trạng thái và đảo hướng trong 5 nến được báo đầy đủ. Nhận diện hướng của
10 nến **đã qua** chỉ là mô tả độ bám sóng, tuyệt đối không gọi là accuracy
dự báo. Báo mô tả này cho các đối chứng cùng kỳ và giữ số dự báo riêng.

UI: biểu đồ la bàn bốn ô phía trên và giá có màu Long/Short phía dưới.
X=(EMA20[T]−EMA20[T−3])/ATR14[T], Y=X[T]−X[T−5]; đây là điểm xu hướng,
không phải P(tăng). Nhãn Long/Short theo quy tắc vùng đệm, không theo
quadrant. Đường giá mặc định tô tín hiệu thật. Không đồng nhất cải thiện
độ bám giá quá khứ với đạt mục tiêu dự báo 75% đã đặt trước đó.

Nguồn giải thích EMA và độ trễ:
[Fidelity](https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/ema).
Tham số vùng đệm là giả thuyết nghiên cứu tự chọn, không là khuyến nghị của
nguồn. Dữ liệu đã xem trước nên vẫn là hồi cứu, không có holdout mới.
