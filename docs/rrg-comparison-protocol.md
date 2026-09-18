# Đối chiếu RRG hiện tại và Market Compass D1

Chốt quy tắc trước khi tải và xem hiệu quả RRG, ngày 17/09/2026. Không sửa
RRG/scanner, không tái tạo công thức JdK bằng EMA thay thế, không chọn quy tắc
thắng sau khi nhìn kết quả.

## Nguồn thật của hệ thống hiện tại

`filter_pattern/rrg_dashboard.py` lấy tọa độ từ StockCharts và Fialda:

- BTCUSD, ETHUSD, DXY, US500, XAUUSD: StockCharts, benchmark `$ONE`.
- SPY: StockCharts, benchmark SPY (so với chính nó).
- E1VFVN30: Fialda, benchmark VNINDEX.

Không coi mọi tọa độ này là cùng một phép đo tương đối với SPY. Đặc biệt SPY
tại tâm 100/100 không có thông tin hướng dù hàm quadrant dùng >= và gọi Leading.
Giữ nguyên cấu hình đó khi đánh giá, ghi rõ điểm bất cập thay vì sửa âm thầm.

## Quy tắc đọc hướng

Dashboard hiện là tham chiếu, không có bộ lọc hai chiều Long/Short hoàn chỉnh.
Vì vậy tách ba phép đọc, không gọi phép đọc mới là quy tắc giao dịch có sẵn:

1. Chính: nửa trên (Improving/Leading, Y>100) Long; nửa dưới (Weakening/Lagging,
   Y<100) Short; đúng Y=100 là WAIT.
2. Đối chiếu sức mạnh trục X: X>100 Long, X<100 Short, đúng 100 WAIT.
3. Hàm `rrg_intent` hiện tại: accepted là Long, còn lại WAIT. Không tự suy diễn
   rejected thành Short. Dùng tối thiểu bốn điểm và chỉ các điểm đến ngày T.

Compass giữ hai mô hình đã lưu; đối chiếu cả ngưỡng 75% hiện tại và phép đọc
hướng P(tăng)>50% mỗi ngày. P=50% WAIT. Giữ EMA và luôn Long làm baseline.

## Mẫu và cách đo

Rổ đúng bảy mã trong ảnh. Dùng nến đã đóng trước 17/09/2026; test từ 2024.
RRG tại ngày T ghép đúng ngày target, không forward-fill. Dùng open T+1 tới
close T+5/10/20; 10 nến là chính, không TP/SL. Loại ngày chưa đủ nến kết quả.
Giữ nguyên OHLC đã được audit của vòng Compass. XAUUSD thiếu OHLC không có
đánh giá hướng dù nguồn RRG có tọa độ; không thay bằng futures.

Chỉ so sánh trên ngày chung có tọa độ RRG và dự báo Compass. Ghi rõ khoảng
lịch sử thực nhận từ API, số ngày thiếu và mất phiên. Không lấy lịch sử ngắn
làm đại diện cho ba năm. Kiểm tra mức khớp giá và lịch nguồn RRG với target;
khác feed/phiên phải công bố. Lịch sử tải hồi cứu không bảo đảm không bị nhà
cung cấp chỉnh sửa; không gọi đây là dữ liệu dự báo được lưu tại thời điểm T.

Tỷ lệ đúng, số sai, độ phủ, Long/Short, các năm, độ ổn định; paired comparison
trên ngày hai hệ thống cùng đưa hướng. Không so hai tỷ lệ trên hai tập ngày
khác nhau rồi tuyên bố có lợi thế. Block bootstrap theo thời gian khi đủ mẫu;
không gộp US500/SPY thành hai thị trường độc lập. Nếu không lấy đủ lịch sử thật,
chỉ kết luận trên phần có thể kiểm thử và ghi rõ giới hạn.

Kiểm tra nguồn trước khi tính performance: crypto chỉ có ngày theo lịch nguồn
StockCharts, không có đủ bảy ngày/tuần; không nội suy cuối tuần. Giá nguồn
DXY ngày 05/03/2025 và E1VFVN30 ngày 29/07/2025 lệch hơn 1% so với cache OHLC.
Giữ toàn bộ ngày chung trong kết quả chính; thêm kiểm tra độ nhạy loại ngày có
giá lệch >1%, không chọn kết quả đẹp hơn. Giá Fialda tính nghìn VND, nhân 1.000
chỉ khi đối chiếu với giá VND của cache. Không thay đổi tọa độ RRG.
