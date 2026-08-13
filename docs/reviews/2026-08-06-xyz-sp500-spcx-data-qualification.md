# XYZ SP500 and SPCX HIP-3 qualification

## Problem restatement

Prepare `xyz:SP500` and `xyz:SPCX` for eventual inclusion in Hypervector's
shared portfolio roster without changing the running v11 cohort or the staged
v14 crypto profile. The immediate output is public, read-only venue evidence.
Live execution is not authorized by this artifact.

Success for this phase requires exact venue identity, current market metadata,
two-sided L2 books, candle availability, collateral identity, leverage and fee
inputs, explicit unresolved facts, and a tested acquisition path. Strategy
transfer and order routing are separate later experiments.

## Known facts and provenance

The immutable evidence is
`data/logs/research/xyz_sp500_spcx_qualification_20260806T1451Z.json`, SHA-256
`c3676eaf2035ba41f6cdd1be6cb5c34207d127e5ee3a90da30f50ca7671529d3`,
4,937 bytes. It was observed at `2026-08-06T14:48:40.545157+00:00` through
the official Hyperliquid SDK public `Info` surface. It loaded no credentials,
constructed no exchange client, and has `execution_authority=none`.

Hyperliquid's official HIP-3 documentation states that deployers own market
definition and oracle operation, while the API and order-book substrate remain
part of HyperCore. The official fee documentation defines growth-mode and
deployer-fee scaling. These protocol statements do not validate either market's
economic edge.

| Fact | `xyz:SP500` | `xyz:SPCX` |
|---|---:|---:|
| Exact venue symbol | verified | verified |
| Size decimals | 3 | 2 |
| Venue maximum leverage | 50x | 20x |
| Margin table ID | 50 | 20 |
| Returned margin tiers | 0 USD and above: 50x | unavailable in dex metadata |
| Growth mode | enabled | enabled |
| Deployer fee scale | 1.0 | 1.0 |
| Positive-fee multiplier versus native | 0.2x | 0.2x |
| Funding multiplier | 0.5 | 0.5 |
| Streaming OI cap | $1.25B | $750M |
| Collateral | USDC, token index 0 | USDC, token index 0 |
| Snapshot day notional volume | $457.3M | $384.0M |
| Snapshot spread | 0.389 bps | 0.896 bps |

The fee multiplier is a protocol-formula input, not the account's final fee.
Actual maker/taker fees still depend on the account tier, referral state,
aligned collateral treatment, growth mode, and the deployer scale at execution
time. It must be recomputed during preflight and reconciled against fills.

## Data coverage

The official candle response returned continuous windows for all requested
intervals, with no missing interval inside each returned prefix:

| Symbol | 1m rows | 5m rows | 15m rows | Approximate earliest 15m bar |
|---|---:|---:|---:|---|
| `xyz:SP500` | 5,034 | 5,007 | 5,003 | 2026-06-15 12:15 UTC |
| `xyz:SPCX` | 5,215 | 5,043 | 5,015 | 2026-06-15 09:15 UTC |

All windows reached the venue's approximate public 5,000-row response ceiling.
The absence of gaps inside these windows does not establish full history or
inception coverage.

An authenticated, bounded 0xArchive HIP-3 probe subsequently established a
separate historical L2 source. The exact route family is
`/v1/hyperliquid/hip3/orderbook/{symbol}/history`; the core-perp route is not
interchangeable. The first returned snapshots were:

| Symbol | First returned historical L2 snapshot |
|---|---:|
| `xyz:SP500` | 2026-03-18 13:58:08.466 UTC |
| `xyz:SPCX` | 2026-05-17 22:35:27.834 UTC |

A completed `2026-08-06 14:00–15:00 UTC` depth-20 sample returned 7,774
snapshots and eight pages for each symbol. SP500 occupied approximately 1.7 MB
and SPCX 3.4 MB in the dual raw-plus-normalized gzip bundle. The extrapolated
full pull is roughly 41 million snapshots and 12–15 GB, subject to activity and
compression variation. The estimate is planning evidence, not a completed
coverage claim.

## Analysis and engineering implications

The existing native-perp SDK initialization cannot resolve HIP-3 names. A
read-only probe using a client without `perp_dexs=["xyz"]` failed with a
`KeyError` for `xyz:SP500`; the exact same request succeeded when the namespace
was explicitly loaded. Hypervector's historical symbol normalizer also changed
`xyz:SP500` into invalid `XYZ:SP500`. The normalizer now preserves exact
lower-case `dex:ASSET` identity and has regression coverage.

