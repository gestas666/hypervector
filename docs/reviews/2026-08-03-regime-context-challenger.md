# Regime context challenger — 2026-08-03

## Problem and success criteria

The live cohort needed a dedicated regime view that could explain current
range/trend structure, retain entry-to-current drift for open positions, and
judge fixed-time exits against the exact causal context available at exit.
Success required backend-authored telemetry, no TUI-side classification, no
execution authority, restart-safe lifecycle joins, and later outcome paths
that can falsify the exit hypothesis.

## Evidence reviewed

- `data/logs/research/regime_component_attribution_20260803_gapq240.json`
- Four Hyperliquid assets: BTC, ETH, HYPE, and SOL
- Chronological validation and pseudo-holdout windows
- 5, 15, 30, and 60-minute strictly future paths
- 240-minute quarantine around filled source gaps
- Current live cohort ledgers under `data/live/bidirectional_cohort/`

Across the 32 asset/window/horizon slices, NON_RANGE observations had higher
median absolute close movement and favorable/adverse excursion than RANGE:

| Diagnostic | Median NON_RANGE/RANGE ratio | Stable slices |
|---|---:|---:|
| Absolute close return | 1.300x | 32/32 |
| Favorable excursion | 1.330x | 32/32 |
| Adverse excursion | 1.419x | 32/32 |

EMA gap, SMA gap, HA-RSI level, and trend slope had negative median daily
directional IC in all 32 later slices. Their magnitudes had positive association
with future absolute excursion in all 32 slices. The evidence supports using
these components as movement/extension context. It contradicts treating their
raw directions as independently validated trend-following votes.

## Implemented contract

Screen 9 is the backend-authored Regime Command Deck. It contains the 1m/5m/15m
state matrix, per-asset range gauges, component and order-book telemetry,
backend label history, open lifecycle drift, and closed lifecycle reflection.

The causal context challenger adds two deliberately separate scores:

- Structure support uses provider primary, canonical primary, 1m, 5m, and 15m
  states with explicit hierarchy weights `3/3/1/3/2`.
- Component alignment uses EMA, SMA, Cipher A, HA-RSI, 5m bias, 15m bias, and
  trend slope direction with display weights `1/1/1/1/2/2/1`.

Those weights encode timeframe hierarchy; they are not fitted expected-return
coefficients. Component alignment is not folded into structure support.
Movement strength remains canonical regime confidence and is explicitly not a
win probability.

Open positions expose whether their current structure is supportive, opposed,
or mixed. Closed reflections preserve the same assessment at the authoritative
exit and retain 5/15/30/60-minute post-exit paths. This makes the eight-hour
timer a measurable challenger rather than an unexamined rule.

The rolling checkpoint also publishes a cumulative maximum-hold journal with
supportive, opposed, mixed, and unavailable buckets present even when their
counts are zero. Screen 9 projects these as `8H OBS`, so subsequent timer exits
automatically update the experiment without manual ledger interpretation.

## Authority and failure modes

- `report_only=true`
- `execution_authority=none`
- `runtime_strategy_changed=false`
- `automatic_strategy_changes=false`

No entry, exit, sizing, leverage, stop, routing, or timer behavior changed.
Missing context remains unavailable. Invalid score ranges, invalid states,
incomplete report-only contracts, conflicting lifecycle identities, or stale
checkpoint coverage fail validation.

## Current evidence and falsification

At the verified live checkpoint, BTC short was mixed/transition and its
components pointed against the position; HYPE long remained directionally
supported. Both were protected by venue stops and the cohort reported no
faulted assets. The two prior HYPE exits both occurred in mixed/range context.

Confidence is high in the data join, schema, display, and no-authority boundary.
Confidence is low in any economic exit improvement because there are only two
closed live lifecycles. A checkpoint/ledger mismatch, an assessment calculated
from data after its decision timestamp, or an order/routing change caused by
the challenger would falsify the implementation. Repeated post-exit evidence
showing timer exits outperform context-conditioned alternatives would falsify
the hypothesis that the fixed timer should become regime-aware.

## Verification

