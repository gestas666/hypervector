# Hypervelocity TUI visual and backend-parity acceptance

## Scope and success criteria

The legacy Hypervelocity TUI is a read-only projection of the Python shadow
backend. Its four screens must show the same run, portfolio, regime, execution,
cost, and L2 facts found in the active backend ledger. The shared-cohort
operator cockpit has nine screens. It projects backend truth and may publish
explicitly confirmed, run-bound local requests; only an already-armed Python
backend may validate or execute them. Neither interface may invent orders,
trades, labels, probabilities, distributions, or fallback market data.

Automated acceptance:

```bash
uv run pytest tests/ -q -m "not network"
cargo fmt --all -- --check
cargo clippy -p hypervector-tui --all-targets -- -D warnings
cargo test -p hypervector-tui
```

Human acceptance uses a terminal at least 120 columns wide. Any mismatch with
the ledger is a failure even when the display looks plausible.

The shared nine-asset core plus HIP-3 cohort has an additional compact
acceptance floor of 120x36 and a hard usability floor of 100x28. Below the hard
floor, the TUI must show an explicit resize diagnostic rather than clipped
operational data.

## Launch

Use the supervised command so one lifecycle owns the backend and foreground
TUI:

```bash
uv run python -m hypervector \
  --data-root data \
  hypervelocity-tui \
  --config configs/hypervelocity_faithful.toml
```

Normal quit preserves the durable shadow portfolio and journal. Do not use a
reset merely to restart the display. A deliberately fresh observation window
uses the recoverable command shown on screen 4:

```bash
uv run python -m hypervector \
  --data-root data \
  hypervelocity-shadow-reset --yes
```

Start the disarmed public-data cohort observer and operator cockpit:

```bash
uv run python scripts/multi_asset_bidirectional_canary_tui.py
```

The default command uses the production signal collectors, opens on screen 2,
and grants no order authority. Confirm 24 unique provider/asset evaluations,
nine completed-candle histories, nine exact L2 books, `SETUPS 24/24 COMPLETE`,
`EXECUTION DISARMED`, and explicit setup blockers. To attach to an already
running backend without starting another, use `--mode monitor`. A documented
armed form is not authorization and is outside this visual acceptance
procedure.

Press `q` after the rows populate. Acceptance also requires the owned observer
to stop, leave no stale STOP sentinel, and publish exactly one immutable
`multi_asset_observer_audit_<run-id>.json` below
`data/logs/research/bidirectional_cohort/`. Its `technical.complete` field must
be true, all 24 provider/asset pairs must be observed, and actions must remain
zero. Readiness movement is setup-process evidence only; this acceptance does
not establish fills, execution quality, or profitability.

## Screen 1: Dashboard

Verify the following against the latest run in
`data/paper/decisions/decisions.jsonl`:

- Run ID, strategy ID, shadow mode, model mode, and model probability match.
- One BTC position maximum is shown; pending maker orders are not positions.
- Entry, mark, size, 40x leverage, unrealized PnL, paid entry fee, funding, and
  estimated exit fee match backend rows.
- Initial capital, equity, realized/unrealized/net PnL, closed trade count, and
  win/loss counts persist across normal quit and restart.
- Five bid and five ask levels are visible when the backend publishes them.
- The journal is selectable. Details include Eastern entry/exit times, entry
  and exit 1m/5m/15m states, entry/exit fees, funding, gross PnL, and net PnL.
- Flat readiness shows backend entry direction, canonical state, maker status,
  retry/cooldown state, funding, L2 age, and structure score.
- In cohort observer mode, empty account/position/fill panels are replaced by a
  four-coin market/L2 pulse, the leading setup and next blocker per coin, and a
  bounded 5m/15m/30m/60m causal path journal. Missing paths say `N/A`; resolved
  and non-overlapping counts remain separate; the panel explicitly says the
  values are annotations, not fills or PnL. All ten selectable readiness rows
  remain available on cohort Screen 2.

## Screen 2: Regime Detection

The exact backend vocabulary is
`TREND_UP`, `TREND_DOWN`, `BREAKOUT`, `RANGE`, `TRANSITION`, and `UNKNOWN`.

