# filter_pattern

D1/H4 pattern scanner and proof-report generator for TradingView-compatible OHLCV CSV exports.

The first version is intentionally TradingView-first and correctness-first:

- Input: CSV candles with `datetime` or TradingView `time`, plus `open`, `high`, `low`, `close`, `volume`.
- Scan target: D1 and H4.
- Pattern: configurable Minervini-style VCP defaults.
- Output: `results.json`, annotated PNG charts, and an HTML report.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

## Configure Symbols

Create `config.yml`, then point each `csv_path` at your exported TradingView D1 or H4 CSV file.

```bash
filter-pattern init-config --out config.yml
```

```yaml
timeframe: D1
technique: minervini-vcp
setup: all
symbols:
  - symbol: AAPL
    market: US stock
    tradingview_symbol: NASDAQ:AAPL
    csv_path: data/AAPL_D1.csv
```

Each CSV should contain:

```csv
datetime,open,high,low,close,volume
2025-01-01,100,105,99,104,1200000
```

TradingView exports using `time` are accepted too:

```csv
time,open,high,low,close,Volume
2026-01-01T04:00:00,100,105,99,104,1200000
```

## Run

Scan your own TradingView CSV exports:

```bash
filter-pattern scan --config config.yml --timeframe D1 --out reports/latest
```

Scan your TradingView CSV exports across every implemented setup in one report:

```bash
filter-pattern scan-all --config config.yml --timeframe D1 --out reports/tradingview-d1
filter-pattern scan-all --config config.yml --timeframe H4 --out reports/tradingview-h4
```

Choose the pattern technique:

```bash
filter-pattern scan --config config.yml --timeframe D1 --out reports/latest --technique minervini-vcp
filter-pattern scan --config config.yml --timeframe D1 --out reports/latest --technique nhathoai --setup rb
filter-pattern scan-market --config config.yml --timeframe D1 --out reports/setup-filter --universe broad --broker exness --technique nhathoai --setup all
filter-pattern scan --config config.yml --timeframe D1 --out reports/latest --technique experimental-ema21-compression
```

You can also set `technique` and `setup` in `config.yml`. CLI flags override the config values when provided.
For `--technique nhathoai`, `--setup all` writes one report with separate evaluations for `DD`, `FB`, `SB`, `BB`, `RB`, `IRB`, `ARB`, and Nhật Hoài `VCP`; use the report's setup filter to inspect one setup at a time.

Download and scan the built-in cross-market universe with Yahoo Finance data:

```bash
filter-pattern scan-market --config config.yml --timeframe D1 --out reports/market
```

Use the broader S&P 500 + cross-market universe:

```bash
filter-pattern scan-market --config config.yml --timeframe D1 --out reports/market --universe broad
```

Filter commodities, forex, and US stocks to symbols supported by Exness:

```bash
filter-pattern scan-market --config config.yml --timeframe D1 --out reports/market --universe broad --broker exness --technique minervini-vcp
```

Use exchange data for crypto instead of Yahoo Finance:

```bash
filter-pattern scan-all-market --timeframe H4 --out reports/market-h4 --period 60d --universe default --data-provider mixed
```

Provider options:

- `--data-provider mixed`: recommended, uses Yahoo Finance first, VNStock as a Vietnam-stock fallback when Yahoo is missing/too short, and CCXT exchange data for crypto.
- `--data-provider yahoo`: uses Yahoo Finance for every market. This is faster, but crypto candles may not match TradingView `BINANCE:*USDT` charts.
- `--data-provider ccxt`: crypto-only data source; non-crypto symbols are reported as unsupported for this provider.
- `--data-provider vnstock`: Vietnam-stock-only source for direct VNStock testing.

VNStock is an optional dependency. Install it with `python -m pip install -e '.[vnstock]'` before using the direct VNStock provider or Vietnam fallback data.
For crypto, CCXT tries Binance first, then Bybit, then OKX. This keeps the scanner closer to TradingView USDT-pair charts than Yahoo's `*-USD` crypto data.
VNStock guest access is rate-limited, so the scanner throttles fallback calls with `VNSTOCK_REQUESTS_PER_MINUTE=18` by default. Use a lower value if the API rejects requests, or a higher value only if your VNStock account allows it.

