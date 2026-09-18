# Bản chu kỳ sóng giá theo bốn trạng thái

Ngày 18/09/2026. [Quy tắc](compass-rotation-protocol.md) được ghi trước chạy.
Mở `reports/compass-rotation-d1/index.html`, mặc định BTC. Giữ nguyên bản
sóng giá Long/Short để so sánh ở `reports/compass-wave-d1/index.html`.

## Nội dung thay đổi

X=(EMA20[T]−EMA20[T−3])/ATR14[T], Y=X[T]−X[T−5], giống tọa độ của bản sóng
giá trước. Không đổi tham số, không học lại hoặc tối ưu trên BTC. Bản mới
dùng trạng thái dấu X/Y làm nội dung chính ở mọi thẻ, đuôi, mũi tên và
đường giá; không hiện nhãn hoặc chấm Long/Short. Không ép chiều quay.

| Trạng thái | Ý nghĩa trên giá tuyệt đối | Màu |
|---|---|---|
| Leading | Xu hướng tăng, độ dốc mạnh lên | Xanh lá |
| Weakening | Xu hướng vẫn tăng, độ dốc giảm | Cam |
| Lagging | Xu hướng giảm, độ dốc âm mạnh thêm | Đỏ |
| Improving | Xu hướng vẫn giảm, độ dốc âm dịu lại | Xanh dương |

Trên trục giữ trung tính; thiếu dữ liệu không bịa tọa độ. Đây là ứng dụng
nguyên lý strength/momentum của RRG vào xu hướng giá tuyệt đối, không là
JdK RRG hoặc đo hiệu suất vượt benchmark. RRG gốc không bị sửa.

## Thống kê kiểm tra theo trạng thái

Phân bố return sau 10 nến toàn rổ, có trọng số cân bằng tài sản và giảm
nửa trọng số US500/SPY. Số ngày là số thô, có cửa sổ chồng lấn. Không đổi
bốn trạng thái thành dự báo nhị phân để gọi các tỷ lệ này là accuracy.

| Trạng thái | Ngày-tài sản | Giá tăng sau đó | Giá giảm sau đó | Return trung bình |
|---|---:|---:|---:|---:|
| Leading | 1.582 | 55,6% | 44,4% | +0,89% |
| Weakening | 1.137 | 57,3% | 42,6% | +0,86% |
| Lagging | 1.202 | 52,8% | 47,1% | +0,49% |
| Improving | 709 | 51,6% | 48,0% | −0,11% |

Phần còn lại là return bằng 0; bảng đầy đủ giữ flat. Màu mô tả chu kỳ
hiện tại, không bảo đảm tiếp diễn sau 10 nến: kết quả trên không chứng
minh 75%. Có lựa chọn 5/10/20 nến và từng mã để đối chiếu, cùng số lần
chuyển trạng thái trong JSON. XAUUSD vẫn thiếu OHLC spot hợp lệ. Dữ liệu
2024–2026 đã xem nhiều vòng nên vẫn là hồi cứu.

## Tái lập và kiểm tra

```powershell
.venv/Scripts/python.exe -m filter_pattern.compass_rotation
.venv/Scripts/python.exe -m pytest tests/test_compass_rotation.py tests/test_compass_wave.py -q
```

7 test đạt: bốn dấu, biên/trống, không dùng return tương lai để gán màu,
không ép chu kỳ hoặc tạo bias nhị phân, giữ flat và thiếu outcome; kèm
kiểm tra nhận diện sóng và không repaint của bản trước.

Trình duyệt kiểm tra 1.080 màu ngày trên sáu mã, đồng bộ màu thẻ/đường giá,
108 dòng thống kê (sáu mã × ba kỳ × sáu trạng thái kể cả trung tính/thiếu),
sáu thẻ/bảy mã/sáu đuôi có dữ liệu, XAU trống, các cửa sổ, xem lại ngày
không lộ giá tương lai, bàn phím và mobile không lỗi JS/tràn ngang. Hash
nguồn và code khớp. Có ảnh desktop/mobile và BTC tại thư mục báo cáo.

## Review sau khi xem biểu đồ

Đối chiếu lại mã nguồn, biểu đồ BTC và kết quả lưu: bản mới đọc chu kỳ dễ
hơn nhưng chưa có thêm bằng chứng về lợi thế dự báo. Nó dùng cùng tọa độ
EMA/ATR của bản sóng giá; thay nhãn bốn ô không bổ sung thông tin đầu vào.

1. **Cơ chế giữ hướng của bản trước chưa đi vào bốn trạng thái.** Bản
   Long/Short dùng vùng đệm 0,5 ATR và giữ hướng trước. Bản rotation chỉ
   xét dấu X/Y tại đúng 0, nên dao động nhỏ quanh trục vẫn đổi màu ngay.
   Trung tính đòi hỏi một tọa độ bằng đúng 0, thực tế không có ngày trung
   tính trong kỳ chung 4.630 ngày-tài sản có đủ outcome 10 nến.
2. **Có các lần đổi màu ngắn cần kiểm tra.** BTC trong 180 nến mới nhất
   đổi trạng thái 35 lần, gồm 5 lần đổi rồi quay về trạng thái cũ ngay ngày
   kế tiếp; trung vị một đoạn màu là 5 nến. Toàn kỳ BTC 990 ngày: 204 lần
   đổi, 40 đoạn chỉ tồn tại một nến, 19 lần quay lại ngay ngày kế tiếp.
   Đổi quadrant không mặc nhiên là sai, nhưng những lần ngắn này làm
   giảm độ ổn định cho nhu cầu la bàn D1.
3. **Các màu chưa phân tách tương lai đủ tốt.** Riêng BTC: Leading có
   155/302 ngày giá tăng sau 10 nến (51,3%); Lagging có 139/294 ngày giá
   giảm (47,3%). Tỷ lệ tăng vô điều kiện trên cùng kỳ là 52,35%. Trên
   toàn rổ có trọng số, Leading có 55,6% tăng sau đó, còn Weakening 57,3%.
   Các nhóm chọn ngày khác nhau nên đây là mô tả, không là kiểm định
   chênh lệch có ý nghĩa thống kê. Chưa có cơ sở dùng tên màu như xác
   suất tiếp diễn, hoặc tuyên bố đạt 75%.

Nhận định kỹ thuật: trước khi thêm chỉ báo, cần thử tách xu hướng nền ổn
định khỏi sự thay đổi động lượng, đồng thời đánh giá một vùng đệm hoặc
điều kiện xác nhận chuyển ô. Đây là giả thuyết cho vòng sau, chưa được
triển khai hoặc chứng minh trong review này. Việc giảm đổi màu cũng có
thể tăng độ trễ; phải đo cả hai và giữ phép đo tương lai riêng.

Số liệu ổn định cả sáu mã được lưu tại
`reports/compass-rotation-d1/review-stability.json`. Không sửa quy tắc,
biểu đồ hoặc kết quả backtest trong lần review.