- `uv run pytest tests/ -q -m 'not network'`: 3,110 passed, 4 deselected
- `cargo test -p hypervector-tui`: 147 passed
- `cargo clippy -p hypervector-tui --all-targets -- -D warnings`: passed
- Ruff and formatting checks: passed

## 09:31 EDT extension-decision projection

The cumulative timer journal now converts the causal context into an explicit
report-only challenger decision: `KEEP` for directionally supported exits,
`EXIT` for opposed or mixed exits, and `WAIT` when context is unavailable. For
each completed-candle horizon, only `KEEP` decisions receive an incremental
gross-dollar projection. Censored and missing paths remain separate; projected
PnL explicitly excludes later fees, funding, slippage, and stop execution.

The first refreshed live checkpoint contained two timer exits. Both were
mixed/transition, so the challenger agreed with the authoritative timer on both:
`KEEP 0 / EXIT 2 / WAIT 0`. This is pipeline validation rather than evidence of
economic superiority. The current HYPE long was still open, directionally
supported, and therefore had no post-exit result in that checkpoint.

The checkpoint sidecar was refreshed without restarting or modifying the live
order backend. Screen 8 projects the cumulative decision count in the routing
counterfactual panel. The existing live timer remains authoritative.

## 10:02 EDT exact open-exit projection

Open lifecycle reflections now join the exact accepted protective-stop order
to the timer contract that is actually managing the position. They publish the
maximum-hold duration, absolute deadline, remaining milliseconds, expiry state,
controller identity, and whether the value came from a bound provider plan or
the legacy asset runtime default. Screen 9 renders the venue stop, US Eastern
deadline, time remaining, and the report-only regime assessment on separate
lines so narrow panes do not truncate the evidence.

The refreshed live checkpoint identified HYPE lifecycle
`HYPE:508799417980` as a long with stop order `508799445939` at
`51.572096`. Its authoritative eight-hour deadline is
`2026-08-03 10:45:15 EDT`; the runtime source is the asset default because the
currently running backend predates bound-plan snapshot telemetry. This is not
an inferred strategy change: the report remains execution-incapable and the
live backend was not restarted.

The extension projection is now stop-aware. A hypothetical retained position
that touches its accepted stop before a 5/15/30/60-minute horizon is scored at
the submitted trigger, while missing protection is reported separately. This
still is not executable net PnL: later fees, funding, trigger slippage, and the
gap between submitted trigger and actual stop fill remain excluded.

Open reflections additionally publish a causal path from the first complete
one-minute candle after the entry fill through the latest completed candle.
The TUI reports current directional return, maximum favorable excursion,
maximum adverse excursion, peak giveback, and completed-bar coverage. Candles
that overlap the entry fill and incomplete current candles are excluded.

At the first verified live projection, the active HYPE long had 448 completed
post-entry bars, `+324.3 bps` maximum favorable excursion, `+296.4 bps`
current directional return, `27.9 bps` peak giveback, and `16.9 bps` maximum
adverse excursion. These values describe this lifecycle; they do not validate
a trailing-stop threshold. The previously tested 60/15/30-bps protection
candidate underperformed the fixed timer on matched historical entries, so it
remains rejected pending contradictory forward evidence.

## 11:20 EDT first supported-timer outcome

HYPE lifecycle `HYPE:508799417980` closed at the authoritative eight-hour
timer for `53.911`, after `28,798,217 ms`. The exact venue lifecycle recorded
`$0.899488` net PnL, `18.06%` net return on its `$4.979588` entry margin,
`$0.021958` fees, and `-$0.001594` funding. The causal exit assessment was
`still_directionally_supported`: structure support `1.0`, component alignment
`1.0`, and movement strength `0.9556`.

The first three strictly later completed-candle paths all continued the long:

| Added hold | Directional close | Favorable/adverse excursion | Stop crossed | Incremental gross PnL |
|---:|---:|---:|:---:|---:|
| 5m | +16.14 bps | +39.88 / 33.20 bps | no | +$0.04176 |
| 15m | +25.60 bps | +62.88 / 33.20 bps | no | +$0.06624 |
| 30m | +22.44 bps | +62.88 / 33.20 bps | no | +$0.05808 |
| 60m | +60.66 bps | +78.46 / 33.20 bps | no | +$0.15696 |

