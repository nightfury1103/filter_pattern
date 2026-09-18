# La bàn chung bằng các trạng thái lịch sử tương tự

Ngày chạy 17/09/2026. [Protocol](compass-analog-protocol.md) chốt trước khi
xem kết quả. Báo cáo: `reports/compass-analog-d1/index.html`. Một phép đối
chiếu và một K/ngưỡng cho toàn rổ, không tùy biến riêng thị trường. Trang
chính có sáu thẻ, đúng bảy mã trong ảnh; số liệu từng mã thu gọn để kiểm tra.
XAUUSD vẫn thiếu OHLC spot nên chỉ đánh giá được sáu mã.

## Kết luận theo tiêu chí

Chưa đạt 75% với độ phủ hữu ích và khả năng định hướng hai chiều. Ứng viên
25 giai đoạn tương tự có tỷ lệ điểm khá hơn khi chỉ lấy tín hiệu mạnh, nhưng
độ phủ thấp và tất cả là Long. Không coi đó là la bàn đạt yêu cầu, không chọn
nó sau khi xem test để thay mô hình đã sàng lọc trước đó.

Không năm nào có K/ngưỡng vượt bước chọn trên năm Y−2; vì vậy bước xác nhận
Y−1 chưa có cấu hình hợp lệ để xét, và la bàn chính WAIT trong cả ba năm
2024–2026. Không diễn giải WAIT toàn kỳ là an toàn hoặc hiệu quả.

## Kết quả tổng quan sau 10 nến

Tỷ lệ đúng và độ phủ cân bằng trọng số phơi nhiễm tài sản; US500/SPY mỗi mã
nửa trọng số. Số tín hiệu là ngày-tài sản, có tương quan và cửa sổ chồng lấn.
Ngưỡng 75% ở đây áp vào tần suất analog làm trơn, chưa phải xác suất đã hiệu
chỉnh. Bảng ứng viên là chẩn đoán cố định, không phải kết quả la bàn chính.

| Chẩn đoán | Tỷ lệ đúng có trọng số | Độ phủ | Ngày-tài sản phát hướng | Long / Short |
|---|---:|---:|---:|---:|
| 25 analog, ngưỡng .75 | 70,38% | 3,16% | 165 | 165 / 0 |
| 50 analog, ngưỡng .75 | 62,82% | 0,39% | 22 | 22 / 0 |
| 100 analog, ngưỡng .75 | — | 0% | 0 | 0 / 0 |
| 25 analog, hướng mỗi ngày | 53,74% | 100% | 4.630 | 3.494 / 1.136 |
| 50 analog, hướng mỗi ngày | 54,39% | 99,96% | 4.628 | 3.822 / 806 |
| 100 analog, hướng mỗi ngày | 54,39% | 100% | 4.630 | 4.151 / 479 |
| EMA | 50,43% | 100% | 4.630 | 3.020 / 1.610 |
| Luôn Long | 54,60% | 100% | 4.630 | 4.630 / 0 |

Không so 70,38% trên vài ngày chọn lọc với 54,60% trên mọi ngày rồi tuyên bố
cải thiện dự báo. Vì ứng viên .75 luôn Long, luôn Long trên chính những ngày
nó chọn có kết quả giống hệt. Cần bằng chứng về chọn thời điểm ổn định và
khả năng Short; thử nghiệm này chưa cung cấp được.

Theo từng mã trong bảng kiểm tra, 25 analog .75 có tỷ lệ điểm 42,86–88,10%.
US500 37/45 và SPY 37/42 tương ứng 82,22% và 88,10%, nhưng đây là hai mã gần
cùng phơi nhiễm, chỉ có 5 và 4 mẫu trên lịch cố định mỗi 10 nến; cận dưới
CI95% lần lượt 47,91% và 53,33%. Không dùng hai tỷ lệ đó để tuyên bố toàn rổ
đạt 75%. Các mã khác có ít tín hiệu hoặc kết quả thấp hơn.

## Đối chiếu cùng ứng viên trên các mã trong ảnh

Báo cáo riêng: `reports/compass-analog-d1/across-symbols.html`, kèm CSV/JSON.
Giữ nguyên K=25, ngưỡng .75 và thư viện từng năm; không huấn luyện lại hay
chọn tham số riêng từng mã. Chân trời chính vẫn là 10 nến.

| Mã | Đúng sau 5 nến | Sau 10 nến | Sau 20 nến | Đúng/ngày tín hiệu 10 nến | Độ phủ 10 nến |
|---|---:|---:|---:|---:|---:|
| XAUUSD | — | — | — | Thiếu OHLC spot hợp lệ | — |
| BTCUSD | 39,1% | 69,6% | 60,9% | 16/23 | 2,35% |
| ETHUSD | 50,0% | 42,9% | 71,4% | 12/28 | 2,86% |
| DXY | 57,1% | 57,1% | 71,4% | 4/7 | 1,04% |
| US500 | 75,6% | 82,2% | 84,4% | 37/45 | 6,73% |
| SPY | 83,3% | 88,1% | 92,9% | 37/42 | 6,28% |
| E1VFVN30 | 60,0% | 70,0% | 85,0% | 14/20 | 3,03% |