Technique behavior:

- `minervini-vcp` is the existing Minervini-style VCP scanner. `vcp` is kept as a backward-compatible alias.
- `nhathoai` scans the Nhật Hoài / Bob Volman style setup set: `dd`, `fb`, `sb`, `bb`, `rb`, `irb`, `arb`, and `vcp`.
- `experimental-ema21-compression` is the old rough EMA21 compression detector. It is kept separate so it cannot be mistaken for an exact Nhật Hoài setup.

The HTML report shows every attempted symbol grouped by market, plus data-unavailable counts by market. This matters because Yahoo Finance does not cover every Vietnam, crypto, forex, or commodity symbol that TradingView can display.

If your shell has both conda Python and Apple system Python, prefer `python` while your conda or virtual environment is active. `python3` may point to `/Library/Developer/...` and miss installed dev tools like `pytest`.

This writes:

- `reports/latest/results.json`
- `reports/latest/index.html`
- `reports/latest/charts/{symbol}.png`

Regenerate only the HTML report:

```bash
filter-pattern report --input reports/latest/results.json --out reports/latest/index.html
```

Combine multiple scan outputs into one filterable HTML report:

```bash
filter-pattern combine-report \
  --inputs reports/candidate-check-vcp/results.json reports/candidate-check-ema21/results.json reports/nhathoai-rules/results.json \
  --out reports/combined/index.html
```

You can also run without installing the console script:

```bash
python -m filter_pattern.cli scan --config config.yml --timeframe D1 --out reports/latest
```

## VCP Rules In V1

The detector checks:

- prior uptrend before the base.
- 2 to 4 contractions.
- progressively tightening contraction depth.
- volume dry-up in the late contraction.
- current close below pivot and within the configured near-pivot zone.

Defaults live in `examples/config.example.yml` and can be tuned per scan.

## Test

```bash
python -m pytest
```

## D1 Market Compass Research

An isolated experiment compares three symmetric `LONG` / `SHORT` / `WAIT`
models: EMA20/50, EMA/ATR with five-bar change, and volatility-normalized
20/60/120-bar momentum with an efficiency filter. It does not change RRG,
pattern qualification, or the existing direction authority.

```bash
filter-pattern compass-research --out reports/compass-d1 --period 10y
```

The Vietnamese HTML report includes instrument selection, historical signal
replay, 5/10/20-bar forward outcomes, directional base rates, coverage, actual
adverse excursions, stability, and chronological holdout evidence. Saved
`candles.json` includes provenance and data hashes; repeat without network:

```bash
filter-pattern compass-research --cache reports/compass-d1/candles.json --out reports/compass-replay
```

For exact TradingView instruments, pass a D1 CSV `--config` using the existing
configuration format. `--before YYYY-MM-DD` excludes that date and later bars.
`--rrg-results path/to/results.json` optionally displays an existing RRG
snapshot alongside the compass, retaining its original benchmark/date. It is
not a historical RRG A/B backtest.

Built-in sources label spot, ETF and futures proxies explicitly. Invalid OHLC
series remain unavailable; stale data forces the current view to WAIT.
`promising` is a provisional evidence label, never an automatic trade permission.
Directional accuracy does not establish setup profitability after costs.
See [the fixed experiment protocol](docs/market-compass-research.md).

## Deploy To GitHub Pages

This repo includes `.github/workflows/scanner-pages-v2.yml` for scheduled website deployment.

Recommended first run:

1. Push the repo to GitHub.
2. In GitHub, open **Settings -> Pages** and choose **GitHub Actions** as the source.
3. Open **Actions -> Scanner Pages -> Run workflow**.
4. Run the workflow.

After that, the workflow refreshes:

- D1 and H4 every 2 hours.

The workflow deploys the static `public/` folder directly with GitHub Pages. A separate `scanner-state` branch stores compact per-shard watchlist state so change tracking does not need to download or push the full generated website.

