# La bàn analog cập nhật theo thời gian — chốt trước chạy

Ngày 18/09/2026. Phạm vi giữ nguyên XAUUSD, BTCUSD, ETHUSD, DXY, US500,
SPY, E1VFVN30, D1. Một phương pháp cho cả rổ, không setup, không TP/SL.
Không sửa RRG/scanner. XAUUSD chưa có OHLC spot hợp lệ: báo thiếu, không
thay bằng hợp đồng tương lai hoặc dữ liệu giả.

## Giả thuyết và giới hạn thử nghiệm

Bản analog cũ giữ thư viện trước năm Y−2 cho cả năm Y. Vòng này kiểm tra
liệu thư viện cập nhật có cải thiện thông tin định hướng. Chỉ một cấu hình
mới: K=25, đúng 12 đặc trưng và phép chuẩn hóa của vòng trước; cập nhật
đầu mỗi tháng, lấy bốn năm lịch gần nhất. Không dò K, số năm hay đặc trưng.

Tại tháng M, chỉ lấy ngày tín hiệu >= M−4 năm và kết quả 10 nến kết thúc
**trước** M. Vẫn lấy mỗi 10 nến cố định theo từng mã, bỏ nhãn flat trong
thư viện, cân bằng trọng số tài sản (US500/SPY mỗi mã nửa trọng số), ít
nhất 100 đoạn lịch sử. Cập nhật scaler chỉ từ thư viện này. Thư viện giữ
nguyên trong tháng; nhãn test đã hoàn tất được phép dùng ở tháng sau theo
quy tắc định trước, không đổi tham số theo kết quả test. Đây là đánh giá
tuần tự một thuật toán cập nhật, không phải mô hình đóng băng cả năm.

## Điểm số và kiểm chứng xác suất

Vote analog làm trơn không mặc nhiên là xác suất tin cậy. Tạo dự báo
theo tháng từ 2022, rồi dùng dự báo ngoài thư viện của năm Y−2 để fit
sigmoid (logit vote → logistic, C=1, không cân bằng lớp). Chỉ nhãn hoàn
tất trước Y−1 được dùng; cần >=200 ngày và hai lớp. Calibrator cố định
suốt năm xác nhận Y−1 và test Y, không fit lại sau xác nhận.

La bàn chính: điểm đã hiệu chỉnh >=.75 → Long, <=.25 → Short, còn lại WAIT;
chỉ hoạt động trong năm Y nếu năm Y−1 đạt đồng thời accuracy có trọng số
>=75%, coverage>=10%, >=100 ngày-tài sản, >=20 Long và >=20 Short. Không
đạt thì WAIT; không đổi ngưỡng để cứu kết quả. Các ngưỡng raw
.60/.65/.70/.75/.80 và raw/calibrated hướng mỗi ngày chỉ là chẩn đoán
định trước. Không tự chọn dòng đẹp nhất thành la bàn chính.

## Đánh giá

Giữ close T → open T+1 đến close T+10, hướng dấu return; flat tính sai
cả hai hướng. 5/20 nến chỉ chẩn đoán. So sánh bản cũ K25/.75 đã lưu trên
đúng ngày, báo accuracy/coverage, Long/Short, sai, ổn định, từng năm,
block CI và cỡ mẫu lịch cố định. Báo Brier cùng các nhóm điểm tin cậy,
không coi Brier thấp hơn là riêng bằng chứng calibration tốt hơn.

Đánh giá thêm điểm theo Long/Short riêng và các ngày hai phương án cùng
phát hướng. Tỷ lệ 75% vẫn cần độ phủ>=10%, >=100 mẫu lịch cố định, cận
dưới block CI95%>=75%, đủ bảy mã; không hạ tiêu chí. Dữ liệu 2024–2026
đã xem nhiều vòng, nên kết quả vẫn hồi cứu, không phải holdout mới.
Không triển khai bộ lọc giao dịch nếu chưa có bằng chứng.

Lưu tất cả thư viện tháng, calibrator năm, ranh giới nhãn, dự báo,
protocol và hash để tái lập. Kiểm tra rằng thay nhãn tương lai không
thay dự báo quá khứ, và nhãn trước ranh giới mới được phép đi vào fit.

Nguồn phương pháp: [kiểm tra theo thời gian](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html)
và [hiệu chỉnh xác suất](https://scikit-learn.org/stable/modules/calibration.html).
Đây là căn cứ cách kiểm thử, không là bằng chứng lợi thế dự báo tài chính.
