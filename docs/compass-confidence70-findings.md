# Mục tiêu 70%: kết quả vòng lọc xác nhận

Ngày 18/09/2026. [Quy tắc chốt trước chạy](compass-confidence70-protocol.md).
Báo cáo: `reports/compass-confidence70-d1/index.html`.

Chưa chứng minh được mục tiêu 70% cho la bàn chung. Giữ nguyên phiên bản
bốn trạng thái và RRG; không dùng các bộ lọc mới làm tín hiệu live.

## Tỷ lệ đúng hướng sau 10 nến

2024–16/09/2026; tín hiệu close T, kết quả open T+1 → close T+10.
4.630 ngày-tài sản có đủ outcome. Các mẫu có chồng lấn và tương quan.
Trọng số cân bằng tài sản, US500/SPY mỗi mã nửa trọng số; tỷ lệ có trọng
số khác phép chia đơn giản tổng số thắng/tổng số mẫu.

| Quy tắc | Đúng hướng | Độ phủ | Mẫu | Sai | CI95 theo block |
|---|---:|---:|---:|---:|---:|
| Bản ổn định, mọi ngày | 50,65% | 100% | 4.630 | 2.244 | 46,62–54,73% |
| Xu hướng và momentum cùng chiều | 51,83% | 57,96% | 2.681 | 1.286 | 46,81–56,93% |
| Thêm xác nhận EMA50 | 51,72% | 41,44% | 1.928 | 913 | 45,20–58,21% |
| Thêm giới hạn chạy xa và nhiễu | 49,59% | 6,28% | 269 | 131 | 41,11–57,23% |
| Tham chiếu luôn tăng | 54,60% | 100% | 4.630 | 2.070 | 48,92–59,68% |

Không bộ lọc nào vượt cổng chọn/xác nhận bằng hai năm trước cho năm
2024, 2025 hoặc 2026. Dòng selected có 0 mẫu và accuracy không xác định;
không được diễn giải thành dự báo đúng hay sai 0%.

Ở bộ lọc cùng chiều, accuracy hướng tăng 56,31%, hướng giảm 45,80%.
Bộ lọc chặt nhất: tăng 56,34%, giảm 39,10%. Không có cải thiện đồng đều
cho cả hai phía. Khung 5/20 nến cũng không gần 70%; tất cả số liệu nằm
trong `results.json`, gồm cả phân tách từng năm.

## Theo đúng mã trong ảnh

| Mã | Mọi ngày | Cùng chiều | Thêm EMA50 | Thêm giới hạn |
|---|---:|---:|---:|---:|
| BTCUSD | 48,98% | 49,45% | 49,87% | 47,27% |
| ETHUSD | 50,51% | 50,63% | 51,57% | 41,82% |
| DXY | 49,03% | 52,45% | 46,52% | 48,08% |
| US500 | 57,40% | 55,10% | 59,06% | 77,27% |
| SPY | 57,70% | 54,55% | 57,89% | 74,07% |
| E1VFVN30 | 47,20% | 51,64% | 51,40% | 46,55% |
| XAUUSD | Thiếu OHLC spot đủ chuẩn | — | — | — |

US500 77,27% chỉ là 17/22 mẫu, phủ 3,29%, gồm 19 tăng và 3 giảm.
SPY 74,07% là 20/27 mẫu, phủ 4,04%, gồm 22 tăng và 5 giảm. Hai mã tương
quan cao; lịch giãn 10 nến chỉ có lần lượt 3/4 mẫu. Không đủ mẫu để báo
CI theo quy tắc đã chốt; không được chọn hai ô đẹp này làm bằng chứng 70%.

## Diễn giải và giới hạn

Làm mượt và xác nhận thêm vẫn mô tả xu hướng đang diễn ra tốt hơn việc
dự báo dấu return tương lai. Vòng này không cho thấy bộ lọc EMA/momentum
là đường tiến đáng tin tới 70%. Không chỉnh tiếp ngưỡng trên cùng dữ liệu
để cố đạt mục tiêu. Giữ bản hiện tại như công cụ quan sát; chưa gắn nhãn
“độ tin cậy 70%”. Chưa kết luận rằng mọi mô hình khác đều không thể đạt.

Dữ liệu này đã được xem ở nhiều vòng. Tách theo thời gian tránh đưa nhãn
tương lai vào chọn bộ lọc, nhưng không biến bộ dữ liệu thành holdout mới.
Muốn xác nhận giả thuyết mới cần chốt quy tắc và ghi nhận dự báo trước
khi kết quả tương lai xuất hiện, đồng thời bổ sung dữ liệu XAUUSD chuẩn.

## Chạy lại và kiểm tra

```powershell
.venv/Scripts/python.exe -X utf8 -m filter_pattern.compass_confidence70
.venv/Scripts/python.exe -X utf8 -m pytest tests/test_compass_confidence70.py tests/test_compass_rotation_stable.py -q
```

8 test đạt: không repaint, bộ lọc lồng nhau, trọng số trước lọc, flat là
sai, bỏ nhãn vượt ranh giới năm, chọn không phụ thuộc kết quả năm kiểm tra,
và không báo accuracy khi không có mẫu.

Audit dữ liệu thật: 18 prefix khớp, tính lại 13.860 return OHLC, các phase
giữ nguyên bản ổn định, baseline khớp báo cáo trước, hash nguồn khớp.
Trình duyệt không lỗi, bảng xem được trên desktop/mobile, không tràn
ngang trang. Artifact: `audit.json`, `desktop.png`, `mobile.png` trong
thư mục báo cáo; các artifact báo cáo không được git theo dõi.
