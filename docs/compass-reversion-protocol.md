# Compass D1: xu hướng chậm và hồi ngắn hạn

Chốt ngày 18/09/2026 trước chạy vòng này. Không thay RRG, la bàn hoặc
setup. Cùng một quy tắc cho XAUUSD/BTCUSD/ETHUSD/DXY/US500/SPY/E1VFVN30.
Thiếu dữ liệu spot thì ghi thiếu, không thay bằng futures.

Giả thuyết: nhịp điều chỉnh có thể cung cấp hướng tương lai tốt hơn tiếp
tục đuổi theo động lượng. Đây là kiểm tra trạng thái thị trường mỗi ngày,
không phải nhận dạng setup, điểm vào lệnh hoặc TP/SL.

Tham khảo ý tưởng phân biệt xu hướng chậm và đảo chiều nhanh:
[Wood và cộng sự, 2021](https://arxiv.org/abs/2105.13727). Vòng này không
tái hiện mạng deep learning của bài báo; các quy tắc dưới đây do dự án
đề xuất. Bài báo không chứng minh accuracy 70% cho rổ hay chân trời này.

## Ba giả thuyết cố định

Tất cả dùng close T, ATR14 Wilder, EMA nhân quả. z=(close−EMA20)/ATR14.
Xu hướng chậm s=+1 nếu close>EMA200 và EMA50[T]>EMA50[T−10]; s=−1 nếu
cả hai bất đẳng thức đảo chiều, còn lại s=0.

1. `reversion`: nếu |z|≥1, hướng = −sign(z), ngược phần giá lệch EMA20;
   đây là đối chứng hồi về trung bình không xét xu hướng chậm.
2. `pullback`: nếu s khác 0 và s*z≤−0,5, hướng=s. Kiểm tra điều chỉnh
   ngược xu hướng chậm, không buộc phải đã bật lại.
3. `recovery`: nếu s khác 0, −1,5≤s*z≤0 và s*(z[T]−z[T−3])>0, hướng=s.
   Kiểm tra hồi phục từ vùng dưới/trên EMA20 theo xu hướng chậm.

Ngoài điều kiện: không đủ xác nhận; không giữ tín hiệu lọc từ ngày trước.
Không tô lại bốn trạng thái gốc, không dùng hướng này làm tọa độ RRG.
Warmup 200. Không chỉnh ngưỡng sau xem kết quả.

## Đánh giá giữ nguyên mục tiêu

Đúng dấu return open T+1 → close T+10; flat là sai. 5/20 nến chẩn đoán.
So với dấu xu hướng bản ổn định, cùng chiều momentum vòng trước và luôn
tăng. Giữ cùng ngày đủ outcome ở mỗi chân trời; coverage trên toàn bộ
ngày đủ dữ liệu. Không đổi định nghĩa đúng để đạt 70%.

Trước năm Y, chọn một trong ba giả thuyết trên năm Y−2 có coverage cao
nhất trong số đạt accuracy≥70%, coverage≥10%, ≥100 ngày-tài sản và ≥20
mẫu mỗi hướng. Cùng giả thuyết phải vượt cổng trên năm Y−1; nếu không,
không chọn cho năm Y. Purge mọi nhãn kết thúc từ đầu năm tiếp theo.
Y=2024/2025/2026. Báo tất cả biến thể, năm, mã và hai hướng.

Trọng số bằng nhau theo tài sản, US500/SPY mỗi mã nửa. Dùng metrics
của vòng confidence70, gồm CI95 bootstrap 500 block resamples, block60
ngày hợp nhất và lịch giãn 10 nến. Không coi các mẫu chồng lấn là độc lập.
Cổng bằng chứng: coverage≥10%, ≥100 mẫu lịch giãn, ≥20 mỗi hướng và
CI95 thấp nhất≥70%. Đủ rổ cần đủ cả bảy mã và từng mã vượt cổng; thiếu
XAU không được coi là đạt toàn rổ.

Đây là vòng nghiên cứu thứ tiếp theo trên dữ liệu đã xem nhiều lần;
tách thời gian không xóa ảnh hưởng của việc thử nhiều giả thuyết.
Không suy rộng điểm số hồi cứu thành xác suất tương lai hoặc triển khai
live. Nếu thấy ứng viên hứa hẹn phải chốt quy tắc và đánh giá bằng dữ liệu
phát sinh sau khi chốt. Không tìm thêm cấu hình trong vòng này.
