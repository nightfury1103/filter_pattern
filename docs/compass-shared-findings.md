# Kết quả: một la bàn chung cho đúng rổ trong ảnh

Chạy 17/09/2026 theo [protocol cố định](compass-shared-protocol.md). Báo cáo:
`reports/compass-shared-d1/index.html`. Dùng một mô hình/ngưỡng chung cho cả
rổ mỗi năm, không cấu hình riêng từng thị trường, không thêm cổ phiếu thành
phần. Sáu thẻ và bảy mã giữ đúng ảnh; XAUUSD vẫn thiếu OHLC spot hợp lệ nên
chỉ có sáu mã được đánh giá. Không thay vàng futures. RRG/scanner giữ nguyên.

## Tiêu chí của người dùng

| Tiêu chí | Kết quả vòng này |
|---|---|
| Đúng bảy tên mã, tổng quan chung | Giao diện có đủ; chỉ 6/7 mã có dữ liệu hợp lệ |
| Một phương pháp cho mọi mã | Có; chọn một model/ngưỡng cho cả rổ, không symbol feature |
| D1, hướng sau 10 nến, độc lập setup | Có; open T+1 → close T+10, không TP/SL |
| Đúng ít nhất 75% với độ phủ hữu ích | Chưa đạt |
| Nhận biết hai chiều Long/Short | Chẩn đoán có hai chiều nhưng accuracy yếu; la bàn chọn lọc không qua gate |
| Đủ bằng chứng để dùng làm la bàn chính | Chưa có |

## Các thử nghiệm và hiệu quả tổng quan

Ba ứng viên cố định: cây D1; cùng cây thêm xu hướng từ tuần **đã đóng**;
rừng cây dùng D1 + tuần đã đóng. Tuần đang chạy không được đưa vào feature.
Train, calibration, validation, test tách theo năm và loại nhãn vượt ranh
giới. Test 2024–2026 đã được xem ở các vòng trước: vẫn là hồi cứu.

Đọc hướng mỗi ngày bằng P(tăng)>50% Long, <50% Short, kết quả 10 nến:

| Phương án chung | Tỷ lệ đúng có trọng số | Độ phủ |
|---|---:|---:|
| Cây D1 | 50,30% | 100% |
| Cây D1 + tuần đã đóng | 49,57% | 100% |
| Rừng D1 + tuần đã đóng | 50,13% | 100% |
| EMA baseline | 50,43% | 100% |
| Luôn Long baseline | 54,60% | 100% |

4.630 ngày-tài sản đủ kết quả; đây là mẫu có tương quan và cửa sổ chồng lấn,
không phải 4.630 quan sát độc lập. Tỷ lệ tổng cân bằng phơi nhiễm theo tài sản,
US500/SPY mỗi mã một nửa trọng số để giảm đếm đôi. Không dùng tỷ lệ tổng che
kết quả riêng: các ứng viên có tỷ lệ từng mã khoảng 44,9–56,0%, đều xa 75%.
Tổng có trọng số không đơn giản là số ngày đúng chia 4.630.

Ở ngưỡng xác suất .75 cố định, cả ba ứng viên không phát tín hiệu ở cả sáu
mã. Không có accuracy để báo, không gọi WAIT toàn kỳ là thành công.

## Chọn ngưỡng bằng quá khứ

Chọn ứng viên Brier tốt nhất trên năm validation trước test. Sau đó chỉ thử
lưới ngưỡng đã chốt [.55,.60,.65,.70,.75,.80,.85]; cần accuracy có trọng số
>=75%, coverage>=10%, >=100 ngày-tài sản, >=20 Long và >=20 Short trên
validation. Không đạt thì la bàn chính WAIT năm test; không dùng test để
đổi model, đổi ngưỡng hoặc bỏ điều kiện.

| Năm test | Model chọn bằng validation | Kết quả gate |
|---|---|---|
| 2024 | Cây D1 + tuần | Không đạt |
| 2025 | Rừng D1 + tuần | Không đạt |
| 2026 | Cây D1 | Không đạt |

Ví dụ validation của năm test 2026: ngưỡng .60 có tỷ lệ đúng 69,60%, coverage
11,18%, 194 tín hiệu nhưng toàn Long. Ngưỡng .65 có 1/1 đúng, coverage 0,056%.
Cả hai không đạt. Đây là số của validation, không phải kết quả test hoặc tín
hiệu có thể sử dụng. La bàn chính có coverage 0%, vì vậy **không đáp ứng nhu
cầu định hướng hữu ích**, dù mô hình vẫn có xác suất để vẽ chẩn đoán.

Các tỷ lệ dự báo gom gần 50% cho thấy những cấu hình đã thử chưa học được
mối quan hệ đủ mạnh để tự tin định hướng. Thêm xu hướng tuần và chia sẻ mô
hình không tạo cải thiện trong thử nghiệm này. Không suy ra mọi phương pháp
khác đều không thể đạt mục tiêu; cũng không có căn cứ hứa chỉ cần tối ưu
tiếp sẽ đạt 75%. Không tiếp tục dò tham số trên test trong vòng này.

## Sản phẩm và kiểm tra

```powershell
.venv/Scripts/python.exe -m filter_pattern.compass_shared --cache reports/compass-exact-d1/candles.json --out reports/compass-shared-d1 --before 2026-09-17
```

Chạy offline với cache đã kiểm tra. Có protocol, hash nguồn/mã, ranh giới các
fold, toàn bộ lưới ngưỡng validation, model artifact, `results.json` và
`overview.json`. `reports/` không được git theo dõi.

6 test đạt: tuần đã đóng không đọc dữ liệu tương lai, purge ba ranh giới,
trọng số US500/SPY, gate không chấp nhận chỉ một hướng, chọn một ngưỡng chung
và không tạo xác suất khi chưa có model. Đối chiếu 13.860 forward outcome với
OHLC; kiểm lại mọi count theo model/horizon/side, mọi mã cùng model/ngưỡng
trong một năm, ranh giới và hash đều khớp.

Trình duyệt desktop/mobile đạt: sáu thẻ/bảy mã, sáu đuôi thật, chọn bốn chế
độ đồ thị, ba chân trời, xem lịch sử không vẽ đuôi tương lai, gate thất bại
hiển thị rõ, không lỗi JavaScript hoặc tràn ngang. Phần kiểm tra từng mã được
thu gọn mặc định; trang chính ưu tiên tổng quan cả rổ.