The current live adapter is not ready for HIP-3. It assumes native metadata,
native mids, native clearinghouse state, and native open-order queries. HIP-3
requires the XYZ dex on each of those reads and requires the authenticated SDK
exchange to be initialized with the same namespace. Adding symbols only to a
TOML roster would therefore be a technical defect, not a valid trial.

SP500 and SPCX must not be pooled with crypto merely to improve a combined
backtest. Both are deployer-oracle markets with different price formation,
funding, event risk, and off-hours behavior. SPCX also has corporate-event and
listing-history discontinuity risk. These are test dimensions, not automatic
performance gates.

## Uncertainties, risks, and failure modes

- SPCX margin table ID 20 was reported, but its tier definition was absent from
  the returned XYZ `marginTables`. A live preflight cannot infer the tiers from
  the headline 20x value.
- Public candle coverage is capped and cannot establish inception behavior,
  rare oracle events, or long-horizon walk-forward stability.
- Current books and volume can change materially; one snapshot does not prove
  fill quality at the intended decision times.
- Growth mode, fee scale, OI cap, leverage, or market status can change. Startup
  must verify them rather than trusting this artifact.
- A deployer can halt or settle a HIP-3 asset. Restart and live reconciliation
  need an explicit halted-market state.
- The existing breakout and regime features may have different semantics
  during equity cash sessions, overnight trading, weekends, IPO events, and
  oracle repricing.
- The TUI is largely symbol-driven, but the overview chart currently renders
  only the first four roster symbols. Six-symbol visibility needs pagination or
  a selected-symbol layout before these candidates join backend telemetry.

Any missing namespace, collateral, margin, fee, market-status, position, order,
or fill identity falsifies technical readiness and must fail closed. Subsequent
negative strategy outcomes falsify economic hypotheses but remain reported
trial results under `SRS_HV1_NO_GATES`.

## Validation plan

1. Add a HIP-3-aware read adapter that explicitly binds dex `xyz` for metadata,
   mids, L2, clearinghouse state, and open orders. Mock every call and smoke-test
   public mainnet reads.
2. Resolve SPCX margin table 20 from an authoritative API or prove how the SDK
   derives it. Do not infer tiers from the table ID.
3. Extend the authenticated SDK builder with an explicit deduplicated perp-dex
   list and test that native-only profiles remain byte-for-byte equivalent in
   behavior.
4. Complete and checksum-audit the resumable 0xArchive HIP-3 L2 backfill. Add a
   durable native forward recorder for candles, L2, funding, oracle/mark skew,
   halts, and session-state behavior. Retain raw namespaced symbols.
5. Add both assets to an observe-only backend generation. The TUI must display
   their candles, regimes, books, funding, readiness, and missing-data states
   without local simulation.
6. Evaluate both long and short signals separately on chronological evidence,
   with HIP-3 fee formulas and observed spreads. Report all trials without an
   implicit performance abort.
7. Only after technical parity is proven, prepare a bounded live candidate with
   one-position-per-coin routing, shared portfolio accounting, venue-native
   stops, restart adoption, and new explicit live authorization.

## Recommendation and trade-offs

| Option | Benefit | Cost/risk | Recommendation |
|---|---|---|---|
| Do nothing | No integration risk | No equity/pre-IPO evidence | Keep as rollback |
| Observe-only roster | Captures real venue behavior without order risk | Requires HIP-3 read and TUI work | Proceed now |
| Copy v14 breakout into HIP-3 live | Fastest execution experiment | Current adapter cannot reconcile the dex; strategy transfer is untested | Do not do yet |
| Build full HIP-3 execution first | Maximum eventual flexibility | Larger change before data semantics are understood | Stage after observation plumbing |

Recommendation confidence: high for observe-only preparation because official
metadata, active books, and tested public acquisition agree. Confidence is low
for strategy profitability because no exact SP500/SPCX forward lifecycles have
been observed. This assessment would improve with resolved SPCX margin metadata,
durable full-session data, and reproducible long/short forward outcomes; it
would be falsified by namespace or reconciliation mismatches in the next
adapter tests.

## Roster expansion: SNDK, GOLD, and oil

The requested SNDK, GOLD, and WTI-oil research was added without changing live
execution authority. The immutable combined active-market qualification is
`data/logs/research/xyz_sndk_gold_brentoil_qualification_20260806T1521Z.json`,
SHA-256
`1eccd9c1ce834dd919ef45087201017ad0858a1b1d21fc0812e274780a1da194`,
6,640 bytes. It was observed at `2026-08-06T15:17:51.445460+00:00` and declares
`execution_authority=none`.

