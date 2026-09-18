# Bốn trạng thái có vùng đệm — kết quả

Ngày 18/09/2026. [Quy tắc chốt trước chạy](compass-rotation-stable-protocol.md).
Báo cáo: `reports/compass-rotation-stable-d1/index.html`; chọn Bản ổn định
hoặc Bản cũ để đối chiếu cùng ngày, mã, cửa sổ giá. Mặc định BTC.

## Kết luận

Giảm đổi màu rõ, nhưng phản ứng chậm hơn và chưa cải thiện dự báo hướng
giá tương lai. Phù hợp hơn cho việc quan sát chu kỳ ít nhiễu, chưa đáp ứng
la bàn định hướng đáng tin với mục tiêu 75%. Không thay RRG/scanner hoặc
xóa bản cũ. Một cấu hình chung cho toàn rổ; không chỉnh thêm sau chạy.

Xu hướng nền X=EMA5(S), với S=(EMA20[T]−EMA20[T−3])/ATR14[T]. Động lượng
Y=EMA3(X[T]−X[T−5]). Mỗi dấu chỉ đổi khi vượt hẳn biên đối diện: ±0,10
cho X, ±0,05 cho Y. Khi nằm trong biên, giữ dấu trước. Hai dấu được kết
hợp thành bốn trạng thái; chưa đủ dấu thì CENTER. Khởi tạo từ warmup200,
tính trên toàn bộ lịch sử nguồn trước khi cắt kỳ đánh giá.

## Độ ổn định trên 180 nến cuối

| Mã | Đổi màu: cũ → mới | Đổi rồi quay về ngay ngày sau | Trung vị độ dài đoạn màu |
|---|---:|---:|---:|
| BTCUSD | 35 → 18 | 5 → 0 | 5 → 7 |
| ETHUSD | 37 → 17 | 2 → 0 | 3,5 → 7,5 |
| DXY | 38 → 28 | 0 → 0 | 5 → 6 |
| US500 | 39 → 24 | 2 → 0 | 3 → 6 |
| SPY | 37 → 26 | 1 → 0 | 3 → 5 |
| E1VFVN30 | 28 → 21 | 1 → 0 | 6 → 8 |

Toàn kỳ cả sáu mã cộng số lần đổi màu từ 938 còn 549 (giảm 41,5%). Đây là
số cộng mô tả, không là các sự kiện độc lập: US500/SPY và các thị trường
khác có tương quan. Không có nhãn nhị phân Long/Short trên biểu đồ.

## Đánh đổi về tốc độ nhận diện

Dùng cùng các mốc close phá đỉnh/đáy close 20 nến, chỉ giữ lần phá vỡ đổi
phía. Đây không phải nhãn đỉnh/đáy thật. Mỗi lần được nhận nếu dấu xu
hướng khớp trong 10 nến, kể cả đã khớp ngay tại mốc.

| Mã | Số mốc | Nhận ngay: cũ → mới | Nhận trong 10 nến: cũ → mới |
|---|---:|---:|---:|
| BTCUSD | 32 | 30 → 16 | 32 → 30 |
| ETHUSD | 30 | 28 → 12 | 30 → 26 |
| DXY | 20 | 20 → 4 | 20 → 20 |
| US500 | 19 | 17 → 8 | 19 → 18 |
| SPY | 19 | 17 → 7 | 19 → 18 |
| E1VFVN30 | 18 | 16 → 8 | 18 → 18 |

Tổng 138 mốc theo mã: nhận ngay 128 → 55, nhận trong 10 nến 138 → 130.
Median trễ thêm trên cùng các sự kiện cả hai nhận được là 0 nến với BTC,
1 nến ở năm mã còn lại. Không dùng median này để che số nhận ngay giảm
và số bỏ lỡ tăng: bảng UI hiển thị cả ba. Mốc phá vỡ xảy ra sau khi một
phần sóng đã chạy nên không đo độ trễ từ đáy/đỉnh tuyệt đối.

