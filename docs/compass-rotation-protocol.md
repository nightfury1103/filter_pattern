# Chu kỳ sóng giá theo bốn trạng thái — trước chạy

Giữ đúng điểm xu hướng của bản sóng giá, không tối ưu lại: X bằng thay đổi
EMA20 qua 3 nến chia ATR14; Y=X[T]−X[T−5]. Chuyển biểu diễn từ hướng nhị
phân sang Leading (X>0,Y>0), Weakening (X>0,Y<0), Lagging (X<0,Y<0),
Improving (X<0,Y>0). Nếu trên một trục, hiển thị trung tính; thiếu điểm thì
thiếu dữ liệu. Không ép chuỗi trạng thái phải đi đủ vòng; có thể quay lại
ô trước hoặc bỏ qua ô. Không làm trơn thêm hoặc tô lại quá khứ.

Đây là ứng dụng nguyên lý strength + momentum lên xu hướng giá tuyệt đối,
không là JdK RS-Ratio/RS-Momentum và không đo vượt benchmark. RRG gốc và
bản Long/Short cũ không thay đổi. Bốn trạng thái không được quy đổi ngầm
thành lệnh: Weakening vẫn có xu hướng tăng, Improving vẫn có xu hướng giảm.

Đúng bảy mã trong ảnh; chỉ sáu mã có dữ liệu. Thẻ, đuôi, mũi tên, đường giá
và dòng thông tin dùng chung một trạng thái đã tính từ dữ liệu tới ngày T.
Mặc định BTC, lịch sử 180 nến; có chọn mã, ngày và khoảng xem như bản trước.
Không hiện Long/Short trong bản này.

Đánh giá phân bố return open T+1 → close T+5/10/20 theo từng trạng thái,
không tự gán cả bốn trạng thái là dự báo tăng hoặc giảm rồi báo accuracy.
Tổng hợp trọng số cân bằng mã (US500/SPY mỗi mã nửa trọng số), công bố số
ngày, xác suất thực nghiệm tăng/giảm/flat và return trung bình theo nhóm.
Chi tiết từng mã và chuyển trạng thái được lưu. Đây là mô tả hồi cứu trên
dữ liệu đã xem, không phải bằng chứng xác suất tương lai 75%.

Nguồn lý thuyết:
[StockCharts ChartSchool](https://chartschool.stockcharts.com/table-of-contents/chart-analysis/chart-types/relative-rotation-graphs-rrg-charts).
