# La bàn đối chiếu trạng thái lịch sử — quy trình trước chạy

Ngày 17/09/2026. Cùng một phép đối chiếu, K và ngưỡng cho đúng bảy mã trong
ảnh; không cấu hình riêng thị trường, không setup, không TP/SL. Giữ hướng
open T+1 → close T+10, thêm chẩn đoán 5/20. XAUUSD thiếu OHLC spot vẫn chưa
thể kiểm thử; không thay bằng futures. RRG/scanner không thay đổi.

## Giả thuyết mới có giới hạn

Dùng các giai đoạn quá khứ có trạng thái gần giống hiện tại để ước lượng tần
suất tăng, thay cho cây/logistic dự báo đã thử. Không hứa analog sẽ tốt hơn.
Chỉ ba K cố định: 25, 50, 100. Không tìm thêm K/feature sau khi có kết quả.

12 đặc trưng dùng chung: 9 đặc trưng D1 (return20/60 theo ATR, khoảng cách
EMA20, trend20/50, thay đổi trend5, efficiency20, volatility10/60, vị trí
trong range20/60) và 3 đặc trưng tuần đã đóng (trend4/10, thay đổi trend2,
vị trí range13). Không giá tuyệt đối, không tên mã. RobustScaler median/IQR
chỉ fit trên thư viện lịch sử; clip tọa độ chuẩn hóa tại ±5; khoảng cách
Euclidean với trọng số đặc trưng bằng nhau.

Thư viện chỉ giữ mỗi 10 nến theo lịch cố định (index−WARMUP)%10=0 ở từng mã,
nhằm giảm cửa sổ kết quả chồng lấn cùng mã. Các asset vẫn có thể tương quan:
không gọi K hàng xóm là K quan sát độc lập. Mỗi mã có trọng số tổng như nhau,
US500/SPY nửa trọng số mỗi mã. Không có loại mô hình/ngưỡng riêng từng mã.

Vote hàng xóm có trọng số phơi nhiễm, chuẩn hóa tổng trọng số thành K; làm
trơn Laplace (weighted_up+1)/(K+2). Đây là tần suất analog được làm trơn,
không phải xác suất đã được hiệu chỉnh hoặc độ chính xác được bảo đảm.
Không dùng sigmoid để tránh mặc định ép ước lượng về trung bình như một số
cấu hình trước; hiệu quả thực tế phải kiểm tra độc lập.

## Chọn trước năm test

Test Y=2024/2025/2026. Thư viện trước Y−2; chọn K bằng weighted Brier năm Y−2,
chọn ngưỡng trong [.55,.60,.65,.70,.75,.80,.85] trên cùng năm đó. Điều kiện
sàng lọc giữ như vòng chung: accuracy>=75%, coverage>=10%, >=100 tín hiệu,
>=20 Long và >=20 Short. Chọn ngưỡng có độ phủ lớn nhất thỏa điều kiện.

Sau đó xác nhận K/ngưỡng cố định trên năm Y−1; cần vượt cùng điều kiện. Nếu
không đạt ở một trong hai bước, năm test báo WAIT; không chọn lại trên năm
xác nhận hoặc test. Không refit scaler/thư viện sau chọn ngưỡng. Mọi nhãn
train/selection/confirmation phải kết thúc trước giai đoạn kế tiếp. Nhãn
return=0 bỏ khỏi thư viện, giữ trong đánh giá và tính sai cho cả hai hướng.

Báo cả ba K ở ngưỡng .75 và hướng mỗi ngày để kiểm tra thông tin phương pháp;
không dùng chẩn đoán để thay mô hình chính khi gate thất bại. Đánh giá riêng
từng mã ở tầng kiểm tra; trang chính là tổng quan cả rổ, không phân tích các
thị trường thành phần. Baseline EMA và luôn Long dùng cùng ngày.

75% chỉ được coi có bằng chứng nếu độ phủ>=10%, >=100 mẫu lịch cố định và
cận dưới block CI95%>=75%; phải báo thiếu vàng và thiếu cỡ mẫu. Toàn bộ các
năm test đã được xem nhiều lần: vẫn là hồi cứu, không thể tự tạo holdout mới.
Vòng này chốt ba K, không dò tiếp để có số đẹp; lưu thư viện/nguồn/manifest.