- `Canonical Primary` says `5m authoritative`.
- `Context Only` is immediately below it and shows 15m non-veto context.
- 1m is execution telemetry and breakout confirmation; no text may advertise
  a 1m directional fallback over 5m.
- A 5m breakout is direction-eligible only after matching 1m confirmation.
- `Structure Strength` is separate from `Model p`; it is an EMA-gap percentile
  diagnostic and is not an execution gate.
- The distribution uses observed backend history, includes `UNKNOWN`, and is
  not a current-state-shaped constant profile.
- The transition audit uses backend timestamps and reasons.
- Missing L2, funding, or playback features say `not available` or
  `not reported`; zero must not be presented as a measured neutral value.

## Screen 3: Read-only chart

- Hypervelocity shows backend OHLCV candles and execution overlays only when
  those values exist in backend telemetry.
- The shared cohort uses four direction-colored candlestick panes from the
  backend `market_candles` event. Each pane shows completed Hyperliquid 1-minute
  OHLCV only: price grid, wicks, bodies, Eastern time endpoints, and volume.
- The initial backend publication may contain at most 360 bars per coin. Faster
  reconciliation polls must not duplicate candle timestamps; later events
  contain only newly completed bars.
- Enter opens the selected strategy and coin. Its chart uses the provider's
  configured 1m, 5m, 15m, or 30m decision clock. Higher-timeframe candles are
  view-only aggregates of consecutive backend-completed 1m bars; incomplete or
  gapped buckets are excluded and labeled rather than inferred.
- Missing chart history displays an explicit awaiting-data state. A flat line
  or close-only reference trace must not substitute for missing OHLCV.

## Screen 4: Effective configuration

Rows are selectable and read-only. Verify these identity fields:

| Field | Expected faithful value |
|---|---|
| Position mode / max per symbol | `one_way` / `1` |
| Margin allocation / leverage | `70%` / `40x` |
| Target | `8%` margin return, strategy-target only |
| Order | post-only limit, event-driven public L2/trade evidence |
| Execution / primary / context timeframe | `1m` / `5m` / `15m` |
| Allowed states | `TREND_UP`, `TREND_DOWN`, `BREAKOUT` |
| Blocked states | `RANGE`, `TRANSITION`, `UNKNOWN` |
| Breakout direction required | `true` |
| Context hard gate / strength-score gate | `false` / `false` |
| Metalabel mode | `off` or `observe`, never a hidden filter |

The displayed reset command must quote and reuse the backend-reported active
data root.

## Shared-cohort visual acceptance

At 120x36 and 190x52, verify all of the following against
`data/live/bidirectional_cohort/decisions.jsonl`:

- Rounded two-line chrome shows backend connection, Eastern sync time, arm
  state, and active view without truncating the arm state.
- Capital, withdrawable balance, total notional, exact margin utilization, and
  backend-configured position capacity match the latest cohort snapshot and
  configuration identity. Zero or invalid equity says margin utilization is
  unavailable.
- Every configured asset is reachable through the shared selector and paged
  panels without truncating namespaced symbols. An open position shows side,
  state, mark, entry, unrealized PnL, liquidation distance, costs, and
  `PROTECTED #<oid>` or the
  high-contrast `STOP MISSING` condition. Fault and stop columns must not be
  transposed.
- Compact fill rows retain time, coin, direction, provider alias, price, fee,
  PnL, slippage, acknowledgement latency, measured markout, and exit reason.
  Wide mode additionally shows exact `tid/oid`, size, and full audit labels.
- Portfolio screen shows account/exposure truth in live mode and a paged
  nine-asset market pulse plus causal research paths in observer mode. Tall
  layouts also
  show a zero-baseline cumulative closed-PnL trace, chronological outcome tape,
  separate long/short W-L and net PnL, and measured venue-fill friction.
- Setups screen shows recent selected/withheld counts, backend position slots,
  exact withholding reasons, source evidence, arrival time, decision time,
  all 24 latest provider/asset evaluations, live indicator values,
  readiness fractions, and next blockers. Rows are selectable and Enter opens
  the exact evidence inspector. Empty sections explicitly report no recent
  actions rather than rendering blank panels. Readiness must say it is a
  diagnostic rather than win probability.