Tất cả 165 ngày-tài sản phát hướng đều là Long. ETHUSD sau 10 nến giảm từ
4/7 năm 2024 xuống 6/11 năm 2025 và 2/10 trong phần năm 2026 đã có nhãn.
US500/SPY có tỷ lệ điểm cao nhưng mẫu nhỏ và tương quan. Không chọn riêng
chân trời 20 nến cho E1VFVN30 để tuyên bố đạt mục tiêu đã đặt ở 10 nến.

Đã phát lại 4.690 ngày dự báo, đối chiếu cả ba K với giá trị lưu sai số
không quá 1e-12, cùng hướng K=25; tính lại return từ OHLC cho mọi tín hiệu
ở 5/10/20 nến và khớp số đúng/tổng. Hash kết quả nguồn khớp. Báo cáo có đủ
bảy dòng phạm vi, sáu mã thực sự kiểm thử, 18 dòng theo năm; kiểm tra trình
duyệt desktop/mobile không lỗi JavaScript, không tràn ngang và các liên
kết tệp tồn tại. Đây vẫn là kiểm tra hồi cứu trên cùng dữ liệu đã xem.

## Cấu hình đã chọn trước từng năm test

| Năm test | K chọn bằng Brier năm Y−2 | Số đoạn trong thư viện | Gate |
|---|---:|---:|---|
| 2024 | 100 | 770 | Không đạt |
| 2025 | 100 | 942 | Không đạt |
| 2026 | 50 | 1.116 | Không đạt |

Ví dụ chọn cho năm test 2026: K=50, ngưỡng .60 có accuracy 64,24%, coverage
33,38%, 570 Long và 28 Short trên năm chọn 2024. Nó không đạt 75%. Ngưỡng
.75 có 1/1 đúng và coverage 0,083%, cũng không đạt. Không đổi K/ngưỡng bằng
kết quả test. Tất cả trial được lưu đầy đủ trong `results.json`.

Thư viện cố định mỗi fold trước năm chọn, lấy cách 10 nến cùng mã; chỉ chứa
kết quả hoàn tất trước ranh giới. Median/IQR của scaler chỉ fit thư viện.
12 đặc trưng giá D1/tuần đã đóng, không tên mã/giá tuyệt đối. K hàng xóm vẫn
có tương quan giữa các mã, không phải K quan sát độc lập. Không refit thư
viện sau khi chọn, nên cả lợi ích và hạn chế của thư viện cũ đều nằm trong
kết quả test.

## Kiểm tra và tái lập

```powershell
.venv/Scripts/python.exe -m filter_pattern.compass_analog --cache reports/compass-exact-d1/candles.json --out reports/compass-analog-d1 --before 2026-09-17
```

Chạy offline. Lưu `protocol.json`, `results.json`, `overview.json`, OHLC,
`reference-libraries.joblib`, hash input/code, các giai đoạn và trial; thư
mục `reports/` không được git theo dõi. Không sửa RRG/scanner hoặc dữ liệu
của các vòng trước. Logic tổng hợp báo cáo cũ đã được kiểm tra cho kết quả
giữ nguyên khi thêm lựa chọn nguồn dự báo cho báo cáo analog.

11 test analog/shared đạt: thư viện cách 10 nến, vote được đối chiếu với
phép tính trực tiếp, nhãn query không ảnh hưởng dự báo, purge ba ranh giới,
giữ flat trong đánh giá, xác nhận không tự dò lại ngưỡng, không tạo xác suất
khi thiếu thư viện, cùng các kiểm tra tuần đã đóng/trọng số của vòng trước.
Trình duyệt desktop/mobile đạt: sáu thẻ/bảy mã, sáu đuôi thật, đổi K/ngày/mã/
chân trời, trạng thái gate rõ, không lỗi JavaScript hoặc tràn ngang.

Đối chiếu 13.860 forward outcome với OHLC, mọi số tín hiệu/đúng theo mô hình,
chân trời và hướng; kiểm tra model/ngưỡng chung từng năm, nhãn thư viện trước
năm chọn, không chồng lấn kết quả cùng mã trong thư viện, cùng hash đều khớp.

Nghiên cứu tiếp tục dùng 2024–2026 đã từng xem: đây vẫn là hồi cứu, không là
xác nhận trên dữ liệu mới. Chỉ ba K đã chốt được thử trong vòng này.
