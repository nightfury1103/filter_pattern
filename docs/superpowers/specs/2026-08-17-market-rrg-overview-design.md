# Market RRG Overview Revision Design

## Goal

Make the multi-market RRG overview readable at a glance and show the current status and movement direction of every supported market.

The overview will use a small, fixed set of daily representative symbols instead of summarizing every scanned symbol. RRG remains non-blocking reference context and does not change pattern qualification.

## Scope

This revision changes the RRG overview data presentation and its generated HTML. It does not change pattern detection, scoring, market filters, provider selection, or the per-candidate RRG reference panel.

The existing market-filter drill-down remains available: the all-markets view uses fixed representatives, while selecting one market may show the detailed daily RRG symbols already available for that market.

## Market Representatives

The all-markets overview uses these D1 representatives:

| Market | Internal fetch symbol | Overview label |
| --- | --- | --- |
| US stock | `SPY` | `SPY` |
| Vietnam stock | `E1VFVN30` | `E1VFVN30` |
| Crypto | `BTCUSDT` | `BTCUSD` |
| Crypto | `ETHUSDT` | `ETHUSD` |
| Forex | `DXY` | `DXY` |
| Index | `US500` | `US500` |
| Commodity | `XAUUSD` | `XAUUSD` |
| Commodity ETF | `DBC` | `DBC` |

Provider-compatible symbols remain internal. Display aliases affect only overview labels and do not change data retrieval or candidate symbol identifiers.

`E1VFVN30` is the Vietnam-market proxy because Fialda returns a usable RRG series for it against VNINDEX. VNINDEX and VN30 themselves return no RRG series from the available providers. The overview must display `E1VFVN30` transparently rather than labeling the proxy as VNINDEX or VN30.

The Forex report symbol remains `DXY`, but its StockCharts request symbol is `$USD`; `$DXY` returns no StockCharts RRG series. Commodity ETF representative `DBC` must be requested whenever Commodity ETF is included in the scan configuration, even when the broker filter removes Commodity ETF candidates from the pattern universe.

## Overview Layout

The overview contains two primary elements:

1. A compact market-status card grid.
2. One combined RRG chart containing only the fixed representatives.

The current four symbol-by-quadrant lists and market-count bars are removed from the overview because they repeat candidate-level information and create the current visual overload.

The summary counts describe representative data, not the full candidate population. They include the number of represented markets, the number of available representative trails, and the supportive-to-risk balance. Supportive and risk totals count individual available representatives: Leading and Improving are supportive; Weakening and Lagging are risk.

## Market Status Cards

Each supported market retains one card in the grid. A card shows:

- Market name.
- Representative symbol or symbols.
- Current RRG quadrant.
- Latest RS-Ratio and RS-Momentum when available.
- Latest observed movement direction.

For a single-representative market, the market status is that representative's quadrant: Leading, Improving, Weakening, or Lagging.

Crypto keeps BTC and ETH visible separately. If both occupy the same quadrant, the crypto card uses that quadrant as its combined status. If both are available in different quadrants, the combined status is Mixed. If only one is available, the combined status is Partial. Both individual status labels remain visible, including Unavailable for a missing representative. No average or synthetic crypto quadrant is calculated.

If a representative cannot be fetched or does not contain usable RRG points, its market card remains visible with an Unavailable status. A missing representative is excluded from chart and balance counts but does not make the market disappear.

## Chart Direction Treatment

The combined chart uses the approved emphasized-final-arrow treatment:

- Historical trail segments are visually faded.
- The final segment between the last two usable points is thicker and fully opaque.
- A larger arrowhead ends at the current point.
- The current point and symbol label remain visible above the trail.

The arrow communicates observed travel from the previous point to the current point. It is not a forecast and must not be labeled as a predicted next quadrant or future market direction.

When a trail contains only one usable point, the chart shows the endpoint without an arrow. When it contains no usable points, the corresponding market remains Unavailable and no trail is rendered.

## Data Flow

1. `attach_rrg_references` collects supported markets from both the requested scan configuration and report rows, so a configured market does not disappear when it has no candidate rows.
2. The existing market-specific fetchers request D1 data for each configured representative.
3. Representative rows retain their internal symbol and receive an overview display label.
4. The report layer normalizes representative rows into status-card and chart items.
5. The all-markets overview renders the fixed representative cards and trails.
6. The existing market filter continues to switch to the appropriate detailed market chart where detailed items are available.

Representative retrieval remains best-effort. Fetch errors are recorded in the existing RRG reference error list and do not fail the pattern scan or report generation.

### Combined Report Aggregation

GitHub Pages builds D1 and H4 reports by combining multiple market shards. The combine boundary must preserve `rrg_reference.market_representatives` from every shard instead of rebuilding the overview from candidate rows.

Combined representatives are deduplicated by market and internal symbol. If duplicate shards disagree, a row with usable RRG data wins over an Unavailable row. Unavailable rows are otherwise retained so every fetched market slot remains visible. Combined RRG errors are deduplicated, and candidate-level RRG references continue to flow through their existing rows.

## Status Semantics

Quadrant labels come directly from the current RRG point:

- Leading: RS-Ratio at or above 100 and RS-Momentum at or above 100.
- Improving: RS-Ratio below 100 and RS-Momentum at or above 100.
- Weakening: RS-Ratio at or above 100 and RS-Momentum below 100.
- Lagging: RS-Ratio below 100 and RS-Momentum below 100.

Movement direction comes from the delta between the final two usable points. It supplements the quadrant and never replaces it.

## Testing

Automated tests will verify:

- The fixed representative map for every supported market.
- `E1VFVN30` retrieval through Fialda with VNINDEX as its benchmark.
- DXY retrieval through the StockCharts `$USD` provider symbol while retaining the `DXY` report label.
- DBC representative retrieval when Commodity ETF is configured but absent from scanned candidate rows.
- D1 fetching for representatives even when the report timeframe is H4.
- `BTCUSDT` and `ETHUSDT` retrieval with `BTCUSD` and `ETHUSD` overview labels.
- Single-representative quadrant status.
- Crypto same-quadrant, Mixed, and Partial aggregation.
- Unavailable cards for missing or unusable representative data.
- Representative-only content and counts in the all-markets overview.
- Removal of the four candidate quadrant lists and market-count bars.
- A faded historical trail, emphasized final segment, and larger final arrowhead.
- Endpoint-only rendering when only one point is available.
- Preservation of selected-market detailed chart behavior.
- Continued non-blocking behavior when representative retrieval fails.
- Preservation and deduplication of representative rows in combined shard reports.
- Preference for an available representative when another shard reports the same representative as unavailable.

## Acceptance Criteria

- A reader can identify every market's RRG status without inspecting a long symbol list.
- The all-markets chart displays no symbols beyond the configured representatives.
- The final arrow makes each multi-point trail's observed direction clear.
- BTC and ETH both remain visible in the crypto card and chart.
- A missing representative produces an Unavailable card instead of removing the market.
- Market drill-down and candidate qualification behavior remain unchanged.
- The GitHub Pages combined report uses the fixed representatives instead of highest-ranked candidate fallbacks.
- The Vietnam card and trail use `E1VFVN30`, not an unavailable VNINDEX or VN30 self-reference.
- Configured DXY and DBC representatives remain present when valid provider data is returned.