- Chart screen pages across all nine assets with real backend OHLC values,
  visible wicks/bodies, price/time axes, and volume. A legacy ledger must show
  `BACKEND OHLCV UNAVAILABLE` instead of deriving candles from mark history.
  Left/right visibly selects each coin and Enter opens its focused chart detail.
  The detail renders completed candles at the provider `DECISION TF`, shows
  recorded 1m/5m/15m state, readiness, indicators, blockers, and matching
  strategy-evidence provenance, and never borrows indicators from another
  provider. Incomplete higher-timeframe buckets are absent and explicitly
  labeled. A configured provider without a current evaluation says the evidence
  is unavailable.
- Depth screen shows every reported exact bid and ask up to the venue-native
  20-level cap, plus cumulative imbalance, book-limited sweep cost, spread,
  receive age, order counts, microprice, walls, concentration, OPI, and bid/ask
  ratio. Five-level legacy/runtime snapshots remain valid, but the display must
  not expand one ratio into a page-height solid slab. Missing or stale backend
  books must be explicit; no synthetic depth or extrapolated sweep liquidity is
  allowed.
- Trades screen shows open risk, liquidation/protection, costs, selectable
  exact fills, slippage, acknowledgement latency, markout, and exit attribution.
  At 120x36 it must retain portfolio and per-strategy W/L, win rate, net USD,
  net return on entry margin, profit factor, fees, and funding without overlap.
- Journal screen shows rolling audit health, coverage, cadence, causal outcomes,
  and the limits of what those observations establish. It must keep eligible
  fired-signal paths separate from readiness-only setup paths; selecting a row
  and pressing Enter must expose resolved, independent, censored, and missing
  counts for 5/15/30/60 minutes. Setup annotations must never substitute for
  signal, fill, cost, or PnL evidence.
- Control screen exposes manual strategy entry and reduce-only close through a
  two-step confirmation. These are one-off overrides and do not disable the
  automatic strategies. A manual close may suppress same-cycle re-entry only;
  the next poll must resume automatic decisions. Both controls remain disabled
  while disarmed. Every accepted request must reconcile to backend command
  lifecycle rows.
- Config screen compares effective values with a complete next-run draft for
  position capacity, polling, isolated leverage/margin/notional/stop/hold, and
  provider-symbol scopes. It stages a separate validated profile while disarmed
  and never hot-mutates or arms the running backend. Credential state is masked.
  For the v25 trial profile it must expose all 24 exact provider/asset scopes.
  Observe mode remains globally disarmed despite those declared scopes; the
  TUI must not confuse eligibility with an armed order client.
- Regime screen pages through the synchronized nine-asset matrix from the
  backend range-onset provider: 1m execution state, authoritative 5m primary,
  non-veto 15m context, canonical call, structure strength, and decision time.
  It retains a bounded backend label tape and shows venue L2 pressure without
  recomputing labels in Rust. EMA/SMA, Cipher A, HARSI, Choppiness, completed
  MTF bias, regression R-squared, and Self-Aware TQI diagnostics must remain
  `N/A` until the Python backend publishes causal completed-bar values. These
  values are observe-only and must not be labeled as win probabilities or
  execution weights. The truth panel must quantify forward evaluations and
  five-minute resolved/non-overlapping paths from the checkpoint, label
  incomplete path coverage, and never turn censored evidence into a resolved
  sample.
- Open and closed lifecycle panels expose the causal entry structure-alignment
  score. An open lifecycle with a backend-bound target must also show its exact
  venue OID, limit price, and backend-computed directional distance from the
  venue-synchronous mark; missing target evidence must render `TGT N/A` rather
  than inferring a price. Fixed threshold comparisons must be grouped by exact
  provider-symbol mapping, retain admitted and excluded after-cost outcomes,
  and remain explicitly report-only with no live execution authority.
- Timer-exit evidence must retain both the portfolio aggregate and exact
  provider-symbol partitions. Counts for supported, opposed, mixed, and
  unavailable exit context must reconcile to recorded timer exits; extension
  projections must retain censoring, missing data, original protective stops,
  and explicit report-only authority.
