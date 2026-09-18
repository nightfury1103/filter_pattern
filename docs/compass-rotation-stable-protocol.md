# Bốn trạng thái có vùng đệm — chốt trước chạy

Ngày 18/09/2026. Một cấu hình chung cho đúng bảy mã đã chọn. RRG gốc và
các bản nghiên cứu trước giữ nguyên. XAUUSD vẫn thiếu OHLC spot hợp lệ.

Giữ gốc S=(EMA20[T]−EMA20[T−3])/ATR14[T]. Bản mới có hai thành phần:

- Xu hướng nền X=EMA5(S).
- Động lượng Y=EMA3(X[T]−X[T−5]).
- Dấu xu hướng chỉ chuyển sang dương khi X>0,10, âm khi X<−0,10; trong
  vùng đệm giữ dấu trước. Dấu động lượng dùng cùng cơ chế với biên ±0,05.
- Dấu ban đầu bằng 0; chỉ bắt đầu xác nhận dấu từ nến 200. Chưa đủ hai
  dấu thì CENTER. Bằng ngưỡng không đổi trạng thái.
- Kết hợp dấu đã xác nhận thành Leading/Weakening/Lagging/Improving.
  Không ép chiều quay, không dùng pivot tương lai, không tô lại màu.

Đây là cấu hình giả thuyết tự chọn, không dò thêm smoothing/biên sau khi
chạy. Làm mượt và giữ trạng thái có thể tăng độ trễ, không bảo đảm tăng
hiệu quả dự báo. Nhãn trạng thái dựa dấu đã xác nhận, **tọa độ vẫn là X/Y
thật**, không dịch điểm sang ô cùng màu. Vẽ vùng đệm quanh trục và giải
thích màu có thể giữ ô cũ khi điểm nằm trong vùng đệm. Không gọi đây là
JdK RRG tương đối với benchmark.

So với bản cũ trên đúng ngày 2024–2026: số đổi trạng thái, trung vị độ dài
đoạn, đoạn một nến và lần A→B→A ngay ngày sau; cả toàn kỳ lẫn 180 nến cuối.
Độ trễ đo từ sự kiện close phá đỉnh/đáy close 20 nến trước, chỉ lấy các
lần hướng phá vỡ luân phiên. Dùng cùng sự kiện cho hai phương án, báo đã
nhận hướng tại T / trong 10 nến / bỏ lỡ, median trễ trên các sự kiện cả hai
nhận được. Đây là mốc kỹ thuật có thể tái lập, không là đỉnh/đáy thực.

Giữ thống kê return open T+1 → close T+5/10/20 theo màu. Thêm kiểm tra
hướng nền dương/âm so return tương lai, không đồng nhất màu Improving với
dự báo tăng hoặc Weakening với dự báo giảm. Báo accuracy/coverage/CI cho
chẩn đoán hướng nền, không dùng nó để biến màu thành lệnh. Tổng rổ có
trọng số cân bằng mã (US500/SPY mỗi mã nửa trọng số). Không hạ tiêu chí
75%; dữ liệu đã được xem nên chỉ là hồi cứu.

UI cho chọn Bản ổn định / Bản cũ trên cùng biểu đồ; mặc định BTC, bốn màu,
không nhãn Long/Short trên giá. Bảng so sánh trình bày giảm nhiễu và độ
trễ cạnh nhau, không chọn riêng chỉ số đẹp để công bố thành công.
