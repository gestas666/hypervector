---
name: hypervector-regime-detector
description: >
  Operate and validate the canonical 1m/5m/15m Hypervelocity regime engine and
  its backend-authored read-only Ratatui telemetry views.
---

# Hypervector Canonical Regime Engine

## Authority contract

The production classifier is implemented in `src/hypervector/regime/` and the
faithful thresholds are defined by `faithful_regime_config()`. Hyperliquid
candles are open-timestamped. A 5m or 15m aggregate becomes available at the
last constituent one-minute open timestamp; future values must never be shifted
into an earlier decision row.

| State | Backend meaning | Entry effect |
|---|---|---|
| `TREND_UP` | Authoritative 5m positive trend structure | Long eligible |
| `TREND_DOWN` | Authoritative 5m negative trend structure | Short eligible |
| `BREAKOUT` | 5m breakout state | Eligible only when 1m confirms the same direction |
| `RANGE` | 5m range/chop/compression structure | Entry blocked |
| `TRANSITION` | Mixed 5m structure | Entry blocked |
| `UNKNOWN` | Warmup incomplete | Entry blocked |

The 1m state is execution-timeframe telemetry and breakout confirmation; it
cannot replace a non-directional 5m primary state. The 15m state is context and
is not a hard veto. `regime_strength_score` is the mean 1m/5m/15m EMA-gap
strength percentile rank normalized to `[0, 1]`. It is a report-only technical
diagnostic, not a model probability or execution gate.

## Shared-cohort routing authority

In the staged shared cohort, canonical structure has a narrow active role only
when multiple providers emit intents for the same coin in the same routing
cycle. The router scores the intent side against completed 1m/5m/15m states
with hierarchy weights 1/3/2, then falls back to configured provider priority
and decision time. This can choose an entry or an opposite-intent exit.

This is conflict preference, not a standalone gate: a lone intent remains
routable even when its score is opposed. Canonical regime changes do not by
themselves force an exit, change leverage, or change size. Screen 2 persists
and displays the exact score, stance, timestamp, and basis. Screen 8 remains
the full diagnostic workstation and must not infer execution authority from
report-only component alignment.

For the installed V89 monitor, use the authenticated launch command and
strategy planning controls in `docs/guides/cohort-strategy-regime-monitor.md`.
Screen 2's setup inspector separates recorded provider indicators, canonical
context at the strategy decision and the latest recorded canonical context.
Screen 9 separates effective settings from a local next-run draft.

The telemetry collector may recover several completed bars in one cycle. The
durable identity is `(strategy_id, symbol, decision_time_ms)`; recovered rows
must be unique and ordered. Every strategy intent is annotated only from the
latest canonical row whose decision time is at or before that intent. A later
row in the same recovery batch must not rewrite an earlier intent. `UNKNOWN`
is explicit unavailable evidence: it contributes neither routing preference
nor maximum-hold extension support and must not be converted to neutral trend
evidence.

The v39 post-start report is a technical check, not a performance gate. It
requires fresh telemetry-only rows for exactly BTC, ETH, SOL, and HYPE, causal
decision/observation ordering, complete signed component directions, and no
`UNKNOWN` state. Missing or stale evidence rejects the report without pausing,
retuning, resizing, or otherwise acquiring execution authority.

The faithful thresholds use EMA 21/55, a 240-bar structure lookback, a 1 bp
minimum trend gap, and BBWP(20) ranked over 240 bars with compression below
25%. A 90-bar breakout requires 8 bp clearance and 2.5x the prior 20-bar mean
volume. RSI(14) crossing its EMA(7), prior-bar BBWP compression, directional
EMA separation, and the breakout evidence form a tactical annotation rather
than an execution gate. The strict conjunction emitted 13 annotations and
matched 0/35 venue-matched historical entries on the measured 90-day window,
while persistent 5m structural eligibility matched 24/35 exactly and 27/35
within 10 minutes; larger fresh shadow evidence can update that policy.

## Unified live shadow view

```bash
uv run python -m hypervector \
  --data-root data \
  hypervelocity-tui \
  --config configs/hypervelocity_faithful.toml
```

The Python command owns the backend lifecycle. The Rust TUI reads the backend
ledger and does not simulate trades. Normal quit preserves the durable shadow
portfolio. A fresh start is explicit and recoverably backed up:

```bash
uv run python -m hypervector \
  --data-root data \
  hypervelocity-shadow-reset --yes
```

## File playback

Export snapshots through the canonical classifier, then open them read-only:

```bash
uv run python -m hypervector \
  --data-root data \
  regime-export --symbol BTC --timeframe 1m --bars 1500

cargo run -p hypervector-tui --bin tui-regime-detector -- \
  --symbol BTC --timeframe 1m \
  --file data/exports/regime_snapshots.json
```

Snapshot playback must not manufacture missing prices, OHLCV, timestamps,
microstructure, funding, regime labels, or policy weights. Missing optional
microstructure and funding are explicitly marked unavailable.

