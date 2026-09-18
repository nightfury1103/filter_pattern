# Kết quả vòng cập nhật thư viện analog theo tháng

Ngày 18/09/2026. Chạy theo [protocol chốt trước chạy](compass-adaptive-protocol.md).
Báo cáo `reports/compass-adaptive-d1/index.html`, kèm CSV, JSON, thư viện và
calibrator đã lưu. Giữ nguyên RRG/scanner, các báo cáo và mô hình cũ.

## Kết luận

Không cải thiện đủ để thay bản cũ hoặc đạt mục tiêu 75%. Cập nhật thư viện
giúp có tín hiệu Short nhưng tỷ lệ đúng của nhóm tín hiệu ngưỡng .75 giảm,
độ phủ cũng giảm. Bản đã hiệu chỉnh không có tín hiệu .75 ở cả năm xác nhận
lẫn test. WAIT toàn kỳ là thất bại về tính hữu ích, không phải thành công.

BTCUSD có tỷ lệ điểm cao hơn ở vài ngày được chọn nhưng không thể dùng một
mã này để tuyên bố cải thiện toàn rổ. Chưa kiểm thử được XAUUSD do thiếu
OHLC spot hợp lệ. Dữ liệu test vẫn là 2024–2026 đã xem nhiều lần, không có
holdout mới. Không triển khai bộ lọc giao dịch từ kết quả này.

## Thay đổi đã thử

Giữ đúng 25 hàng xóm, 12 đặc trưng và cách vote cũ. Thay thư viện cố định
trước năm Y−2 bằng thư viện bốn năm gần nhất, cập nhật mỗi tháng. Mọi nhãn
tham khảo phải hoàn tất trước đầu tháng. Chỉ các kết quả test đã hoàn tất
mới được dùng cho lần cập nhật sau; không chọn tham số từ kết quả test.

Thêm sigmoid hiệu chỉnh từ dự báo tuần tự năm Y−2, xác nhận ngưỡng .75 trên
Y−1, giữ calibrator suốt năm test. Không đổi K, cửa sổ, đặc trưng hay ngưỡng
chính sau chạy. Ngưỡng .60/.65/.70/.75/.80 đều khai báo là chẩn đoán trước
khi chạy, không chọn dòng đẹp nhất để thay la bàn chính.

## Tổng quan trên cùng ngày — hướng sau 10 nến D1

Tỷ lệ và độ phủ có trọng số cân bằng tài sản, US500/SPY mỗi mã nửa trọng số.
Số tín hiệu là ngày-tài sản, có cửa sổ chồng lấn, không phải giao dịch độc lập.
Mỗi phương pháp chọn ngày khác nhau; không coi chênh lệch tỷ lệ ở nhóm .75
là so sánh cặp trên cùng tín hiệu. Phần hướng mỗi ngày dùng cùng toàn bộ ngày.

| Phương án | Tỷ lệ đúng có trọng số | Độ phủ | Ngày-tài sản | Long / Short |
|---|---:|---:|---:|---:|
| Cũ K25 / .75 | 70,38% | 3,16% | 165 | 165 / 0 |
| Cập nhật tháng / .75 | 57,23% | 1,86% | 91 | 77 / 14 |
| Cập nhật tháng / .60, chẩn đoán | 55,15% | 38,85% | 1.838 | 1.329 / 509 |
| Cũ / hướng mỗi ngày | 53,74% | 100% | 4.630 | 3.494 / 1.136 |
| Cập nhật tháng / hướng mỗi ngày | 54,75% | 100% | 4.630 | 2.998 / 1.632 |
| Sau hiệu chỉnh / hướng mỗi ngày | 49,51% | 100% | 4.630 | 3.160 / 1.470 |
| Sau hiệu chỉnh / .75 | — | 0% | 0 | 0 / 0 |
| La bàn chính qua xác nhận | — | 0% | 0 | 0 / 0 |
| Luôn Long | 54,60% | 100% | 4.630 | 4.630 / 0 |

Định hướng mỗi ngày cải thiện khoảng 1 điểm phần trăm so bản cũ, gần mức
luôn Long. CI95% chênh lệch theo khối giữa bản cập nhật và bản cũ trên cùng
ngày đều chứa 0 ở cả sáu mã. Chưa có bằng chứng khác biệt rõ. Không coi
54,75% là cải thiện đủ để sử dụng la bàn theo mục tiêu 75%.

## Kiểm tra từng mã, cùng ngưỡng .75

| Mã | Bản cũ: đúng sau 10 nến | Cập nhật: đúng/tín hiệu | Tỷ lệ mới | Độ phủ mới |
|---|---:|---:|---:|---:|
| XAUUSD | — | Chưa đủ dữ liệu | — | — |
| BTCUSD | 69,6% | 14/17 | 82,4% | 1,73% |
| ETHUSD | 42,9% | 17/31 | 54,8% | 3,16% |
| DXY | 57,1% | 4/8 | 50,0% | 1,19% |
| US500 | 82,2% | 11/14 | 78,6% | 2,09% |
| SPY | 88,1% | 6/13 | 46,2% | 1,94% |
| E1VFVN30 | 70,0% | 2/8 | 25,0% | 1,21% |

