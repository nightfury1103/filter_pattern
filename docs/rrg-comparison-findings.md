# RRG hiện tại và Market Compass: kết quả đối chiếu

Chạy ngày 17/09/2026 theo [quy trình chốt trước khi xem performance](rrg-comparison-protocol.md).
Báo cáo tương tác: `reports/rrg-comparison-d1/index.html`; kết quả, các dòng dự
báo và raw response nguồn nằm cùng thư mục. Không sửa RRG/scanner, không fit
lại Compass, không đổi benchmark để làm kết quả tốt hơn.

## Kết luận

Không có bằng chứng RRG tốt hơn Compass trên toàn bộ rổ. RRG đọc trục Y tốt
hơn về tỷ lệ quan sát ở BTCUSD/DXY, yếu hơn ở US500/E1VFVN30; kết luận còn phụ
thuộc cách đọc X hay Y. Không phương án nào chứng minh đạt mục tiêu 75% trên
rổ này. US500 Compass mỗi ngày gần bằng luôn Long; vì vậy thắng RRG ở US500
không đủ để chứng minh có năng lực định hướng hữu ích.

## So sánh chính: hướng sau 10 nến

Nguồn RRG thật StockCharts/Fialda, ghép đúng ngày với các dự báo Compass đã
lưu. Ngày tín hiệu từ 02/01/2024; OHLC đã đóng đến 16/09/2026, loại những ngày
chưa có đủ nến tương lai. Đo open T+1 → close T+10, không TP/SL.

| Mã | RRG trục Y | RRG trục X | Compass chỉ giá, mỗi ngày | Compass bối cảnh, mỗi ngày | Luôn Long |
|---|---:|---:|---:|---:|---:|
| BTCUSD | 55,01% (368/669) | 46,58% (313/672) | 50,30% | 52,53% | 51,64% |
| ETHUSD | 48,21% (324/672) | 52,76% (354/671) | 51,04% | 49,11% | 48,51% |
| DXY | 59,07% (394/667) | 49,40% (330/668) | 46,79% | 52,32% | 49,93% |
| US500 | 47,14% (313/664) | 57,25% (383/669) | 63,98% | 63,38% | 63,68% |
| SPY | Không có hướng | Không có hướng | 63,53% | 63,53% | 63,53% |
| E1VFVN30 | 49,09% (324/660) | 55,15% (364/660) | 55,76% | 56,97% | 59,39% |
| XAUUSD | Chưa đánh giá | Chưa đánh giá | Thiếu OHLC | Thiếu OHLC | — |

RRG Y: trên 100 Long, dưới 100 Short; RRG X: tương tự theo trục X. Đúng 100
là WAIT. Đây là hai phép đọc dùng để kiểm thử, không phải bộ lọc hai chiều đã
có trong scanner. Compass mỗi ngày: P(tăng)>50% Long, <50% Short. Cùng tập
ngày có dữ liệu, nhưng số ngày có hướng có thể khác do WAIT/tọa độ đúng tâm.
Phép so sánh paired bên dưới chỉ dùng ngày cả hai cùng có hướng.

RRG gốc còn có `rrg_intent`: chấp nhận Long ở Improving/Leading khi đầu đuôi
đi lên; từ chối là WAIT, không phải Short. Kết quả Long/WAIT sau 10 nến:

| Mã | Đúng / số ngày Long | Tỷ lệ đúng | Độ phủ |
|---|---:|---:|---:|
| BTCUSD | 101/175 | 57,71% | 26,04% |
| ETHUSD | 85/180 | 47,22% | 26,79% |
| DXY | 99/174 | 56,90% | 26,01% |
| US500 | 81/145 | 55,86% | 21,67% |
| SPY | 0/0 | — | 0% |
| E1VFVN30 | 107/184 | 58,15% | 27,88% |

## So sánh paired và mức chắc chắn

Chênh lệch tính bằng tỷ lệ đúng RRG trừ Compass, trên cùng ngày cả hai có
hướng. CI95% là 500 lần block bootstrap, block 60 ngày quan sát, giữ các ngày
WAIT trong chuỗi khi lấy mẫu. Chỉ báo CI khi đủ mẫu; đây là các kiểm tra thăm
dò, chưa điều chỉnh cho thử nhiều phép so sánh.

- DXY, RRG Y so với Compass chỉ giá: +12,14 điểm %, CI +3,89 đến +21,38.
  So với Compass bối cảnh: +6,60 điểm %, CI −4,21 đến +18,46.
- US500, RRG Y so với Compass chỉ giá: −17,02 điểm %, CI −26,12 đến −5,09.
  RRG X so với Compass chỉ giá: −6,73 điểm %, CI −12,71 đến −0,13; cận trên
  sát 0, không nên diễn giải quá mạnh sau nhiều phép so sánh.
- BTC/ETH/E1VFVN30: các CI chênh lệch giữa RRG X/Y và Compass hướng mỗi ngày
  đều chứa 0. Chưa xác lập bên nào tốt hơn một cách ổn định.

