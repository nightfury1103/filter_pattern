# Compass D1: kiểm tra xu hướng chậm và nhịp hồi

Ngày 18/09/2026. [Quy tắc chốt trước chạy](compass-reversion-protocol.md).
Báo cáo: `reports/compass-reversion-d1/index.html`.

## Kết luận

Ba giả thuyết mới chưa cải thiện tỷ lệ đúng hướng sau 10 nến và không đạt
70%. Không chọn được quy tắc vượt cổng phát triển/xác nhận cho năm 2024,
2025 hoặc 2026. Không thay RRG, bản bốn trạng thái, biểu đồ giá hoặc setup.
Đây là kết quả thất bại cần giữ lại, không phải cơ sở để đảo ngược mọi
tín hiệu rồi tuyên bố có mô hình tốt hơn.

## Kết quả chính

Tín hiệu close T, return open T+1 → close T+10. Cùng 4.630 ngày-tài sản
đủ outcome trong 2024–16/09/2026; tín hiệu cuối kỳ thiếu kết quả bị loại
riêng theo chân trời. Flat tính sai. Trọng số cân bằng tài sản, US500/SPY
mỗi mã nửa. Mẫu có tương quan/chồng lấn; các tỷ lệ có trọng số không bằng
phép chia tổng thắng/tổng mẫu.

| Quy tắc | Đúng hướng | Độ phủ | Mẫu | Sai | CI95 block |
|---|---:|---:|---:|---:|---:|
| Bản ổn định, mọi ngày | 50,65% | 100% | 4.630 | 2.244 | 46,62–54,73% |
| Vòng trước: xu hướng/momentum cùng chiều | 51,83% | 57,96% | 2.681 | 1.286 | 46,81–56,93% |
| Hồi về EMA20 | 46,54% | 49,68% | 2.332 | 1.260 | 41,46–52,35% |
| Điều chỉnh trong xu hướng chậm | 47,93% | 10,38% | 488 | 245 | 38,56–56,24% |
| Hồi phục theo xu hướng chậm | 40,85% | 3,97% | 179 | 102 | 29,86–52,81% |
| Tham chiếu luôn tăng | 54,60% | 100% | 4.630 | 2.070 | 48,92–59,68% |

Các phương án mới có tỷ lệ điểm thấp hơn, nhưng các khoảng bất định còn
rộng; không tuyên bố mọi chênh lệch đều có ý nghĩa thống kê. Dòng selected
không có mẫu, accuracy không xác định, không phải 0% chính xác.

## Từng mã, đúng sau 10 nến

| Mã | Hồi về EMA20 | Điều chỉnh | Hồi phục |
|---|---:|---:|---:|
| BTCUSD | 48,75% / 439 mẫu | 52,48% / 101 | 48,84% / 43 |
| ETHUSD | 49,78% / 450 | 46,85% / 111 | 43,75% / 48 |
| DXY | 51,12% / 313 | 34,78% / 69 | 23,33% / 30 |
| US500 | 41,03% / 390 | 59,46% / 74 | 55,56% / 18 |
| SPY | 41,22% / 393 | 58,11% / 74 | 52,94% / 17 |
| E1VFVN30 | 43,80% / 347 | 45,76% / 59 | 39,13% / 23 |
| XAUUSD | Thiếu OHLC spot đủ chuẩn | — | — |

Không có mã nào chạm tỷ lệ điểm 70% ở ba giả thuyết này. Báo cáo HTML có
đủ tỷ lệ và số mẫu riêng cho hướng tăng/giảm, từng mã, từng năm. BTC không
được cải thiện rõ: tốt nhất trong ba là 52,48% nhưng chỉ 101 mẫu.

## Chân trời phụ

| Giả thuyết | 5 nến | 10 nến chính | 20 nến |
|---|---:|---:|---:|
| Hồi về EMA20 | 49,15% | 46,54% | 43,53% |
| Điều chỉnh | 53,05% | 47,93% | 50,78% |
| Hồi phục | 40,72% | 40,85% | 41,02% |

Không đổi mục tiêu sang 5 nến chỉ vì có một ô nhỉnh hơn.

## Ý nghĩa cho bước phát triển

Các vòng vừa rồi chưa cung cấp bằng chứng rằng thêm vài điều kiện lên
EMA/momentum sẽ tạo được la bàn đúng 70%. Không kết luận mọi mô hình
chỉ dùng giá đều không thể đạt, cũng không lấy màu nhìn hợp sóng làm
thay thế cho khả năng dự báo. Chưa đưa quy tắc mới vào UI định hướng.

Các ngưỡng của vòng này giữ nguyên sau khi xem kết quả. Dữ liệu kiểm
tra đã được xem ở nhiều vòng nên đây vẫn là nghiên cứu hồi cứu. Nếu
tiếp tục phát triển, cần một giả thuyết có thông tin bổ sung rõ ràng,
cùng kế hoạch ghi nhận dự báo trước khi giá tương lai xuất hiện; tránh
tiếp tục tìm ngưỡng trên cùng lịch sử. Muốn kết luận đủ rổ còn cần XAUUSD
spot chuẩn. Nguồn học thuật trong protocol chỉ gợi ý phân biệt hai cơ
chế; nghiên cứu này không tái tạo kết quả hay mô hình của bài báo.

## Chạy lại và kiểm tra

```powershell
.venv/Scripts/python.exe -X utf8 -m filter_pattern.compass_reversion
.venv/Scripts/python.exe -X utf8 -m pytest tests/test_compass_reversion.py tests/test_compass_confidence70.py tests/test_compass_rotation_stable.py -q
```

12 test đạt, gồm đối xứng tăng/giảm, biên điều kiện, không giữ tín hiệu
lọc ngoài điều kiện, không repaint, chọn chỉ bằng năm trước, cùng các
kiểm tra trọng số/purge của vòng trước.

Audit nguồn thật: 18 prefix, phát lại 4.690 dòng, tính lại 13.860 outcome
từ OHLC và 21 bộ số liệu tổng hợp bằng phép tính trọng số độc lập. Các
baseline/phase khớp hoàn toàn vòng trước, hash nguồn hợp lệ. Trình duyệt
có đủ 9 bảng, liên kết nội bộ hợp lệ, không lỗi JS hoặc tràn trang mobile.
Artifact audit, script kiểm tra và ảnh desktop/mobile lưu cùng báo cáo
trong `reports/compass-reversion-d1/` (không được git theo dõi).
