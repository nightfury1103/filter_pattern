# Kết quả la bàn D1 theo đúng các mã trong ảnh

Ngày chạy: 17/09/2026. Dữ liệu chỉ lấy nến trước ngày này. Báo cáo tương tác:
`reports/compass-exact-d1/index.html`; ảnh desktop/mobile và toàn bộ số liệu nằm
cùng thư mục. [Quy trình cố định](compass-exact-protocol.md) mô tả cách chọn mô
hình riêng từng mã bằng dữ liệu quá khứ, trước năm kiểm tra.

## Kết luận

Chưa chứng minh được mục tiêu đúng hướng ít nhất 75% với tần suất hữu ích.
Không đưa mô hình vào scanner hoặc thay RRG. Giao diện mới phục vụ kiểm tra
giả thuyết; xác suất trên biểu đồ không phải độ chính xác đã được xác nhận.

Đã kiểm tra BTCUSD, ETHUSD, DXY, US500, SPY và E1VFVN30. XAUUSD vẫn thiếu lịch
sử spot hợp lệ, được giữ trong thẻ và bảng nhưng không có đường biểu diễn giả.
Không thay mã này bằng vàng futures. US500 dùng S&P 500 cash index; cần dữ liệu
broker nếu muốn đánh giá chính xác feed CFD đang giao dịch.

## Kết quả hướng sau 10 nến

Tín hiệu tại close T; đo từ open T+1 đến close T+10. Chỉ phát Long khi xác suất
tăng >=75%, Short khi <=25%; còn lại Chưa rõ. Các ngày phát tín hiệu liên tiếp
có cửa sổ kết quả chồng lấn, không phải các quan sát độc lập.

| Mã | Chỉ giá: đúng / số ngày tín hiệu | Tỷ lệ đúng | Độ phủ | Thêm bối cảnh: đúng / số ngày tín hiệu | Tỷ lệ đúng | Độ phủ |
|---|---:|---:|---:|---:|---:|---:|
| BTCUSD | 3 / 3 | 100% | 0,31% | 0 / 0 | — | 0% |
| ETHUSD | 0 / 0 | — | 0% | 0 / 0 | — | 0% |
| DXY | 6 / 11 | 54,55% | 1,64% | 0 / 2 | 0% | 0,30% |
| US500 | 42 / 64 | 65,63% | 9,57% | 0 / 0 | — | 0% |
| SPY | 17 / 23 | 73,91% | 3,44% | 13 / 14 | 92,86% | 2,09% |
| E1VFVN30 | 47 / 87 | 54,02% | 13,16% | 5 / 5 | 100% | 0,76% |
| XAUUSD | Chưa kiểm thử | — | — | Chưa kiểm thử | — | — |

SPY 92,86% và E1VFVN30 100% không đủ bằng chứng: trên lịch lấy mẫu cố định mỗi
10 nến chỉ còn lần lượt 2 và 1 tín hiệu có bối cảnh. BTC 3/3 cũng quá ít. Với
US500 chỉ giá, khoảng tin cậy block bootstrap 95% là 49,29–77,83%; E1VFVN30 chỉ
giá là 27,60–65,38%. Không mã/mô hình nào đạt tiêu chí bằng chứng đã khai báo.
Không chọn mô hình thắng trên bảng test này để triển khai.

Báo cáo có phân tách Long/Short, đối chiếu 5/20 nến, số sai và baseline EMA /
luôn Long. Đây chưa phải kiểm chứng mô hình mới tốt hơn RRG: liên kết RRG chỉ
là đối chiếu giao diện, chưa có thử nghiệm lịch sử RRG đồng nhất cho cả rổ.
Các năm kiểm tra 2024–2026 đã được xem trong nghiên cứu trước; kết quả vẫn là
nghiên cứu hồi cứu, không phải xác nhận trên một tập mới hoàn toàn.

## Dữ liệu và giao diện

- Giữ đúng sáu nhóm và bảy mã trong ảnh; Crypto có BTCUSD và ETHUSD.
- E1VFVN30: 2.665 nến hợp lệ từ Vietcap, đến 16/09/2026; kiểm tra chéo KBS có
  1.664 ngày chung và toàn bộ giá đóng cửa khớp chính xác. Raw response được lưu.