A second immutable snapshot verifies the complete five-market active research
roster together: `xyz:SP500`, `xyz:SPCX`, `xyz:SNDK`, `xyz:GOLD`, and
`xyz:BRENTOIL`. It is stored at
`data/logs/research/xyz_active_roster_qualification_20260806T1524Z.json`,
SHA-256
`b2a1c8a96be69a982960c334019253326c801a263abe689ddfe11657f1ca70f5`,
10,182 bytes, observed at `2026-08-06T15:21:57.263154+00:00`. The report is
observation-only and grants no strategy or execution authority.

| Requested idea | Exact venue evidence | Current disposition |
|---|---|---|
| SNDK | `xyz:SNDK` | Active, qualified for observation only |
| GOLD | `xyz:GOLD` | Active, qualified for observation only; fee multiplier unresolved |
| WTIOIL | No active exact symbol | Preserve as unresolved requested alias |
| Historical WTI | `cash:WTI` | Delisted; historical research only |
| Active oil alternative | `xyz:BRENTOIL` | Active, qualified separately; not treated as WTI |

The public Hyperliquid `perpDexs` and per-dex `metaAndAssetCtxs` responses
showed `xyz:SNDK`, `xyz:GOLD`, and `xyz:BRENTOIL` without a delisted flag. They
showed `cash:WTI` with `isDelisted=true`. Other oil identities found in current
metadata (`flx:OIL`, `km:USOIL`, and `mkts:USOIL`) were also delisted. No exact
`WTIOIL` identity appeared. Hyperliquid documents namespaced HIP-3 asset IDs and
per-dex metadata on its public Info API; a human ticker resemblance is not a
valid symbol mapping.

| Fact at qualification time | `xyz:SNDK` | `xyz:GOLD` | `xyz:BRENTOIL` |
|---|---:|---:|---:|
| Size decimals | 3 | 4 | 2 |
| Venue maximum leverage | 10x | 25x | 20x |
| Margin table ID | 10 | 25 | 20 |
| Returned margin tiers | unavailable | unavailable | unavailable |
| Growth mode | enabled | unavailable | enabled |
| Computable positive-fee multiplier | 0.2x | unavailable | 0.2x |
| Funding multiplier | 0.5 | 0.5 | 0.5 |
| Streaming OI cap | $500M | $500M | $750M |
| Snapshot day notional volume | $908.8M | $111.2M | $111.1M |
| Snapshot spread | 0.762 bps | 0.235 bps | 0.123 bps |

The qualifier was changed to retain an omitted `growthMode` as unresolved
rather than guessing enabled or disabled. GOLD can therefore be observed, but
its final fee multiplier remains unavailable until authoritative metadata or
an account-level fee preflight resolves the missing input. This behavior has a
regression test. Hyperliquid's fee formula explicitly depends on growth mode,
so substituting a default would create false precision.

0xArchive's namespaced HIP-3 history route returned the following first
depth-20 snapshots from a February-to-August bounded probe:

| Symbol | First returned L2 snapshot |
|---|---:|
| `xyz:SNDK` | 2026-02-26 17:51:11.877 UTC |
| `xyz:GOLD` | 2026-02-26 17:51:11.332 UTC |
| `xyz:BRENTOIL` | 2026-03-04 22:34:52.890 UTC |
| `cash:WTI` | 2026-03-12 12:15:00.584 UTC |

Recent three-minute probes returned 394 valid two-sided snapshots for each
active XYZ market. `cash:WTI` instead returned rows with an empty bid side,
which the typed downloader rejected. A bounded transition probe found its last
two-sided snapshot at `2026-06-30T20:08:24.630Z` and the first empty-sided row
at `2026-06-30T20:08:30.039Z`. This agrees with the official delisted flag and
means post-transition WTI rows must not be interpreted as an active book.

Confidence is high for the exact identity and active-versus-delisted findings
because the official venue metadata and 0xArchive book structure agree. It is
low for economic edge because no chronological strategy trials exist for these
markets. The identity assessment would be updated if an official active market
named `WTIOIL` appears; the technical readiness assessment would be falsified
by missing margin tiers, unresolved GOLD fee inputs, incomplete backfill
checksums, namespace reconciliation failures, or empty/crossed live books.
