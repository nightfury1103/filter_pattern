# Kết quả la bàn trạng thái giá + RRG

Ngày chạy 17/09/2026, theo [protocol chốt trước khi chạy](compass-hybrid-protocol.md).
Báo cáo tương tác: `reports/compass-hybrid-d1/index.html`. Có sáu thẻ/bảy mã
đúng ảnh, bốn quadrant, lịch sử và mũi tên, chọn mô hình/ngày để xem lại.
XAUUSD thiếu OHLC spot hợp lệ nên giữ trạng thái thiếu dữ liệu.

## Kết luận

Phương án kết hợp này **chưa chứng minh được mục tiêu 75%**. Thêm RRG không
cải thiện ổn định so với cùng mô hình chỉ dùng giá. Không đổi RRG/scanner,
không hạ ngưỡng xác suất để tăng tín hiệu sau khi nhìn kết quả, không chọn
riêng mô hình có tỷ lệ điểm đẹp ở từng mã để triển khai.

Đây là nghiên cứu hồi cứu trên giá đã từng được xem. Mỗi fold chỉ học bằng
quá khứ và loại nhãn vượt ranh giới, nhưng toàn nghiên cứu không có tập mới
hoàn toàn. Kết quả âm không chứng minh mọi phương pháp đều bất khả thi; nó
loại bỏ việc coi các cấu hình đã thử là la bàn đạt yêu cầu.

## Phạm vi so sánh

StockCharts mới có lịch sử từ 07/2022, Fialda từ 12/2023. Yêu cầu tối thiểu
200 train và 120 calibration được giữ nguyên. Năm 2024 không có fold ML nào
đủ điều kiện; E1VFVN30 năm 2025 cũng không đủ.

- BTCUSD, ETHUSD, DXY, US500, SPY: so sánh ML từ 02/01/2025–16/09/2026,
  427 ngày có dự báo/mã, 420 ngày đủ kết quả 10 nến với crypto, 417 với các mã
  còn lại. Crypto RRG không có đủ cuối tuần; kết quả vẫn đo 10 nến tài sản.
- E1VFVN30: từ 05/01/2026, 172 ngày dự báo, 162 ngày đủ kết quả 10 nến.
- Quy tắc cố định được báo riêng từ 2024, không gộp tỷ lệ với ML ở kỳ ngắn hơn.

## Hướng mỗi ngày sau 10 nến

Đọc P(tăng)>50% là Long, <50% là Short. Đây là chẩn đoán có sẵn trong protocol,
không thay thế ngưỡng 75% của la bàn chọn lọc.

| Mã | Logistic chỉ giá | Logistic giá + RRG | Cây chỉ giá | Cây giá + RRG | Luôn Long |
|---|---:|---:|---:|---:|---:|
| BTCUSD | 48,81% | 48,57% | 50,00% | 49,76% | 48,33% |
| ETHUSD | 56,67% | 53,33% | 56,43% | 54,52% | 47,86% |
| DXY | 54,92% | 45,80% | 51,56% | 46,52% | 47,00% |
| US500 | 60,91% | 60,91% | 60,91% | 60,91% | 60,91% |
| SPY | 60,91% | 60,91% | 60,91% | 60,91% | 60,91% |
| E1VFVN30 | 46,30% | 46,30% | 46,30% | 46,30% | 46,30% |

US500/SPY/E1VFVN30 luôn nghiêng Long trong mẫu ML. Chúng chưa giải quyết được
nhu cầu phân biệt hai hướng. DXY logistic khi thêm RRG giảm 9,11 điểm %, CI95%
paired block bootstrap −16,07 đến −2,40 điểm %. Các kiểm tra nhiều mô hình là
thăm dò, chưa hiệu chỉnh nhiều giả thuyết; không tuyên bố RRG luôn vô ích.

## Khi yêu cầu xác suất ít nhất 75%

| Mã | Hybrid logistic: đúng / tín hiệu | Độ phủ | Hybrid cây: đúng / tín hiệu | Độ phủ |
|---|---:|---:|---:|---:|
| BTCUSD | 0/0 | 0% | 3/3 | 0,71% |
| ETHUSD | 0/0 | 0% | 0/0 | 0% |
| DXY | 0/0 | 0% | 0/0 | 0% |
| US500 | 0/1 | 0,24% | 0/0 | 0% |
| SPY | 0/2 | 0,48% | 2/2 | 0,48% |
| E1VFVN30 | 9/10 | 6,17% | 0/0 | 0% |