Không dùng kết quả này để chọn riêng trục X hoặc Y thắng ở từng mã rồi tuyên
bố đó là hệ thống đã được xác nhận. Muốn làm vậy cần validation trước test và
dữ liệu tương lai chưa dùng để chọn quy tắc.

## Hai chiều, chân trời và độ ổn định

Ở RRG Y, US500 Long đúng 174/275 = 63,27%, Short đúng 139/389 = 35,73%.
Đây là vấn đề chính: momentum yếu đi không đồng nghĩa giá sẽ giảm. RRG X
US500 Long đúng 318/496 = 64,11%, Short đúng 65/173 = 37,57%. E1VFVN30 Y Long
đúng 58,36%, Short 39,18%; DXY Y cân bằng hơn: Long 59,63%, Short 58,53%.

RRG Y DXY đúng 52,23% / 59,07% / 57,08% sau 5/10/20 nến. US500 là 44,10% /
47,14% / 46,18%. Không có bằng chứng đổi chân trời sẽ tự đưa RRG lên 75%.
Báo cáo có đầy đủ các chân trời, bên Long/Short, số sai và kết quả từng năm.

RRG Y đổi trạng thái nhiều hơn RRG X: US500 59 so với 17 lần trong 679 ngày
chung; E1VFVN30 60 so với 43 lần trong 670 ngày. Nhưng Compass US500 bối cảnh
chỉ đổi 4 lần chủ yếu vì luôn nghiêng Long, không chứng minh nhận biết đảo
chiều tốt. RRG Y E1VFVN30 đúng 53,41% năm 2024, 38,55% năm 2025, 58,64% phần
2026 có kết quả; mức hiệu quả không ổn định qua năm.

## Các phát hiện về cấu hình và dữ liệu

1. SPY hiện so với chính SPY: cả 679 ngày chung đều ở 100/100. Dashboard dùng
   điều kiện >= nên gọi Leading, nhưng đây không phải tín hiệu thị trường mạnh.
   Backtest coi tọa độ chính giữa là trung tính. Chưa thay benchmark trong app.
2. BTC/ETH/DXY/US500/XAU hiện so với `$ONE`, còn E1VFVN30 so với VNINDEX.
   Không thể giải thích toàn bộ rổ là tương đối với SPY. Yếu hơn VNINDEX không
   nhất thiết đồng nghĩa E1VFVN30 giảm giá tuyệt đối.
3. StockCharts trả 1.056 điểm đã đóng từ 01/07/2022 đến 16/09/2026; Fialda trả
   690 điểm từ 01/12/2023. Phần 57 ngày trùng của yêu cầu ngắn/dài ở BTCUSD,
   ETHUSD và US500 có chênh lệch tọa độ bằng 0. Kiểm tra này không chứng minh
   toàn bộ lịch sử không từng bị nhà cung cấp sửa lại.
4. RRG crypto chỉ có lịch ngày làm việc. Compass có 990 ngày dự báo nhưng
   chỉ ghép được 679 ngày; loại cuối tuần/ngày nghỉ, không forward-fill.
   Chân trời kết quả vẫn là 5/10/20 nến của chính tài sản (crypto gồm cuối tuần).
5. Khác feed: median chênh lệch giá BTC 0,0216%, ETH 0,0256%, US500 gần 0,
   SPY 0,00007%, DXY 0,0030%, E1VFVN30 0%. DXY 05/03/2025 lệch 1,359%,
   E1VFVN30 29/07/2025 lệch 3,125%. Khi loại hai ngày này, RRG Y DXY còn
   59,01%, E1VFVN30 49,01%; kết luận không đổi. Raw giá Fialda tính nghìn VND.
6. Có RRG XAUUSD nhưng chưa có OHLC spot hợp lệ và dự báo Compass để ghép;
   không tính kết quả bằng vàng futures hoặc đổi cách đo sang close-to-close.

## Tái lập và kiểm tra

```powershell
.venv/Scripts/python.exe -m filter_pattern.rrg_comparison --sources reports/rrg-comparison-d1 --compass reports/compass-exact-d1/results.json --candles reports/compass-exact-d1/candles.json --out reports/rrg-comparison-d1
```

Lệnh chạy offline với raw response đã lưu; `results.json` có hash các đầu vào.
Raw StockCharts dùng endpoint/cấu hình production với `d=1100`, `p=d`; Fialda
yêu cầu 01/12/2023–16/09/2026. Không lưu auth token trong manifest. Các artifact
`reports/` không được git theo dõi.

31 test RRG và comparison đạt, gồm tọa độ trung tính, không dùng điểm tương
lai, không forward-fill, từ chối Long không biến thành Short, ghép đúng ngày
và so sánh trên các ngày cả hai cùng có tín hiệu.

Kiểm tra trình duyệt desktop/mobile đạt: sáu mã, chín phép đọc, chuyển cả ba
chân trời, bảng paired/Long/Short/từng năm, SPY trung tính, không lỗi JavaScript
hoặc tràn ngang trang. Đã thêm liên kết từ báo cáo Compass sang backtest này.