The site root is a lightweight D1/H4 selector. Detailed reports keep every lifecycle-review result searchable and filterable: the highest-ranked 300 use detailed inline cards, while the remainder use compact cards with lazy-loaded Pattern and RRG charts. Compact cards preserve the original chart links and expose complete metrics, evidence, direction authority, RRG reference, and lower-timeframe review on demand. Only qualified candidates retain full-resolution pattern-chart assets; other visible results use previews so the published site stays within GitHub Pages' size budget. Complete evaluations also remain available in each timeframe's `results.json`. Published chart filenames include a content hash, so a newly generated image cannot be confused with an older GitHub Pages cache entry. Reports also show the latest candle timestamp as `Data as of`.

Each scan compares the new qualified watchlist with the previous `results.json` for the same timeframe. The report marks candidates as:

- `New`
- `Triggered change`
- `Improved`
- `Weaker`
- `Status changed`
- `Unchanged`
- `Dropped`

Use the report's **All changes** filter to review only symbols that changed since the last run.

The workflow uses these defaults:

```text
DATA_PROVIDER=mixed
BROKER=exness
D1_PERIOD=180d
H4_PERIOD=60d
D1_UNIVERSE=default
H4_UNIVERSE=default
D1_MARKETS=all
H4_MARKETS=US stock,Commodity,Forex,Crypto
```

### La bàn dự báo D1 độc lập với setup (nghiên cứu vòng 2)

Không dùng detector hoặc TP/SL. Dự báo hướng từ open nến sau đến close sau
10 nến; Long / Short / Chưa rõ. Ngưỡng xác suất 75% cố định, cần kiểm chứng
bằng tỷ lệ đúng thực tế và độ phủ; không bảo đảm hiệu quả live.

```powershell
uv pip install --python .venv/Scripts/python.exe '.[research]'
.venv/Scripts/python.exe -m filter_pattern.cli compass-forecast --cache reports/compass-d1/candles.json --out reports/compass-forecast-d1 --before 2026-09-17
```

Mở `reports/compass-forecast-d1/index.html`. Tham số, chia thời gian và nguồn
được lưu trong `protocol.json` / `results.json`; model chỉ lưu cho nghiên cứu,
scanner không tải model. Xem [phạm vi vòng 2](docs/setup-compass-v2.md).
Dữ liệu đánh giá trùng một phần nghiên cứu trước; phải coi là kiểm tra hồi
cứu, chưa phải xác nhận bằng dữ liệu mới. RRG được giữ nguyên.

Kết quả và đính chính dữ liệu: [báo cáo vòng 2](docs/compass-forecast-findings.md).
Nguồn VN30_ETF trong báo cáo vòng một không đủ chất lượng; không dùng các
số liệu đó để kết luận hiệu quả la bàn.

### La bàn D1 theo đúng các mã trong ảnh

Bản thử riêng XAUUSD, BTCUSD, ETHUSD, DXY, US500, SPY và E1VFVN30, trình bày
sáu thẻ cùng biểu đồ bốn quadrant có lịch sử và mũi tên. Chọn mô hình riêng từng
mã bằng dữ liệu trước năm test; giữ nguyên RRG và scanner.

```powershell
.venv/Scripts/python.exe -m filter_pattern.cli compass-exact --cache reports/compass-exact-d1/input-candles.json --context-cache reports/compass-context-d1/context-sources.json --out reports/compass-exact-d1 --before 2026-09-17
```

Mở `reports/compass-exact-d1/index.html`. Cần các cache nghiên cứu đã chuẩn bị;
lệnh này không tự tải dữ liệu. Hiện sáu mã có dữ liệu kiểm thử, XAUUSD spot còn
thiếu. **Chưa chứng minh được mục tiêu chính xác 75%.** Xem
[quy trình](docs/compass-exact-protocol.md) và [kết quả](docs/compass-exact-findings.md).