- Each lifecycle must report fixed `-0.5` opposition persistence at one, three,
  and five consecutive completed decisions. Missing decisions break a sequence,
  and the compact open-trade panel shows current/maximum persistence without
  converting it into an automatic close signal.
- Closed outcomes must be partitioned by exact provider-symbol and whether each
  persistence level occurred. These partitions use recorded after-cost
  lifecycle results, do not claim a hypothetical early-exit fill, and cannot
  authorize a policy change.
- Historical component attribution is a venue-matched prior, not live forward
  proof. The frozen 2026-08-03 report must remain execution-incapable and must
  not replace the screen's current-run forward/resolved/non-overlapping counts.
  RANGE and strength cues may be described as movement diagnostics; canonical
  direction must not be advertised as predictive from that report.

Generate deterministic human-readable buffers for visual inspection:

```bash
HYPERVECTOR_VISUAL_SNAPSHOT=1 \
  cargo test -p hypervector-tui \
  --test bidirectional_cohort_view_test -- --nocapture
```

## Measured lower-risk source-follow acceptance

The disarmed measured candidate uses:

```bash
uv run python -m hypervector \
  --data-root data \
  hypervelocity-tui \
  --config configs/hypervelocity_source_follow_bidirectional_minrange12_alloc10_lev5_shadow.toml
```

This profile must remain backend-authored and display all of the following:

- bidirectional completed-5m source authority, with 1m and 15m explicitly not
  classified;
- 10% isolated margin, 5x leverage, and 0.50x equity gross notional;
- 1.333% gross margin return and the unchanged 26.67-bps BTC price target;
- no fixed stop, post-only entry/target, and 24-hour maximum hold;
- `observe` as annotation collection with inference inactive and no filtering
  or scaling authority;
- `development / not live proven`, execution economics inconclusive, and two
  active book-gap windows from the pinned research artifact;
- latest backend mark, margin, notional, target order, fees, liquidation price,
  and signed liquidation distance for an open position;
- `N/A` rather than zero for missing confidence, range, funding, L2, or cost
  measurements.

At 120x36, the header must retain execution mode, feed mode, and backend
connection. The policy panel and active-position panel use compact layouts.
Screen 4 must scroll with the selected row and show the full selected value in
the detail footer.

Generate deterministic source-follow buffers at both acceptance sizes:

```bash
HYPERVECTOR_VISUAL_SNAPSHOT=1 \
  cargo test -p hypervector-tui \
  --test btc_source_follow_view_test \
  measured_secondary_screens_retain_truth_at_acceptance_sizes -- --nocapture
```

## Persistence and honesty protocol

1. Record the current run ID, equity, journal count, and open/pending state.
2. Quit with `q` and verify the shell returns normally.
3. Relaunch the same supervised command.
4. Confirm the same durable run and portfolio resume unless a new backend run
   identity is explicitly required by an incompatible execution fingerprint.
5. Confirm shadow mode never writes a live decision or constructs a live venue
   execution client.
6. Inspect regime rows and assert no `submit_entry` occurs when `state_5m` is
   `RANGE`, `TRANSITION`, or `UNKNOWN`.

## File-playback parity

```bash
uv run python -m hypervector \
  --data-root data \
  regime-export --symbol BTC --timeframe 1m --bars 1500

cargo run -p hypervector-tui --bin tui-regime-detector -- \
  --symbol BTC --timeframe 1m \
  --file data/exports/regime_snapshots.json
```

Playback states, reasons, timeframe labels, and structure scores must match
`classify_multitimeframe(..., faithful_regime_config())` for the same rows.
Incomplete snapshots are rejected instead of backfilled with synthetic values.

## Sign-off record

```text
Date:
Commit:
Terminal and dimensions:
Backend run ID:
Screen 1 dashboard parity: PASS | FAIL
Screen 2 regime parity: PASS | FAIL
Screen 3 chart parity: PASS | FAIL
Screen 4 config parity: PASS | FAIL
Quit/restart persistence: PASS | FAIL
No-submit shadow honesty: PASS | FAIL
Reviewer notes:
```

Automated green tests increase confidence in parsing and rendering. They do not
replace human visual inspection or a fresh venue-matched shadow/real comparison.
