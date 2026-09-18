# La bàn hướng D1 độc lập với setup — vòng 2

Ngày 17/09/2026, người dùng chốt: không tập trung TP/SL và không phụ thuộc setup.
La bàn là hướng chính của từng market; setup chỉ đối chiếu hướng đó.
Thiết kế đánh giá phụ thuộc detector trước đây không được triển khai.

Phép thử hiện tại: `filter_pattern/compass_forecast.py`, lệnh `compass-forecast`.

- Dự báo tại close T, đo hướng từ open T+1 đến close T+10; đối chiếu 5/20 nến.
- Long khi xác suất tăng >=75%; Short khi <=25%; còn lại Chưa rõ.
- Hai mô hình cố định: logistic và boosted trees nông; hiệu chỉnh sigmoid
  trên giai đoạn riêng. Không diễn giải điểm EMA/ATR thành xác suất.
- Đầu vào: momentum 1/5/20/60, khoảng cách EMA/ATR, thay đổi trend, volatility,
  vị trí trong vùng giá và hình dạng nến. Không cần setup hoặc nhãn detector.
- Học trước 2022, hiệu chỉnh 2022–2023, đánh giá từ 2024. Loại nhãn vượt ranh
  giới; chuẩn hóa chỉ học trên train; không random split.
- Ngưỡng và tham số cố định trước chạy; không tìm kiếm đến khi có 75%.
- Báo cáo từng market/hướng: accuracy, độ phủ, số ngày sai, mẫu không chồng
  lấn theo lịch độc lập tín hiệu, CI theo khối ngày, calibration và ổn định.
- SPY chỉ đối chiếu nếu đã có US500, không tính hai lần trong học/gộp.
  Bootstrap lấy cùng khối ngày trên các tài sản để giữ tương quan chéo.
- Ứng viên hồi cứu cần cận dưới CI >=75%, >=100 mẫu lịch cố định và độ phủ
  >=10%. Không tự bật quyền định hướng live dù qua các tiêu chí đó.
- Dữ liệu 2024+ đã được xem ở vòng một: đây là kiểm tra thời gian hồi cứu,
  không phải holdout mới chưa từng xem. Xác nhận tiếp cần dữ liệu mới.

75% là tỷ lệ đúng cần chứng minh, không phải bảo đảm cho tương lai. Đi đúng
hướng cuối kỳ không có nghĩa giá không đi ngược trong kỳ, cũng không đồng
nghĩa tỷ lệ thắng giao dịch. RRG và scanner không thay đổi.

Cơ sở hiệu chỉnh xác suất:
https://scikit-learn.org/stable/modules/calibration.html

Kiểm tra chất lượng bổ sung sau lần chạy đầu: loại toàn bộ nguồn nếu có
khoảng trống >14 ngày lịch hoặc >=20 nến liên tiếp có OHLC cùng một giá.
Phát hiện nguồn VN30_ETF bị đứt 812 ngày. Lần chạy đầu bị vô hiệu hóa và lưu
riêng để kiểm toán; công thức, ngưỡng và mốc thời gian không thay đổi khi
chạy lại. Không dùng những ngày lợi nhuận đã biết để sửa nến hoặc chọn đoạn.