**Cập nhật nguồn vàng:** repo có dữ liệu cho nhãn XAUUSD qua GC=F, nguồn
futures đang được scanner dùng. Đã tải lại 2.512 nến D1 bằng provider repo
và kiểm thử riêng, ghi rõ proxy; xem
[xác minh nguồn và kết quả](docs/compass-gold-repo-findings.md).
Chạy `.venv/Scripts/python.exe -m filter_pattern.compass_gold_repo`, rồi
mở `reports/compass-gold-repo-d1/index.html`. Thiếu OHLC spot không đồng
nghĩa repo không có nguồn giá vàng.

### Market Compass trên GitHub Pages — cập nhật D1 mỗi lần chạy

Workflow `scanner-pages-v2.yml` lấy mới dữ liệu và tạo `public/compass/`
trước khi ghép báo cáo. Trang chính có liên kết Market Compass; báo cáo
D1/H4 có mục mở la bàn dưới RRG. Đây là mục thử nghiệm, không tác động
qualification/setup hoặc thay RRG. D1 được dùng kể cả khi mở từ trang H4.

```powershell
python -m pip install -e '.[vnstock]'
python -m filter_pattern.compass_publish --out public/compass
```

Không cần cache nghiên cứu trong `reports/` để chạy trên CI. Yahoo cung
cấp GC=F, BTC-USD, ETH-USD, DX-Y.NYB, ^GSPC, SPY; VCI cung cấp E1VFVN30
(đơn vị nghìn VND theo provider). Hiển thị nến D1 mới nhất nguồn trả về,
kể cả nến đang hình thành; ghi ngày cuối từng nguồn, đánh dấu cũ khi quá
5 ngày lịch. Nến mang ngày UTC hiện tại hoặc ngày phiên tiếp theo được
đánh dấu tạm thời, vẽ nét đứt và được tính vào vị trí la bàn. Giá/màu nến
này có thể đổi khi workflow chạy lại. Chỉ outcome kết thúc trước ngày
UTC cập nhật được chấm hiệu suất; chưa dùng nến tạm thời làm kết quả đã
đóng. Đây là cập nhật mỗi lần workflow chạy, không phải stream giá. Lỗi nguồn được
hiển thị thiếu dữ liệu và không tự dùng lại snapshot cũ. Phân tích hiệu
suất chỉ chấm outcome đã hoàn tất. Cache cookie/timezone của Yahoo ở
`.cache/compass-yahoo`, không đi vào artifact công khai.

Kiểm tra tích hợp: `python -m pytest tests/test_compass_publish.py
tests/test_workflow_config.py tests/test_compass_rotation_stable.py -q`.
Thay đổi workflow có hiệu lực khi code được đưa lên nhánh chạy Pages;
chạy preview tại máy không tự triển khai website.

### Review hiện tại: hiệu suất và biểu đồ cả bảy mã

```powershell
.venv/Scripts/python.exe -X utf8 -m filter_pattern.compass_review
```

Mở `reports/compass-review-d1/index.html`: bảng/biểu đồ hiệu suất 5/10/20
nến, la bàn bốn ô và bảy biểu đồ giá tô màu cùng lúc. Có chọn từng mã,
cửa sổ 60/180/360 nến, so sánh bản ổn định/bản cũ và phát lại theo ngày.
Hiệu suất phát lại chỉ dùng các outcome đã kết thúc trước hoặc trong
ngày đang xem. XAUUSD ghi rõ GC=F futures đại diện từ nguồn scanner.
Rổ gồm sáu mã và nguồn vàng đại diện đạt 51,8% sau 10 nến ở bản ổn định;
chưa đạt mục tiêu 70%. Không thay RRG/scanner hoặc quy tắc dự báo.

### Chu kỳ D1 có làm mượt và vùng đệm

```powershell
.venv/Scripts/python.exe -m filter_pattern.compass_rotation_stable
```