Tổng thô ở bản cập nhật: 54/91 đúng, 37 sai; Long 48/77 và Short 6/14.
Các tỷ lệ tổng thô này khác tỷ lệ có trọng số ở bảng tổng quan.
BTCUSD sau 5 nến là 9/17, sau 20 nến là 7/14; ba tín hiệu gần cuối chưa có
kết quả 20 nến. Không thể diễn giải riêng 82,4% sau 10 nến thành độ chính
xác ổn định trên các khoảng thời gian. Mọi chân trời và từng năm nằm trong
báo cáo, không loại các kết quả kém.

## Hiệu chỉnh và tính ổn định của điểm tin cậy

Hệ số sigmoid cho test 2024/2025/2026 lần lượt khoảng −0,574 / 0,031 / 0,239.
Đây là kết quả fit từ năm Y−2, không phải hệ số chọn bằng test. Quan hệ
vote–kết quả học được thay đổi đáng kể qua các năm; sau hiệu chỉnh, điểm
không đi vào vùng .75/.25. Hiệu chỉnh không tự tạo thêm thông tin dự báo.
Brier giảm ở một số mã và tăng ở mã khác; các nhóm điểm và tần suất tăng
thực tế được công bố, không đồng nhất Brier với riêng chất lượng hiệu chỉnh.

Không năm nào vượt gate .75 trên năm xác nhận. Kết quả này không chứng minh
mọi cách làm la bàn đều bất khả thi; nó bác bỏ việc đưa cấu hình mới này
vào sử dụng với tuyên bố đạt mục tiêu đã đặt.

## Kiểm tra và tái lập

```powershell
.venv/Scripts/python.exe -m filter_pattern.compass_adaptive
.venv/Scripts/python.exe -m pytest tests/test_compass_adaptive.py tests/test_compass_analog.py tests/test_compass_shared.py -q
```

18 test đạt. Kiểm tra mới gồm cửa sổ bốn năm, nhãn hoàn tất trước tháng,
thay nhãn/đặc trưng tương lai không đổi dự báo tháng trước, nhãn mới chỉ
vào thư viện tháng sau, purge calibration, không bịa xác suất khi thiếu
fit, không bỏ ngày thiếu điểm khỏi độ phủ, flat tính sai và gate cần đủ
hai hướng. Có chạy lại kiểm tra analog/tuần dùng chung.

Phát lại độc lập 8.147 vote theo tháng (gồm 4.690 ngày test) từ 57 thư viện,
đối chiếu 39.038 dòng tham khảo và mọi nhãn trước ranh giới; sai số vote
không quá 1e-12. Tính lại 13.860 kết quả giá từ OHLC, khớp toàn bộ số
đúng/sai/tín hiệu theo mô hình, chân trời và hướng. Hash input/code khớp.
Chi tiết: `reports/compass-adaptive-d1/audit.json` và `audit.py`.

Trình duyệt desktop/mobile: sáu thẻ, bảy mã, sáu đuôi có dữ liệu; bốn lựa
chọn biểu đồ, mọi mã/chân trời, bảng so sánh bảy dòng, không lỗi JavaScript,
không tràn ngang, liên kết tệp tồn tại. Ngày đầu không tạo đuôi giả. Không
nối đuôi qua kỳ cập nhật thư viện để tránh coi thay mô hình là momentum giá.
Các tệp trong `reports/` là artifact local và không được git theo dõi.

## Bổ sung biểu đồ giá

Báo cáo có đường giá đóng cửa D1 bên dưới la bàn, dùng thang log và màu
Long xanh / Short đỏ / Chờ xám theo dự báo lưu tại ngày đó. Chọn mã từ thẻ
hoặc danh sách; cửa sổ 60/180/360 nến hoặc toàn kỳ. Ngày và mô hình đồng bộ
với la bàn; di chuột, chạm hoặc phím trái/phải xem từng điểm. XAUUSD giữ
trạng thái thiếu dữ liệu. Chỉ dựng lại HTML, không chạy lại mô hình hoặc
thay số liệu backtest. Kiểm tra trình duyệt đối chiếu 4.320 trạng thái màu
trên bốn mô hình/sáu mã, lọc giá theo ngày xem lại, chọn bằng bàn phím,
khung thời gian, bảng cũ và màn hình nhỏ đều đạt; không lỗi JavaScript.

Chế độ màu mặc định sau phản hồi là bốn trạng thái Improving (xanh dương),
Leading (xanh lá), Weakening (cam), Lagging (đỏ), tính từ điểm tăng so với
50% và thay đổi qua 5 nến trong cùng kỳ thư viện. Đoạn trên trục hoặc chưa
đủ dữ liệu giữ xám. Có lựa chọn màu Long/Short/Chờ riêng: bản selected
thực sự WAIT toàn kỳ nên ở chế độ tín hiệu đường vẫn xám, kèm giải thích.
Không biến màu quadrant thành tín hiệu giao dịch. Kiểm tra thêm 4.320
trạng thái quadrant trên bốn mô hình/sáu mã khớp lịch sử; chấm Long/Short
vẫn chỉ lấy tín hiệu đã lưu và backtest không đổi.