The submitted stop `508799445939` at `51.572096` remained untouched in every
resolved path. The 60-minute path became valid on the first checkpoint after
the 11:45 candle completed; no incomplete candle was used. All four horizons
agree with the extension challenger for this one trade. That is not enough
evidence to promote it. Later funding, replacement-exit fees, and
replacement-exit slippage remain unmeasured.

The cumulative compatible-profile journal now contains four closed trades:
three wins, one loss, `$1.043222` net PnL, `$0.085849` fees, and `$0.003251`
funding on `$19.796322` summed entry margin. The three timer exits comprise two
mixed/transition decisions and this one supported decision. Of the mixed
examples, one favored exit after 15/30/60 minutes while the other reversed at
15/30 minutes and resumed the original direction by 60 minutes. That split
prevents a claim that mixed context is a validated exit trigger.

BTC lifecycle `BTC:509104805648` remained open, long `0.00039 BTC`, protected
by accepted stop `509104867159` at `63231.072`, with no backend faults. Its
structure remained directionally supportive while component alignment was
mixed (`0.1111`). No runtime rule, position, order, or timer was changed by
this review.

## 11:31 EDT runtime-configuration generation incident

The armed process started with profile fingerprint
`12e4d47e94d1176738b5881c91240a7d29d8efa19425cf17a25131be99cfa47c`.
The current TOML, modified at `2026-08-03 07:16:04 EDT`, resolves to
`0919ed27ccb60fa7dbe874d013e56c2380c06cc9be99a2c21f18c1c059b81186`.
The mismatch is direct evidence that the running process predates the current
provider execution contract.

BTC lifecycle `BTC:509104805648` confirms the behavioral consequence. It has
an accepted 80-bps venue stop and the legacy asset-default eight-hour timer,
but no provider-bound target order. The current source-follow contract instead
specifies a maker target at `26.6667 bps` and a 24-hour maximum hold. The open
trade remains protected and fault-free; it is not executing the intended
current exit shape.

At the `63,741` entry, the configured target is `63,910.976`. The first later
completed one-minute candle to cross it began at `10:56:00 EDT`, about 10m45s
after the entry fill, and reached `63,934`. Four additional captured candles
also exceeded the target. If a reduce-only post-only target had been accepted
and retained at entry, this is strong but not conclusive evidence that it could
have filled: completed bars do not prove queue position, order acceptance, or
exact intrabar sequencing. Gross PnL at the target would be approximately
`$0.066291` before the observed entry fee, exit fee, funding, and any
order-specific execution effects.

The rolling checkpoint now reloads the non-secret configuration identity on
every publication and compares it with the authoritative running fingerprint.
The TUI renders `STALE RUNTIME CONFIG`, `RESTART WHEN FLAT`, and both 12-character
fingerprint prefixes when they differ.
This evidence is advisory only: `execution_authority=none` and
`automatic_restart=false`. The read-only sidecar was restarted; the armed
backend and its BTC position were not interrupted.

Restart readiness is derived from every asset's authoritative final state,
signed position size, and observed open-order IDs. The current value is
`wait_for_flat_and_no_orders` with blocker `BTC`, rendered as
`WAIT BTC OPEN/ORDER`. Only an all-asset `FLAT`, zero-size, zero-order prefix
becomes `candidate_flat_no_orders`; that is a verification candidate, not an
automatic restart instruction.

Validation after the change:

- `uv run pytest tests/ -q -m 'not network'`: 3,112 passed, 4 deselected
- `cargo test -p hypervector-tui`: 153 passed
- `cargo clippy -p hypervector-tui --all-targets -- -D warnings`: passed
- Ruff, Rust formatting, CLI status, and a production-shaped checkpoint: passed

The safe correction point is the first verified flat state with no cohort-owned
orders. At that point the backend must be restarted from the current TOML and
the new configuration identity, bound target order, stop order, and maximum
hold must all be reconciled before the next entry. A matching fingerprint with
an absent target would falsify the hypothesis that configuration generation is
the sole cause and require a separate bracket-submission investigation.
