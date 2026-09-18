# Vòng 3 — giả thuyết bối cảnh liên thị trường, D1

Chốt trước khi đánh giá kết quả ngày 17/09/2026. Không thay RRG/scanner.
Không phụ thuộc setup; đúng hướng từ open T+1 đến close T+10, đối chiếu 5/20.

## Giả thuyết và nguồn

Giá của một market có thể thiếu thông tin về mức tham gia và tâm lý rủi ro.
Thử bổ sung bối cảnh từ:

- Chín ETF ngành gốc XLB/XLE/XLF/XLI/XLK/XLP/XLU/XLV/XLY: tỷ lệ trên EMA50,
  tỷ lệ tăng 20 phiên, thay đổi độ tham gia, phân tán đà ngành, chu kỳ/phòng thủ.
- RSP/SPY: diễn biến tương đối của tỷ trọng đều so với vốn hóa.
- HYG/IEF: diễn biến tương đối high-yield/Kho bạc; đây không phải credit spread
  thuần vì ETF còn khác duration và phân phối tiền mặt.
- TLT, USD index, S&P500: đà giá chuẩn hóa biến động.
- VIX/VIX3M và thay đổi VIX: bối cảnh biến động kỳ vọng từ Cboe.

Độ tham gia ETF ngành là proxy, không phải breadth của toàn bộ cổ phiếu.
Rổ chín ngành cố định tránh ghép danh sách cổ phiếu hiện tại ngược lịch sử,
nhưng phân ngành và thành phần ETF vẫn thay đổi qua thời gian. Không suy rộng
độ rộng Mỹ thành độ rộng riêng của crypto hoặc Việt Nam.

## Ba ứng viên cố định, không tìm kiếm tham số

1. **price_only**: cây nông chỉ nhận 15 đặc trưng giá của vòng 2.
2. **context**: cùng thuật toán/tham số, thêm 14 đặc trưng bối cảnh. Đây là
   ứng viên chính; so sánh trên đúng cùng tập train/calibration/test.
3. **confirmation**: quy tắc xác nhận cố định, không gán xác suất 75% cho rule:
   - Mọi hướng cần đà 5 nến cùng chiều và giá cách EMA20 không quá 2 ATR.
   - US500/BTC/ETH Long: >=2/3 ngành trên EMA50, HYG/IEF 5 phiên tăng,
     VIX/VIX3M<1; Short: <=1/3 ngành trên EMA50, HYG/IEF giảm, VIX/VIX3M>1.
   - Gold Long: USD giảm, TLT tăng trong 20 phiên; Short: ngược lại.
   - DXY Long: TLT giảm 20 phiên và HYG/IEF giảm 5 phiên; Short: ngược lại.
   Các quan hệ trên là giả thuyết cần kiểm tra, không phải quy luật chắc chắn.

Cây nông giữ tham số vòng 2: depth=2, 100 vòng, learning_rate=.05,
min_samples_leaf=50, L2=10, không early-stopping ngẫu nhiên. Sigmoid C=1.
Hai mô hình xác suất chỉ chọn Long ở P>=.75, Short ở P<=.25; còn lại Chưa rõ.

## Kiểm tra tuần tự và thời điểm thông tin

- Fit riêng mỗi market để không ép quan hệ vàng, USD và crypto giống nhau.
- Mỗi năm 2022–2026: train trước năm liền trước; calibration năm liền trước;
  test trong năm hiện tại. Nhãn vượt ranh giới bị loại. Không học từ kết quả
  năm đang kiểm tra. Giữ nguyên các mốc và tham số qua mọi fold.
- Đánh giá chính gộp các fold từ 2024; 2022–2023 là chẩn đoán sớm.
- Nguồn ngoài chỉ dùng ngày **nhỏ hơn** ngày nến target; không dùng dữ liệu
  cùng ngày chưa chắc đóng ở múi giờ khác. Quá 5 ngày lịch: Chưa rõ.
- Loại toàn nguồn target/context nếu OHLC sai, đứt >14 ngày hoặc có >=20 nến
  OHLC đứng yên cùng một giá. Không sửa nến hoặc nối qua khoảng trống.
- Trước khi đánh giá phát hiện nhân giá điều chỉnh có sai số khoảng một ULP
  ở ranh giới high=close. Validator chấp nhận tối đa 8 ULP (độ chính xác số
  thực máy), giữ nguyên mọi giá, đếm số dòng được chấp nhận theo ngoại lệ này.
  Đây không phải dung sai theo tick hoặc cho phép sai OHLC có ý nghĩa kinh tế.
- Bối cảnh thiếu dẫn tới Chưa rõ; vẫn tính trong mẫu đủ outcome để không
  tăng độ phủ giả. Không gộp SPY lần hai với US500.

## Tiêu chí và giới hạn

Báo cáo accuracy, false signals, coverage, Long/Short, 5/10/20, từng năm,
khối bootstrap theo cùng ngày giữa các market, lịch mỗi h nến, calibration,
độ ổn định và mức kéo giãn giá. Đối chứng thêm EMA và luôn Long.

Ứng viên hồi cứu: coverage>=10%, >=100 mẫu lịch không chồng lấn và cận dưới
CI95%>=75%. Đây chưa phải quyền định hướng live; không đổi ngưỡng sau xem kết quả.
Một phần lịch sử mục tiêu đã xem ở các vòng trước. Nguồn bối cảnh mới và cách
walk-forward không biến nó thành holdout mới. Xác nhận tương lai cần dữ liệu
phát sinh sau khi đóng băng mô hình; lưu snapshot dự báo cuối để kiểm tra sau.

Nguồn phương pháp/sản phẩm:
- https://www.cboe.com/tradable-products/vix/vix-historical-data
- https://www.invesco.com/us/financial-products/etfs/product-detail?ticker=RSP
- https://www.sec.gov/Archives/edgar/data/1064641/000095012312013525/b30061a1nvcsr.htm
- https://www.ishares.com/us/products/239565/ishares-iboxx-high-yield-corporate-bond-etf
- https://scikit-learn.org/stable/modules/calibration.html
