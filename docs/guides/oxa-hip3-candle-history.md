# Archived HIP-3 traded candles

Use explicit market family and case-sensitive builder identity:

```bash
uv run python -m hypervector --data-root /path/to/research-data oxa-candle-fetch \
  --market-family hip3 --symbol xyz:SNDK \
  --start 2026-07-01T14:00:00Z --end 2026-07-01T15:00:00Z \
  --interval 15m --limit 10 --max-pages 2
```

The command requires the existing `OXA_API_KEY` environment configuration.
It fetches public market history and stores an immutable evidence bundle.
It does not start a trading process. Core assets retain the default family
`core`; `xyz:SNDK` requires `--market-family hip3`.

The HIP-3 route is `/v1/hyperliquid/hip3/candles/{symbol}`. The vendor describes
these as candles aggregated from HIP-3 trades, with symbol-specific coverage.
See the [vendor contract](https://docs.0xarchive.io/schemas/operations/get-hip3-candles).

Bundles are saved under
`cache/vendor/0xarchive/hyperliquid/hip3/<symbol>/<window>_candles_<interval>`.
The manifest records the family, exact symbol, source endpoint, page identifiers,
request bounds and raw/Parquet hashes. The existing core bundle path is preserved.

`read_complete_candle_evidence(bundle, request, require_complete_cadence=True)`
verifies those identities, reproduces Parquet from the saved raw pages, and
requires the exact half-open timestamp grid. A completed page sequence alone
does not prove complete cadence. The vendor's inclusive end candle is excluded
from the normalized half-open window.

Optional `--install-research-cache` supports `--interval 1m` only, because its
gap repair operates at minute cadence. Other intervals fail before acquisition
when that flag is supplied. Omit the flag to acquire higher-interval bundles.
One-minute repair retains its explicit `hl_gap_fill` source labels.

September 12 acceptance verified one hour of SNDK history from July 1, including
four normalized 15-minute bars and exact raw reproduction. It does not establish
whole-period coverage, agreement with native candleSnapshot bars, or a trading
advantage. Missing vendor request identifiers, quote volume or trade count remain
explicit validation failures; this importer does not synthesize those fields.
