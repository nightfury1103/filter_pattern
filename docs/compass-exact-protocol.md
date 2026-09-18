# La bàn D1 — đúng các mã trong ảnh

Phạm vi người dùng chốt 17/09/2026: XAUUSD, BTCUSD, ETHUSD, DXY, US500,
SPY, E1VFVN30. Sáu thẻ Commodity / Crypto / Forex / Index / US stock /
Vietnam stock; Crypto giữ hai mã riêng. Không thêm VNINDEX hoặc đổi vàng
spot thành futures. Nguồn/phiên của US500 là S&P500 cash index, không phải
giá CFD của một broker; BTC/ETH là USD spot, không phải perpetual.

## Tối ưu riêng mã, giới hạn trước khi xem kết quả

Mỗi mã và mỗi năm 2024–2026, so sánh hai bộ đầu vào: giá riêng và giá có
bối cảnh. Mỗi bộ chỉ có ba ứng viên cố định:

1. Logistic: StandardScaler chỉ fit trên train; C=0.1.
2. Cây nông depth=2, 100 vòng, learning_rate=.05, leaf>=50, L2=10.
3. Cây depth=3, 100 vòng, learning_rate=.05, leaf>=50, L2=10.

Để dự báo năm Y: inner-train trước Y−2; chọn ứng viên bằng Brier trên năm
Y−2; refit trước Y−1; hiệu chỉnh sigmoid trên năm Y−1; test năm Y. Loại
mọi nhãn 10 nến vượt ranh giới. Không xem test để chọn ứng viên/ngưỡng.
Ít hơn 200 train/refit hoặc 120 validation/calibration, thiếu hai lớp:
không phát dự báo. Chọn bằng Brier toàn tập, không chọn vài tín hiệu đẹp.

Long khi P(tăng)>=.75, Short khi <=.25, còn lại Chưa rõ. Giữ ngưỡng qua
mọi market/năm; không gọi xác suất dự báo là accuracy được đảm bảo.
Kết quả đo open T+1 tới close T+10; 5/20 nến chỉ đối chiếu cùng tín hiệu.

Nguồn ngoài nhỏ hơn ngày target, tối đa 5 ngày lịch; không same-day join.
Mọi model dùng cùng tập có bối cảnh để so sánh. Bối cảnh ETF ngành Mỹ không
phải breadth của Việt Nam/crypto; hiệu quả phải kiểm tra từng mã riêng.
Không gộp SPY/US500 thành hai thị trường độc lập. Không dùng số tổng gộp
để tuyên bố đạt 75%. Cửa sổ test 2024+ đã được xem ở nghiên cứu trước; đây
vẫn là nghiên cứu hồi cứu, không phải holdout mới hoàn toàn.

## Dữ liệu và trình bày

- E1VFVN30 từ Vietcap, kiểm tra chéo KBS: 1.664 ngày trùng, 1.664 giá đóng
  cửa khớp chính xác. Loại ngày hiện tại và lưu raw nguồn.
- XAUUSD chưa có dữ liệu hợp lệ: Stooq yêu cầu xác minh trình duyệt,
  Dukascopy trả 429, Yahoo không có mã. Không thay bằng GC=F.
- Các nguồn cache khác giữ ngày tải và nguồn ban đầu.
- Kiểm tra OHLC, ngày trùng, continuity, nến chưa đóng như vòng trước.
- Thiếu nguồn vẫn giữ thẻ và dòng kết quả, không tạo đuôi giả.

Biểu đồ dùng bốn ô giống bố cục ảnh nhưng là la bàn xác suất: trục X=
100+100×(P(tăng)−.5), trục Y=100+100×(P hôm nay−P 5 nến trước). Trung tâm
100 chỉ là dịch trục để dễ đọc, không phải JdK RS-Ratio/Momentum. Đuôi tách
tại thời điểm refit đầu năm; mũi tên là di chuyển đã xảy ra, không dự báo
đường đi tương lai. RRG gốc/snapshot chỉ đối chiếu riêng, không sửa logic.

Tiêu chí bằng chứng giữ nguyên: coverage>=10%, >=100 mẫu lịch 10 nến,
cận dưới CI95%>=75%. Không đủ mẫu hoặc thất bại phải ghi rõ. Mục tiêu vòng
này là thử đúng rổ và trình bày dễ đọc, không ép một backtest vượt 75%.