## Evaluation and tuning

```bash
uv run python -m hypervector hypervelocity-regime-eval \
  --positions docs/external/manual_positions_unified_2026-07-09_to_today_20260724_150845.csv

uv run python -m hypervector hypervelocity-regime-autotune \
  --positions docs/external/manual_positions_unified_2026-07-09_to_today_20260724_150845.csv \
  --n-trials 100 --seed 42 \
  --out data/logs/research/hypervelocity_regime_autotune.json

uv run python -m hypervector hypervelocity-regime-challengers \
  --symbol BTC --timeframe 1m --lookback 180 \
  --forward-horizon 30 --seed 42 --n-splits 3 \
  --out data/logs/research/hypervelocity_regime_challengers.json
```

Evaluation is chronological and report-only. Retain every valid trial result,
including losses, sparse trades, weak scores, and poor drawdown. Only a
technical failure may mark a trial as an error. Expanding volatility terciles,
walk-forward GMM, and training-only Wasserstein states are annotation-only.
Optional HMM/MS-AR arms report a missing dependency instead of silently
substituting a non-causal model. Challengers remain non-executable until a
separate decision explicitly changes that policy.

Exact upstream strict/legacy comparisons use the research database, not the
runtime classifier path:

```bash
uv run python -m hypervector --data-root data \
  research-db-live-event-import --symbol BTC
uv run python -m hypervector --data-root data research-db-shadow-import
uv run python -m hypervector --data-root data research-db-regime-compare
```

Import each source-generated label/metadata pair sequentially with
`research-db-regime-label-import`. `shadow_completed_5m_bars` requires five
complete 1m observations, and the comparison joins a source label only after
its recorded five-minute availability. These relations are report-only and
must not alter entry, sizing, exit, or model authority.

The 2026-07-27 strict 90-day venue comparison found that changing only the
range filter from Choppiness85 to BBWP25 produced an identical
entry/structural decision fingerprint. EMA21/55 reduced modeled liquidations
relative to the original, but the full BBWP blueprint did not dominate
EMA-only or EMA+clearance across L2 fill assumptions. Every tested TP-only
candidate had at least -99.95% modeled maximum drawdown at 70% margin and 40x.
Retain BBWP tactical fields as telemetry, but do not claim they improved the
measured entry decisions or promote a candidate from this evidence alone.

## One-year component attribution

The frozen four-asset report-only command is:

```bash
uv run python scripts/regime_component_attribution.py \
  --bars BTC=data/cache/BTC_1m_365d.parquet \
  --bars ETH=data/cache/ETH_1m_365d.parquet \
  --bars SOL=data/cache/SOL_1m_365d.parquet \
  --bars HYPE=data/cache/HYPE_1m_365d.parquet \
  --development-start 2025-07-28T00:00:00Z \
  --development-end 2026-01-28T00:00:00Z \
  --validation-end 2026-05-28T00:00:00Z \
  --pseudo-holdout-end 2026-07-28T00:00:00Z \
  --output data/logs/research/regime_component_attribution_<run>.json
```

Labels begin after the completed decision bar, cannot cross a chronological
split, and explicitly exclude decisions or future paths touching an
`hl_gap_fill` minute. Numeric associations are summarized as daily Spearman
ICs; pooled row correlations are prohibited. Report every overlapping row and
the separate greedy non-overlapping effective count.

The 2026-08-03 venue report found lower absolute future movement during RANGE
than non-RANGE in 48/48 asset/segment/horizon cells. Regime strength, absolute
EMA gap, absolute SMA gap, and absolute trend slope had positive daily
association with future excursion in 48/48 cells. This supports continued
observe-only range and movement-intensity telemetry. It does not establish a
trade edge. Canonical direction had 0/32 positive pseudo-holdout direction
cells, so it is not a standalone directional predictor. Full evidence and
falsifiers are documented in
`docs/research/regime-component-attribution-2026-08-03.md`.

The predeclared `--gap-quarantine-minutes 240` sensitivity preserved the RANGE
separation in 48/48 cells after removing every decision whose rolling features
could still contain a gap-filled minute. Use this option for venue-evidence
robustness; it is not a runtime classifier setting.

## Verification

```bash
uv run pytest tests/test_regime_classifier.py \
  tests/test_hypervelocity_regime_eval.py \
  tests/test_regime_snapshot_export.py \
  tests/test_regime_component_attribution.py \
  tests/test_regime_component_attribution_script.py \
  tests/test_canonical_regime_recovery.py \
  tests/test_cohort_canonical_regime_telemetry.py \
  tests/test_v39_canonical_regime_acceptance.py \
  tests/test_v39_poststart_acceptance.py -q
cargo test -p hypervector-tui
```

Falsifiers include prefix non-invariance, disagreement with a venue-native 5m
candle, a 1m trend overriding 5m `RANGE`/`TRANSITION`/`UNKNOWN`, unconfirmed
breakout direction, fabricated TUI values, or a technical score labeled as a
model probability.