Mở `reports/compass-rotation-stable-d1/index.html` để đổi giữa bản ổn định
và bản cũ. BTC 180 nến: đổi màu 35 → 18, nhưng nhận hướng chậm hơn;
chẩn đoán hướng nền sau 10 nến toàn rổ 52,5% → 50,7%. **Giảm nhiễu, chưa
cải thiện dự báo hoặc đạt 75%.** RRG giữ nguyên. Xem
[quy tắc](docs/compass-rotation-stable-protocol.md) và
[kết quả](docs/compass-rotation-stable-findings.md).

### Kiểm tra mục tiêu 70% cho la bàn D1

```powershell
.venv/Scripts/python.exe -X utf8 -m filter_pattern.compass_confidence70
```

Mở `reports/compass-confidence70-d1/index.html`. Ba bộ lọc xác nhận dùng
chung cho rổ trong ảnh, giữ nguyên bốn trạng thái và RRG. Chưa chứng minh
70%; bộ lọc cùng chiều đạt 51,83% với độ phủ 57,96%. Xem
[quy tắc](docs/compass-confidence70-protocol.md) và
[kết quả, giới hạn mẫu](docs/compass-confidence70-findings.md).

### Kiểm tra xu hướng chậm và nhịp hồi

```powershell
.venv/Scripts/python.exe -X utf8 -m filter_pattern.compass_reversion
```

Mở `reports/compass-reversion-d1/index.html`. Ba giả thuyết chung, không
phụ thuộc setup và không thay RRG: hồi về EMA20, điều chỉnh, hồi phục.
Kết quả 10 nến lần lượt 46,54% / 47,93% / 40,85%, chưa chứng minh 70%.
Xem [quy tắc](docs/compass-reversion-protocol.md) và
[kết quả](docs/compass-reversion-findings.md).

### La bàn nhận diện sóng giá D1

Bản **bốn trạng thái theo nguyên lý RRG**, dùng cùng tọa độ sóng giá:

```powershell
.venv/Scripts/python.exe -m filter_pattern.compass_rotation
```

Mở `reports/compass-rotation-d1/index.html`: Leading / Weakening / Lagging /
Improving đồng bộ trên thẻ, la bàn và giá; không dùng nhãn Long/Short. Đây
là chu kỳ giá tuyệt đối, không phải JdK RRG so với benchmark. Xem
[quy tắc](docs/compass-rotation-protocol.md) và [kết quả](docs/compass-rotation-findings.md).

### Bản hướng sóng Long/Short

Thử nghiệm nhận diện **sóng giá Long/Short** riêng, EMA20 + vùng đệm ATR:

```powershell
.venv/Scripts/python.exe -m filter_pattern.compass_wave
```

Mở `reports/compass-wave-d1/index.html` (mặc định BTC). Màu sóng theo dữ
liệu tại thời điểm đó, không tô lại về đỉnh/đáy. **Chưa đạt dự báo 75%**:
accuracy sau 10 nến toàn rổ 53,03%; độ bám sóng quá khứ không là accuracy
tương lai. Xem [quy tắc](docs/compass-wave-protocol.md) và
[kết quả](docs/compass-wave-findings.md).

### La bàn analog cập nhật theo tháng

Giữ K=25 và đặc trưng cũ, cập nhật thư viện bốn năm mỗi tháng, chỉ dùng
nhãn đã hoàn tất; thêm hiệu chỉnh điểm tin cậy trên dự báo quá khứ.

```powershell
.venv/Scripts/python.exe -m filter_pattern.compass_adaptive
```

Mở `reports/compass-adaptive-d1/index.html`. **Chưa cải thiện đủ để thay bản
cũ**: ngưỡng .75 có tỷ lệ đúng có trọng số 57,23%, độ phủ 1,86%; bản đã hiệu
chỉnh không có tín hiệu .75. Giữ nguyên RRG/scanner. Xem
[protocol](docs/compass-adaptive-protocol.md) và [kết quả](docs/compass-adaptive-findings.md).

### La bàn D1 bằng các trạng thái tương tự trong quá khứ

Một thư viện và K/ngưỡng chung cho cả rổ; thử đúng 25/50/100 analog với thư
viện lấy cách 10 nến, chọn và xác nhận trước năm test. Chạy offline:

```powershell
.venv/Scripts/python.exe -m filter_pattern.compass_analog
```

Mở `reports/compass-analog-d1/index.html`. **Chưa đạt tiêu chí 75%**: ứng viên
25 analog có tỷ lệ điểm 70,38%, độ phủ 3,16%, toàn Long; la bàn chính không
qua gate. XAUUSD vẫn thiếu OHLC spot. Xem
[protocol](docs/compass-analog-protocol.md) và [kết quả](docs/compass-analog-findings.md).

### La bàn chung D1 cho đúng bảy mã trong ảnh

Một mô hình/ngưỡng cho cả rổ, thử xu hướng D1 và tuần đã đóng. Model được
chọn và ngưỡng được sàng lọc trên validation trước năm test; không cấu hình
riêng từng market. Chạy offline với cache đã lưu:

```powershell
.venv/Scripts/python.exe -m filter_pattern.compass_shared
```

Mở `reports/compass-shared-d1/index.html`. **Chưa đạt mục tiêu 75%**; cả ba
năm không có ngưỡng qua gate, XAUUSD vẫn thiếu OHLC spot. Giao diện ưu tiên
tổng quan cả rổ, chi tiết kiểm tra được thu gọn. Xem
[protocol](docs/compass-shared-protocol.md) và [kết quả](docs/compass-shared-findings.md).

### La bàn kết hợp trạng thái giá và RRG

Thử quy tắc giá/RRG và hai mô hình cố định với/không có đặc trưng RRG. Lệnh
chạy offline, giữ nguyên dữ liệu và mô hình của các vòng trước:

```powershell
.venv/Scripts/python.exe -m filter_pattern.compass_hybrid
```

Mở `reports/compass-hybrid-d1/index.html`. Cần cache OHLC và raw RRG từ các
vòng trước. Mẫu ML bắt đầu 2025, riêng E1VFVN30 từ 2026 do thiếu lịch sử RRG
để học các fold trước đó. **Chưa chứng minh được mục tiêu 75%.** Xem
[protocol](docs/compass-hybrid-protocol.md) và [kết quả](docs/compass-hybrid-findings.md).

### Backtest RRG hiện tại so với Compass

Dùng tọa độ thật từ StockCharts/Fialda, giữ benchmark và hàm xác nhận Long
hiện tại; so sánh hướng trục X/Y riêng với Compass trên cùng ngày. Chỉ chạy
offline với raw nguồn và kết quả Compass đã lưu:

```powershell
.venv/Scripts/python.exe -m filter_pattern.rrg_comparison
```

Mở `reports/rrg-comparison-d1/index.html`. Xem
[quy trình](docs/rrg-comparison-protocol.md) và
[kết quả đối chiếu](docs/rrg-comparison-findings.md). RRG không thắng đồng đều
trên các mã; cả hai hướng tiếp cận chưa chứng minh mục tiêu chính xác 75%.

### La bàn D1 với bối cảnh liên thị trường (vòng 3)

So sánh mô hình chỉ dùng giá, mô hình thêm bối cảnh ETF ngành/trái phiếu/
VIX/USD và quy tắc xác nhận cố định. Học riêng mỗi market theo từng năm,
không dùng setup, không thay RRG hoặc scanner.

```powershell
.venv/Scripts/python.exe -m filter_pattern.cli compass-context --cache reports/compass-d1/candles.json --out reports/compass-context-d1 --before 2026-09-17
```

Để chạy lại offline, thêm
`--context-cache reports/compass-context-d1/context-sources.json`.
Báo cáo nằm ở `reports/compass-context-d1/index.html`.
Xem [giả thuyết cố định](docs/compass-context-protocol.md) và
[kết quả vòng 3](docs/compass-context-findings.md).
Dữ liệu mục tiêu từng được xem ở các vòng trước; đây vẫn là nghiên cứu hồi
cứu. Snapshot mới nhất là sản phẩm nghiên cứu, chưa phải tín hiệu forward
được ghi nhận đúng thời điểm giao dịch.
