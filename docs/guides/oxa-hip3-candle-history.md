# Archived HIP-3 traded candles

Fetch HIP-3 candles with an explicit market family and the case-sensitive
builder identity:

```bash
.venv/bin/python -m hypervector --data-root /path/to/research-data archive candle-fetch \
  --market-family hip3 --symbol xyz:SNDK \
  --start 2026-07-01T14:00:00Z --end 2026-07-01T15:00:00Z \
  --timeframe 15m --limit 10 --max-pages 2
```

- **API key.** The command loads only `OXA_API_KEY` from the environment or
  `.env`.
- **Validation first.** It validates every argument and checks for an output
  collision before any API call.
- **Output.** It fetches public market history, stores an immutable evidence
  bundle and starts no trading process.
- **Market family.** Core assets keep the default family `core`. `xyz:SNDK`
  needs `--market-family hip3`.

The HIP-3 route is `/v1/hyperliquid/hip3/candles/{symbol}`. The vendor
describes these as candles aggregated from HIP-3 trades, with symbol-specific
coverage. See the
[vendor contract](https://docs.0xarchive.io/schemas/operations/get-hip3-candles).

## Bundles

Bundles are saved under
`<data-root>/cache/vendor/0xarchive/hyperliquid/hip3/<symbol>/<window>_candles_<timeframe>`.
Core bundles keep their own path under `hyperliquid/<symbol>/`.

The manifest records:

- the family and the exact symbol;
- the source endpoint and page identifiers;
- the request bounds;
- raw and Parquet hashes.

`read_complete_candle_evidence(bundle, request, require_complete_cadence=True)`
does three things:

1. checks those identities;
2. rebuilds the Parquet from the saved raw pages;
3. requires the exact half-open timestamp grid.

A completed page sequence alone does not prove complete cadence. The vendor's
inclusive end candle is dropped from the normalized half-open window.

## Research cache

`--install-research-cache` also installs the candles as an exact research cache.

- It supports `--timeframe 1m` only, because its gap repair works at minute
  cadence. Any other timeframe with the flag fails before the fetch.
- Omit the flag to fetch higher-timeframe bundles.
- One-minute repair keeps its explicit `hl_gap_fill` source labels.

Missing vendor request identifiers, quote volume or trade count are explicit
validation failures. The importer never synthesizes those fields.