Ví dụ BTC: chuyển Lagging 19/05 (bản cũ 17/05), Leading 12/07 (bản cũ
04/07). Độ trễ không cố định một nến; các sự kiện khác nhau có đánh đổi
khác nhau. Màu giữ lâu hơn không tự chứng minh hướng đúng hơn.

## Hướng tương lai chưa cải thiện

Chẩn đoán dấu xu hướng nền (không chuyển màu Improving/Weakening thành
lệnh), cùng ngày và cùng return open T+1 → close T+10:

| Mã | Bản cũ | Bản ổn định |
|---|---:|---:|
| BTCUSD | 50,1% | 49,0% |
| ETHUSD | 49,9% | 50,5% |
| DXY | 55,4% | 49,0% |
| US500 | 56,5% | 57,4% |
| SPY | 55,6% | 57,7% |
| E1VFVN30 | 51,1% | 47,2% |
| Cả rổ có trọng số | 52,5% | 50,7% |

Độ phủ 100% trên 4.630 ngày-tài sản đủ nhãn 10 nến cho cả hai. Con số cũ
52,5% là dấu X của bản bốn trạng thái, khác rule giữ hướng EMA/ATR ban đầu.
Sáu mã đủ dữ liệu; XAUUSD chưa kiểm thử vì thiếu OHLC spot. Dữ liệu đã
được xem nhiều vòng, không phải holdout mới.

Sau trạng thái Leading của bản mới, tỷ lệ giá tăng 10 nến có trọng số là
56,3%; sau Lagging, tỷ lệ giảm là 45,8%. Báo cáo có đầy đủ phân bố tăng,
giảm, flat và return trung bình cho 5/10/20 nến, toàn rổ và từng mã, cho
cả hai phiên bản. Đây là thống kê hồi cứu theo trạng thái, không phải
xác suất được bảo đảm hay bằng chứng 75%.

## Hiển thị và kiểm tra

Tọa độ vẫn là X/Y thật, không đổi dấu tọa độ để ép điểm về ô cùng màu.
Dải xám trên la bàn hiển thị vùng đệm. Màu có thể giữ trạng thái cũ khi
điểm vừa qua trục và còn trong dải này; ngoài cả hai dải, quadrant phải
khớp màu. Tooltip dòng giá ghi rõ khi đang ở vùng đệm. Đây là trạng thái
của xu hướng đã xác nhận bằng biên, không là xác nhận hiệu quả giao dịch.

```powershell
.venv/Scripts/python.exe -m filter_pattern.compass_rotation_stable
.venv/Scripts/python.exe -m pytest tests/test_compass_rotation_stable.py tests/test_compass_rotation.py tests/test_compass_wave.py -q
```

11 test đạt. Kiểm tra vùng đệm và ngưỡng chặt, không đổi trạng thái chỉ vì
qua 0, xu hướng/momentum khởi tạo, chuỗi phẳng, không repaint khi thay dữ
liệu tương lai, độ trễ dùng cùng sự kiện và giữ số bỏ lỡ.

Audit trên dữ liệu thật: phát lại 9.380 trạng thái của hai bản; 18 kiểm
tra prefix; tính lại 13.860 return OHLC; mọi số ngày tăng/giảm/flat theo
mã/mô hình/trạng thái/chân trời khớp; đối chiếu độ trễ từng sự kiện và hash
nguồn/code đều đạt. Trình duyệt: 2.160 trạng thái màu, 216 dòng bảng phase,
hai chế độ model, dải vùng đệm, thẻ/giá khớp, thiếu XAU trống, ngày replay
không có giá tương lai, bảy dòng bảng so sánh, desktop/mobile không lỗi
JS hoặc tràn ngang. Artifact: `reports/compass-rotation-stable-d1/audit.json`,
`btc-price.png`, `desktop.png`, `mobile.png`; không được git theo dõi.