Mẫu 3/3 hay 2/2 không chứng minh chính xác 100%. E1VFVN30 9/10 = 90%, nhưng
chỉ có một tín hiệu trên lịch lấy mẫu cố định mỗi 10 nến. Mô hình logistic
chỉ giá ở cùng mã đã đạt 14/16 = 87,5%, độ phủ 9,88%; 10 ngày hybrid chọn đều
nằm trong 16 ngày đó. Chưa có bằng chứng RRG tạo lợi thế dự báo ổn định.

Toàn bộ tín hiệu hybrid ML vượt ngưỡng đều là Long. Không có bằng chứng ở
phía Short. Không phương án nào đạt độ phủ>=10%, >=100 tín hiệu lịch cố định
và cận dưới CI95%>=75% như protocol; lịch sử hiện tại cũng chưa đủ để tích
lũy 100 mẫu không chồng lấn ở các fold ML được dùng.

## Quy tắc trạng thái giá và RRG

Trên mẫu chung ML:

| Mã | Chỉ trạng thái giá | Thêm xác nhận RRG | Độ phủ kết hợp |
|---|---:|---:|---:|
| BTCUSD | 53/110 = 48,18% | 52/109 = 47,71% | 25,95% |
| ETHUSD | 66/119 = 55,46% | 66/119 = 55,46% | 28,33% |
| DXY | 68/141 = 48,23% | 68/141 = 48,23% | 33,81% |
| US500 | 67/114 = 58,77% | 67/114 = 58,77% | 27,34% |
| SPY | 65/110 = 59,09% | 0/0 | 0% |
| E1VFVN30 | 16/54 = 29,63% | 10/27 = 37,04% | 16,67% |

RRG xác nhận gần như toàn bộ tín hiệu giá ở BTC/ETH/DXY/US500; bộ lọc thêm
không cung cấp nhiều phân biệt mới trong cấu hình này. SPY so với chính nó
nên không thể xác nhận qua trục X/dX. Với E1VFVN30, giảm tín hiệu nhưng kết
quả vẫn yếu. Bảng paired giữa quy tắc giá và bộ lọc trên cùng ngày tất nhiên
cho tỷ lệ bằng nhau, vì bộ lọc không đổi hướng; đánh giá bộ lọc cần xem cả
các ngày bị loại và độ phủ, không dùng sự bằng nhau đó để suy luận hiệu quả.

Trên toàn kỳ quy tắc 2024+, US500 139/204 = 68,14% với độ phủ 30,49%, SPY
chỉ giá 136/199 = 68,34%. Tuy nhiên US500 giảm còn 58,77% trong mẫu 2025+;
không coi tỷ lệ toàn kỳ tốt hơn là một phát hiện đã được kiểm chứng ổn định.

## Artifact và kiểm tra

```powershell
.venv/Scripts/python.exe -m filter_pattern.compass_hybrid --cache reports/compass-exact-d1/candles.json --sources reports/rrg-comparison-d1 --out reports/compass-hybrid-d1 --before 2026-09-17
```

Chạy offline, không cần tải lại nguồn. Lưu `protocol.json`, `results.json`,
`candles.json`, `research-models.joblib`, ảnh desktop/mobile và browser check.
Kết quả có hash đầu vào/mã nguồn, phiên bản thư viện, ranh giới train/calibration
và lý do bỏ fold. `reports/` không được git theo dõi.

11 test hybrid/comparison đạt: công thức causal, không dùng nhãn test để học,
purge ranh giới, trung tính SPY, không forward-fill và bảo vệ HTML. Đối chiếu
12.009 forward return với OHLC gốc, toàn bộ số đúng/tín hiệu theo mô hình,
chân trời và Long/Short, cùng hash nguồn/mã đều khớp.

Trình duyệt desktop/mobile đạt: sáu thẻ, bảy mã, sáu đuôi thật, 14 phương án
trong bảng, 15 cặp đối chiếu, đổi mã/chân trời/mô hình/ngày; xem đầu kỳ thiếu
model không xuất hiện đuôi tương lai; không lỗi JavaScript hoặc tràn ngang.
