# Nhận diện sóng giá: kết quả vòng đầu

Ngày 18/09/2026. [Protocol](compass-wave-protocol.md) được ghi trước khi chạy.
Một cấu hình EMA20/ATR14/vùng đệm 0,5 ATR và độ dốc EMA qua 3 nến, cùng
quy tắc cho toàn bộ rổ. Không tối ưu sau khi xem kết quả. RRG, các mô hình
và backtest trước giữ nguyên. XAUUSD vẫn thiếu dữ liệu spot hợp lệ.

## Kết luận

Màu Long/Short mô tả hướng sóng đang chạy rõ hơn màu quadrant từ xác suất
analog. Nhưng đây chưa là cải thiện dự báo tương lai: accuracy 10 nến có
trọng số toàn rổ là 53,03%, so analog hướng mỗi ngày 54,75% và luôn Long
54,60%. Không đạt yêu cầu 75%, không triển khai làm bộ lọc giao dịch đã
được xác nhận. Bộ nhận diện không biết đỉnh/đáy tức thời và vẫn sai khi
giá đi ngang hoặc vừa đảo chiều.

## Hai thước đo khác nhau

“Khớp hướng đã qua” so hướng tại close T với dấu close T/close T−10−1;
đây là mô tả độ bám giá, có dùng dữ liệu giá quá khứ trong chính quy tắc,
không phải bằng chứng dự báo. “Đúng sau 10 nến” giữ nguyên phép đo trước:
open T+1 → close T+10. Không được thay thế thước đo thứ hai bằng thứ nhất.

| Mã | Khớp hướng 10 nến đã qua | Đúng sau 5 nến | Đúng sau 10 nến | Đúng sau 20 nến |
|---|---:|---:|---:|---:|
| BTCUSD | 83,2% | 48,8% | 51,5% | 49,2% |
| ETHUSD | 78,1% | 50,2% | 53,2% | 54,1% |
| DXY | 80,0% | 52,2% | 54,1% | 51,6% |
| US500 | 82,5% | 57,0% | 57,4% | 61,6% |
| SPY | 82,9% | 56,2% | 57,0% | 62,1% |
| E1VFVN30 | 83,3% | 50,3% | 49,2% | 49,9% |
| XAUUSD | Chưa có dữ liệu | — | — | — |

Độ phủ 100% trên kỳ chung có nhãn 10 nến, với 2.753 Long và 1.877 Short.
Tỷ lệ đúng tổng có trọng số 53,03%; số đúng thô 2.479/4.630, khác tỷ lệ có
trọng số vì cân bằng tài sản và giảm nửa trọng số US500/SPY.

BTC có 47 lần đổi trạng thái trên 990 ngày dự báo. 230 ngày có hướng đối
nghịch xuất hiện trong 5 nến kế tiếp; đây là số ngày tín hiệu, không phải
230 lần đổi hướng độc lập. Trong 180 nến gần nhất, màu thật gồm 99 Long và
81 Short. Chuyển Short 17/05/2026, Long 05/07/2026; không đổi màu từ đỉnh
tháng 5 hoặc đáy tháng 6 khi nhìn lại. Có nhiều lần đảo qua lại tháng 8.
Trong 170 ngày gần nhất có đủ nhãn 10 nến: đúng 96/170 (56,5%), analog
105/170 (61,8%), luôn Long 95/170 (55,9%). Không chọn riêng một đoạn sóng
đẹp để khẳng định hiệu quả.

## Báo cáo và kiểm tra

```powershell
.venv/Scripts/python.exe -m filter_pattern.compass_wave
.venv/Scripts/python.exe -m pytest tests/test_compass_wave.py -q
```

Mở `reports/compass-wave-d1/index.html`; mặc định biểu đồ giá BTC và tô
Long/Short thực tế. La bàn bốn ô sử dụng điểm EMA/ATR, không gắn phần trăm
xác suất cho quy tắc giá. Có đối chứng EMA20/50 và analog theo ngày, xem lại
ngày, các cửa sổ 60/180/360/toàn kỳ và dữ liệu Long/Short/từng năm thu gọn.

4 test đạt: giữ hướng trong vùng đệm, điều kiện đối xứng và ngưỡng chặt,
chuỗi tăng/giảm tổng hợp không tô lại về đỉnh, bất biến khi thay tương lai,
giá phẳng và dữ liệu rỗng. Kiểm tra prefix trên 18 đoạn lịch sử thật khớp
chuỗi tính đầy đủ. Tính lại 13.860 return từ OHLC và mọi số đúng/tín hiệu
theo mô hình/hướng/chân trời khớp; hash nguồn và code khớp.

Trình duyệt đối chiếu 3.240 trạng thái ngày với dữ liệu lưu cho ba mô hình
và sáu mã; đủ sáu thẻ/bảy mã, XAU trống, không hiển thị giá tương lai,
không gắn xác suất giả, không lỗi JS/tràn ngang trên mobile. Chạy lại kiểm
tra biểu đồ analog cũ: 4.320 màu tín hiệu và 4.320 màu quadrant vẫn khớp.
Chi tiết ở `reports/compass-wave-d1/audit.json`; artifact local không được
git theo dõi. Tất cả kết quả vẫn hồi cứu trên dữ liệu đã xem nhiều lần.
