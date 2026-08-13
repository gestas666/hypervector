# Bidirectional shared live cohort — implementation record

**Status:** Implemented and verified while disarmed on 2026-08-01. This record
does not grant live authority.

## System contract

One backend process owns one Hyperliquid account lock and one authenticated SDK
pair. It schedules BTC, ETH, SOL, and HYPE sequentially through serialized SDK
calls. Every configured coin and provider declares both `long` and `short`.
The portfolio permits one position per coin and at most four different open
coins. Strategy results remain measurements rather than implicit permission
gates; technical integrity failures remain fail-closed.

Two attributed signal providers are enabled initially:

- `hulk_expansion_bidirectional_tuned_v2`: completed 30-minute expansion
  decisions built causally from completed 5-minute Hyperliquid candles;
- `range_onset_bidirectional_v1`: completed 1-minute range-onset decisions with
  multi-timeframe regime annotations.

Both use a 60-second maximum entry age. On restart or data transport delay, an
older eligible decision is journaled as `stale_completed_decision` and cannot
be routed. This is a technical freshness invariant, not a performance filter.

## Execution and lifecycle invariants

- Mainnet, isolated margin, 5x configured leverage.
- Runtime venue metadata must agree with BTC 40x, ETH 25x, SOL 20x, and HYPE
  10x maxima. Direct public metadata agreed on 2026-08-01; armed preflight
  revalidates it.
- Each coin uses a $25 maximum notional and 3% account-margin envelope.
- Each entry must reconcile and acquire a venue-native reduce-only protective
  stop before its lifecycle reports `OPEN`.
- The configured 80-bps protective stop and eight-hour maximum hold apply to
  both directions on every coin.
- A maximum-hold close suppresses same-cycle re-entry. An opposite strategy
  intent closes first and also does not reverse in the same cycle.
- Reconciliation is repeated after every routed action before cohort telemetry
  is published, preventing a post-entry TUI snapshot from using pre-entry venue
  facts.
- Stopping an open lifecycle preserves its venue-native protection and durable
  ledger identity for restart reconciliation.

## Backend and telemetry implementation

Key modules:

- `multi_asset_live_config.py`: strict asset/provider/runtime identity;
- `serialized_hyperliquid_clients.py`: one lock around shared SDK calls;
- `bidirectional_cohort_factory.py`: one SDK build for all four coins;
- `multi_asset_intent_poller.py`: causal provider clocks and stale-entry
  withholding;
- `bidirectional_intents.py`: deterministic provider priority, one-position
  per symbol, and configured cohort-capacity routing;
- `multi_asset_live_runner.py`: reconcile, route, protect, close, and publish;
- `multi_asset_cohort_telemetry.py`: shared account, symbol lifecycle, exact
  fills, fees, funding, liquidation distance, acknowledgement latency,
  directional slippage, and measured five-second-or-later markouts;
- `scripts/multi_asset_bidirectional_live.py`: fail-closed live command;
- `scripts/multi_asset_bidirectional_canary_tui.py`: monitor-default unified
  launcher with supervised rolling analysis and immutable post-stop audit;
- `scripts/multi_asset_bidirectional_live_checkpoint.py`: execution-incapable
  latest-only rolling checkpoint process;
- `scripts/multi_asset_bidirectional_live_audit.py`: report-only run evidence
  with no order authority.

The exact config is `configs/multi_asset_bidirectional_canary.toml`. Asset
ledgers live under `data/live/bidirectional_cohort/<symbol>.jsonl`; the TUI
reads the shared `data/live/bidirectional_cohort/decisions.jsonl` projection.
Cost and fill summaries are restricted to the current run ID rather than
silently mixing prior sessions.

The profile now separates observation coverage from canary authority. Both
providers continue evaluating BTC/ETH/SOL/HYPE long and short, while
`execution_symbols` explicitly grants live routing only to the SOL range-onset
pair. Hulk and the remaining mappings are retained as journaled challengers.
The runner records a fresh challenger intent as
`provider_symbol_observe_only`; the final audit rejects any action outside the
identity's declared scope. This is an explicit configuration contract, not an
implicit performance abort gate.

The post-stop audit also computes causal counterfactual path diagnostics for
every post-activation provider evaluation. It separates eligible signals from
readiness-only annotations, attributes blockers, reports 5/15/30/60-minute
directional close return plus favorable/adverse excursion, and counts a
non-overlapping subset. These are signal diagnostics only: no order, fill,
fee, funding, size, or PnL is assumed. Missing elapsed one-minute candles are a
technical coverage gap; unresolved end-of-run horizons remain right-censored.
Provider evaluations preserve exact machine-readable decision-time indicator
values in addition to compact operator strings, so later parity and drift
analysis does not depend on rounded display text.
The stopped-run audit conditions resolved forward paths on those exact values:
numeric metrics separate positive from nonpositive directional outcomes, while
categorical metrics report outcomes by exact JSON value. Metric gaps and type
drift remain technical evidence failures. The audit does not train a model,
select a threshold, or modify execution behavior.

The live sidecar snapshots only complete JSONL prefixes and discloses any
in-progress trailing suffix. It atomically replaces one bounded latest artifact
instead of copying full ledgers into interval histories. Each checkpoint
includes the same audit evidence plus explicit lifecycle reconciliation across
the cohort heartbeat and all four asset state machines. Performance remains
advisory; the sidecar has no automatic pause, tuning, sizing, or execution path.
Final immutable audits do not use the rolling-tail allowance.

## TUI implementation

The TUI remains read-only and renders the cohort without requiring legacy
single-symbol regime snapshots:

1. Dashboard: shared equity/margin/notional, rolling-checkpoint freshness,
   reconciled lifecycle and evidence coverage, four coin lifecycles, long+short
   capability, position/mark/entry/liquidation, liquidation distance, fees,
   funding, stop identity, faults, and the recent exact fill journal.
2. Router: recent selected actions plus every withheld intent and backend
   reason.
3. Chart: per-coin completed-1m backend reference-price trajectories.
4. Config: effective asset envelopes, provider clocks/priorities, and exact
   canary versus observe-only execution scope.

The Rust parser rejects malformed cohort identity, missing bidirectionality, or
snapshot/config symbol disagreement. It does not calculate trades or infer
missing backend values.

## Commands

Safe monitor-only attachment:

```bash
uv run python scripts/multi_asset_bidirectional_canary_tui.py
```

The following live form requires fresh explicit user authorization at the time
of use; documentation alone is not authorization:

```bash
uv run python scripts/multi_asset_bidirectional_canary_tui.py \
  --mode live --enabled --i-accept-live-risk
```

Backend-only equivalent:

```bash
uv run python scripts/multi_asset_bidirectional_live.py \
  --enabled --i-accept-live-risk
```

## Validation and falsifiers

Current repository-wide verification passes 2,685 offline Python tests with
four network tests deselected, all 102 Rust/TUI tests, strict all-target Clippy,
Rust formatting, task-scoped Ruff, backend status, and whitespace checks. Both the
backend-only and unified
TUI live commands were invoked without their arm flags and refused before
constructing execution authority.

Technical readiness is falsified by any unprotected open position, unknown or
duplicate fill identity, stale decision execution, wrong account owner,
position-capacity breach, venue/backend disagreement, malformed current-run
cost attribution, or TUI/backend mismatch. Profit, loss, drawdown, and cadence
update economic evidence but do not retroactively change these technical
facts. The first live evidence cycle remains bounded to 3–5 calendar days.
