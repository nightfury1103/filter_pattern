# La bàn chung cho đúng rổ trong ảnh — vòng thử cố định

Chốt trước khi chạy ngày 17/09/2026. Một mô hình và một ngưỡng dùng chung cho
XAUUSD, BTCUSD, ETHUSD, DXY, US500, SPY, E1VFVN30; không mô hình/ngưỡng riêng
từng mã, không cổ phiếu thành phần, không thêm thị trường. Khung tín hiệu D1.
XAUUSD vẫn thiếu OHLC spot hợp lệ: không thay futures, không tuyên bố đã đạt
đủ bảy mã. Giữ nguyên RRG, scanner và tất cả kết quả nghiên cứu trước.

## Khác biệt so với các vòng trước

Thử thông tin xu hướng chậm hơn từ **tuần đã đóng**, kết hợp giá D1, rồi học
một quan hệ chung giữa trạng thái và kết quả. Các vòng pooled trước chủ yếu
dùng đặc trưng D1 và mô hình nông; không coi pooled tự nó là giả thuyết mới.
Tuần đang chạy bị loại hoàn toàn; không dùng giá cuối tuần tương lai.

Ba ứng viên cố định, không mở rộng sau khi xem kết quả:

- `daily`: HistGradientBoosting, chỉ 15 đặc trưng D1 hiện có.
- `weekly`: cùng mô hình cộng 8 đặc trưng tuần đã đóng.
- `forest`: RandomForest với cùng bộ D1 + tuần.

Hist: max_depth=4, max_leaf_nodes=16, max_iter=150, learning_rate=.04,
min_samples_leaf=100, L2=20, early_stopping=False, random_state=17.
Forest: 200 cây, max_depth=8, min_samples_leaf=50, max_features=.7,
random_state=17, n_jobs=2. Không dùng symbol/market làm feature. Chuẩn hóa
theo ATR/tỷ lệ; không dùng giá tuyệt đối, không học lại theo từng market.

Tuần ISO hoàn tất trước tuần chứa T: lợi suất 1/4/13 tuần chia ATR tuần và
sqrt(h), EMA4−EMA10 chia ATR tuần, thay đổi trend 2 tuần, efficiency13,
vị trí trong vùng 13 tuần và khoảng cách đến EMA4 theo ATR tuần. Crypto tuần
gồm cuối tuần; thị trường nghỉ cuối tuần dùng các phiên có dữ liệu của tuần.

## Thời gian và chọn ngưỡng

Test từng năm 2024/2025/2026. Train trước Y−2, sigmoid calibration năm Y−2,
validation năm Y−1, test năm Y. Mọi nhãn 10 nến phải kết thúc trước giai đoạn
sau. Nến cuối chưa đủ kết quả vẫn giữ dự báo nhưng không tính performance.
Không refit sau validation để tránh đổi thang xác suất/ngưỡng đã chọn.

Mỗi tài sản có tổng trọng số bằng nhau, riêng US500 và SPY mỗi mã một nửa để
tránh đếm đôi cùng phơi nhiễm. Không oversample outcome thắng/thua hoặc dùng
tên mã. Chỉ train/calibration nhận trọng số; báo cáo riêng từng mã và kết quả
tổng có trọng số theo phơi nhiễm, không coi các mã là quan sát độc lập.

Chọn **một** ứng viên cho cả rổ bằng weighted Brier nhỏ nhất trên validation.
Với ứng viên đó, thử đúng lưới ngưỡng [.55,.60,.65,.70,.75,.80,.85] trên
validation, chọn ngưỡng có độ phủ cao nhất thỏa: accuracy có trọng số>=75%,
độ phủ>=10%, >=100 ngày-tài sản có tín hiệu, >=20 Long và >=20 Short. Không
đạt thì model chọn lọc WAIT toàn rổ cho năm test; không chọn bằng test.
Các con số trên chỉ là điều kiện sàng lọc trên validation, chưa đủ bằng chứng
75% thực tế. Ngưỡng không cần bằng .75: xác suất mô hình khác tỷ lệ đúng.

Luôn báo cả ba ứng viên ở ngưỡng .75 và hướng mỗi ngày P>.5/<.5, cùng mô hình
được chọn và trạng thái gate. Các chẩn đoán không tự động thay thế model chính
nếu gate thất bại. Báo EMA và luôn Long trên cùng ngày.

## Tiêu chí và giới hạn

Giữ nguyên hướng open T+1 → close T+10, 5/20 nến đối chiếu, không TP/SL.
Đúng ít nhất 75% phải đi cùng độ phủ hữu ích; báo riêng Long/Short/từng mã để
không che mã yếu bằng tỷ lệ tổng. Bằng chứng nghiêm ngặt vẫn cần coverage>=10%,
>=100 mẫu lịch cố định và cận dưới block CI95%>=75%; không thay đổi mục tiêu
vì lịch sử hiện tại chưa đủ. Thiếu vàng tự nó khiến tiêu chí đủ rổ chưa đạt.

2024–2026 đã được xem nhiều lần: kết quả là hồi cứu, không holdout mới; giới
hạn ba ứng viên giúp quản lý thử nghiệm chứ không xóa rủi ro chọn theo lịch sử.
Không hứa đạt 75%, không tiếp tục dò tham số cho đến khi có kết quả đẹp.