- XAUUSD: Stooq trả trang xác minh, Yahoo không có lịch sử cho mã thử, endpoint
  Dukascopy trả 429. [Hướng dẫn chính thức của Dukascopy](https://www.dukascopy.com/wiki/en/development/data-export/)
  yêu cầu AWS credentials và cơ chế Requester Pays; chưa sử dụng nguồn này.
- Bốn quadrant giữ bố cục ảnh, nhưng trục là xác suất hướng và thay đổi xác
  suất sau 5 nến. Tâm 100 là phép dịch trục, không phải JdK RS-Ratio/Momentum.
- Thanh thời gian chỉ hiện dữ liệu đến ngày được chọn. Đuôi không nối qua lần
  huấn luyện lại đầu năm. Leading không tự động có nghĩa là được phép Long.

## Kiểm tra kỹ thuật

78 test liên quan đạt, gồm kiểm tra ranh giới thời gian, loại nhãn vượt ranh
giới và bảo đảm dữ liệu test không ảnh hưởng việc chọn mô hình. Kiểm tra trình
duyệt desktop/mobile đạt: sáu thẻ, bảy mã, sáu đường thật, mũi tên, đổi mô hình,
chọn ngày, chọn mã và bảng chi tiết; không có lỗi JavaScript hoặc tràn ngang.
Đây không phải kết quả chạy toàn bộ test của repository.

Lệnh tái lập bằng cache đã lưu:

```powershell
.venv/Scripts/python.exe -m filter_pattern.cli compass-exact --cache reports/compass-exact-d1/input-candles.json --context-cache reports/compass-context-d1/context-sources.json --out reports/compass-exact-d1 --before 2026-09-17
```

Các artifact nghiên cứu ở `reports/` không được git theo dõi. `results.json`
lưu nguồn, hash, phiên bản thư viện, mô hình được chọn và ranh giới từng fold.

## Kiểm tra performance bổ sung

Tính lại số tín hiệu và số đúng từ từng dòng dự báo: toàn bộ kết quả 5/10/20
nến khớp bảng đã lưu. Đồng thời đối chiếu trực tiếp các forward return với
open T+1 và close T+h trong cache OHLC. Chi tiết kiểm tra thêm được lưu ở
`reports/compass-exact-d1/performance-audit.json`; không huấn luyện lại hay đổi
ngưỡng của mô hình.

Để đánh giá việc dùng biểu đồ làm hướng mỗi ngày, kiểm tra thêm quy tắc đọc
trục X: P(tăng)>=50% là Long, thấp hơn là Short. Đây là chẩn đoán sau nghiên
cứu, không phải ngưỡng triển khai mới. Tỷ lệ đúng sau 10 nến:

| Mã | Chỉ giá | Có bối cảnh | Luôn Long, cùng ngày |
|---|---:|---:|---:|
| BTCUSD | 51,22% | 53,06% | 52,35% |
| ETHUSD | 51,22% | 48,67% | 47,96% |
| DXY | 46,65% | 52,16% | 49,78% |
| US500 | 63,98% | 63,38% | 63,68% |
| SPY | 63,53% | 63,53% | 63,53% |
| E1VFVN30 | 55,67% | 56,88% | 59,30% |

SPY luôn có P(tăng)>50% ở cả hai mô hình trong toàn bộ mẫu này; việc đọc hướng
biểu đồ tương đương luôn Long. US500 gần như không cải thiện baseline. Mức
nghiêng xác suất trên biểu đồ hiện chưa đủ để làm bộ lọc hướng đáng tin cậy.

Ở ngưỡng 75%, toàn bộ tín hiệu của BTCUSD, US500, SPY và E1VFVN30 đều là Long;
chỉ DXY chỉ giá có 6 ngày Short, đúng 4. Bản có bối cảnh không có ngày Short
nào ở sáu mã. Vì vậy chưa có bằng chứng nhận biết downtrend tốt. So sánh EMA
trên đúng ngày phát tín hiệu cho US500 chỉ giá là 60,94% so với la bàn 65,63%;
với SPY bối cảnh là 42,86% so với 92,86%, nhưng SPY chỉ có 14 ngày tín hiệu.
Các so sánh toàn thời gian và trên ngày được chọn trả lời những câu hỏi khác
nhau; chưa có kiểm định khẳng định cải thiện có ý nghĩa thống kê.

Kết quả phụ thuộc chân trời: US500 chỉ giá đúng 45,31% sau 5 nến, 65,63% sau
10 và 84,38% sau 20 (cùng 64 ngày tín hiệu). Không dùng kết quả 20 nến để tuyên
bố đạt mục tiêu chính 10 nến. E1VFVN30 bối cảnh có 5 tín hiệu đã đủ hạn 10 nến
nhưng chỉ 1 đủ hạn 20 nến; tỷ lệ 100% ở đây đặc biệt thiếu mẫu.

Độ tin cậy xác suất cũng yếu: nhóm tín hiệu US500 chỉ giá có xác suất tăng
trung bình 77,90% nhưng thực tế đúng 65,63%; E1VFVN30 là 79,54% so với 54,02%.
Ngưỡng xác suất 75% rõ ràng không đồng nghĩa với tỷ lệ đúng thực tế 75%.

Về ổn định, bản bối cảnh không đổi trạng thái lần nào ở BTC/ETH/US500 vì luôn
WAIT. Điều này không chứng minh la bàn có hướng ổn định. Bản chỉ giá US500
có 56 lần đổi trạng thái trong 679 ngày dự báo; SPY có 26 lần trong 679 ngày.
Tín hiệu E1VFVN30 chỉ giá chỉ xuất hiện trong năm 2026; US500 và SPY không
có tín hiệu đạt ngưỡng trong phần năm 2026 đã có kết quả 10 nến. Hiệu quả và
độ phủ không ổn định qua năm.

Kết luận kiểm tra: bản hiện tại chưa đáp ứng vai trò la bàn chính theo yêu
cầu. Nó vừa ít đưa ra hướng ở ngưỡng cao, vừa chưa dự báo đủ tốt khi đọc hướng
mỗi ngày. Chưa thể kết luận tốt hơn RRG từ thử nghiệm này.
