# Market Cipher / Hulk Smash Rehabilitation Review

## Decision

The rebuilt two-symbol and bidirectional Hulk variants are not promotable. The
development-selected BTC short variant `hulk_expansion_short_robust_v3` is a
directional cohort survivor and may advance to shared-capital shadow/canary
preparation. It is not established as a profitable live strategy.

Confidence is medium for the narrower claim that the BTC variant contains a
repeatable historical directional signal under the tested bar replay. Confidence
in live profitability is low-to-medium because the independent pseudo-holdout
was slightly negative, the complete sample has only 66 trades, June and July
were negative, and OHLC replay cannot measure queue position or intrabar path.

This decision would be falsified by materially worse venue-matched fills,
after-fee canary losses inconsistent with the replay envelope, reconciliation
faults, or a fresh sample showing the forward result was concentrated in one
expired regime.

## Restored System

The rehabilitation preserves Hulk Smash as the deterministic directional core.
Market Cipher A/B/DBSI and Krown components are causal annotations and signal
evidence; the Trading Brain and regime model have no execution authority.

The replay uses:

- completed 30-minute signals and adverse next-bar entry;
- one position per symbol and one shared $15,000 portfolio;
- 0.25% equity risk per trade and 5x leverage;
- structural wick stops clipped to 20–75 bps;
- an all-at-target 3R control exit and 48-bar maximum hold;
- 4.5 bps adverse entry/market-exit fees, 1.5 bps target fees;
- 2 bps adverse entry and market-exit slippage;
- authentic hourly Hyperliquid funding;
- pessimistic liquidation-before-stop-before-target ordering;
- gap-through-stop execution and end-of-data closes.

No research command has wallet, order-submission, paper-fill, or live authority.

## AutoTune Protocol

The local signal surface was declared before evaluation and contains 27 trials:

- minimum score: 7, 8, or 9;
- pivot lookback: 6, 8, or 10 bars;
- ADX bands: 16/23, 18/25, or 20/27;
- fixed quality identity: Supertrend 7/3, ADX period 20, squeeze period 20.

Every trial was evaluated over three non-overlapping development folds under
nominal costs, higher fees/slippage, and one additional 30-minute entry delay.
All 243 cells, including losing and sparse results, are retained in
`data/research/strategy_trials.duckdb` under run
`20260801-hulk-local-signal-v1`. The immutable report is
`data/logs/research/20260801_hulk_local_signal_autotune_v1.json`.

Ranking prioritized positive cells, then worst-cell PnL, total PnL, minimum PF,
and drawdown. The selected neighborhood was pivot 6 and ADX 16/23. Score values
7, 8, and 9 generated identical trades, so score is locally non-identifying.
Score 7 was frozen as a deterministic tie resolution, not because it produced a
better observed result.

The selected development cells were:

| Fold | Nominal | Cost stress | +1 bar delay |
|---|---:|---:|---:|
| 1 | +$39 | +$7 | -$145 |
| 2 | +$192 | +$151 | -$141 |
| 3 | +$124 | +$70 | +$73 |

The delayed-entry losses show that even the selected neighborhood remains
timing-dependent in development. Selection improved stability; it did not erase
the failure mode.

## Chronological Evidence

Exact standalone BTC portfolio results:

| Segment | Dates | Trades | Net PnL | PF | Max DD | Liquidations |
|---|---|---:|---:|---:|---:|---:|
| Backward check | 2025-08-02–2025-08-23 | 2 | +$60.86 | 2.25 | 0.50% | 0 |
| Development | 2025-08-23–2026-02-01 | 39 | +$362.47 | 1.33 | 1.85% | 0 |
| Validation | 2026-02-01–2026-05-01 | 18 | +$405.59 | 1.89 | 1.27% | 0 |
| Pseudo-holdout | 2026-05-01–2026-07-27 | 9 | -$18.35 | 0.93 | 1.57% | 0 |

The backward check is directionally favorable but statistically weak because it
contains only two trades. The pseudo-holdout is a direct contradictory result,
although the loss is small relative to the prior validation gain.

The continuous 2025-08-23–2026-07-27 diagnostic produced 66 trades, +$758.57,
PF 1.41, 1.85% maximum drawdown, $438.44 in fees, +$31.15 funding cashflow, and
zero liquidations. It is descriptive and does not replace segmented validation.

Monthly PnL became negative in June (-$137.36) and July (-$106.37). Current
canary evidence therefore matters more than the full-period average.

## Forward Robustness

The exact standalone BTC candidate remained positive under every predeclared
combined-forward perturbation from 2026-02-01 through 2026-07-27:

| Scenario | Trades | Net PnL | PF | Max DD | Liquidations |
|---|---:|---:|---:|---:|---:|
| Nominal | 27 | +$386.75 | 1.52 | 1.57% | 0 |
| Higher fees/slippage | 27 | +$165.91 | 1.20 | 1.64% | 0 |
| One extra 30-minute delay | 25 | +$11.14 | 1.01 | 1.58% | 0 |
| 60 bps stop cap | 27 | +$276.27 | 1.35 | 1.62% | 0 |
| 90 bps stop cap | 26 | +$51.41 | 1.07 | 1.76% | 0 |
| Double funding | 27 | +$390.69 | 1.53 | 1.57% | 0 |

The one-bar-delay result is barely above break-even. Timely execution is a
material operating assumption, not a cosmetic optimization.

## Rejected and Observe-Only Variants

- Bidirectional tuned Hulk: development +$1,715/PF 1.66, validation
  -$683/PF 0.71, pseudo-holdout -$103/PF 0.93. Forward falsified.
- Two-symbol short v3: combined forward -$109/PF 0.94 because SOL lost about
  $491 while BTC gained about $381. Forward falsified the shared BTC/SOL form.
- Trading Brain negative-veto and continuous-sizing arms improved some windows
  but degraded the first validation window. Brain remains annotation-only.
- Causal 30m/2h/6h regime scaling improved development but did not remain
  positive across both forward windows. Regime remains telemetry, not a gate.

## Risks and Validation Requirements

- **Sparse cadence:** 66 trades in roughly 11 months is about 1.4 trades/week.
  Hulk cannot alone meet a high-frequency portfolio objective.
- **Recent decay:** two negative recent months may represent ordinary variance
  or edge decay; the present evidence cannot distinguish them.
- **Bar ambiguity:** stops and targets touched in one bar use pessimistic ordering,
  but real market gaps and queue position may still be worse.
- **Post-hoc BTC isolation:** BTC was retained after the two-symbol forward split
  exposed SOL weakness. Forward robustness supports the hypothesis, but a fresh
  canary is required for clean confirmation.
- **No long counterpart:** the current survivor is short-only. A separate long or
  mean-reversion strategy is still required for a diverse active portfolio.

Good enough for the next phase means deterministic shared-capital attribution,
no duplicate BTC exposure, backend/TUI parity, fail-closed launch controls, and
a small explicitly authorized canary that records real decisions, fills, fees,
funding, slippage, markouts, liquidation distance, and reconciliation evidence.

## Shared-Capital Cohort Result

The failed Apex mean-reversion candidate remains an observer/negative control.
Allowing it to own BTC rejected 23 Hulk intents in the development comparison
and selected a negative Hulk subset, so it was removed from the active allocator
under the requirement to eliminate conflicting, non-surviving exposure.

The active report-only set contains Hulk plus the Apex market-making measurement
candidate. Hulk has priority for simultaneous BTC entries; already-active
positions are not synthetically preempted. Every ownership or margin rejection
remains in the artifact.

| Segment | Shared net | Max DD | Hulk PnL | MM PnL | Rejections |
|---|---:|---:|---:|---:|---:|
| Development overlap | +$102.35 | 1.81% | +$108.19 | -$5.85 | 6 |
| Validation | +$381.70 | 0.60% | +$396.16 | -$14.46 | 1 |
| Robustness | +$84.19 | 1.21% | +$87.57 | -$3.38 | 3 |

The MM leg did not add profit and remains eligible only to collect live execution
measurements. A production allocator must cancel/reconcile MM quotes before Hulk
takes BTC ownership; completed-outcome research cannot estimate partial-session
PnL from such preemption.

## Staged Canary Operations

The frozen Hulk candidate now has a one-terminal supervisor for either a
no-submit observer or an explicitly armed live canary:

```bash
uv run python scripts/hulk_smash_canary_tui.py --mode observe
```

The live variant additionally requires both explicit risk flags. This review
does not grant that authority. The supervisor starts the authoritative backend,
waits for a new run ID with the exact profile fingerprint and arm state, then
opens the read-only TUI against the same append-only ledger. An older process
cannot satisfy startup by appending unrelated telemetry.

Normal TUI exit requests verified backend shutdown through the strategy STOP
file. A flat lifecycle stops flat; an open lifecycle preserves its exact
venue-native stop/target bracket and durable ownership instead of force-closing
because the TUI exited. The live backend is not forcibly terminated if that
transition cannot complete within 120 seconds; the process and STOP evidence
remain for operator inspection. A backend that exits nonzero is surfaced as
failure. The immutable stopped-run audit is published only after a subsequent
reconciliation has proved the position and owned orders flat.

Execution telemetry now retains:

- local order/cancel acknowledgement round-trip latency;
- expected-price versus owned-fill directional slippage;
- measured post-fill markout horizon, configured target horizon, lateness, and
  restart-recovery provenance;
- venue-reported isolated liquidation price and signed mark distance;
- honest `mixed_bracket_exit` attribution when both target and stop OIDs fill.

The TUI projects these backend fields without substituting the configured
five-second target for a later actual markout. Ledger history is retained across
normal restarts; no implicit reset is part of the launcher.

Once an explicitly authorized run is stopped and flat, its evidence is frozen
with:

```bash
uv run python scripts/hulk_smash_live_canary_audit.py \
  --decisions data/live/hulk_smash/decisions.jsonl \
  --run-id <hulk-live-run-id> \
  --out data/logs/live/hulk_smash_canary_<UTC>.json
```

This audit is report-only, snapshots and hashes an append-only ledger prefix,
and refuses overwrite. It accepts zero-fill and losing runs rather than turning
performance into an abort gate. Technical completeness instead requires exact
fill identities for fee, slippage, and markout evidence; a proven flat final
position with no open orders; truthful target/actual markout horizons; and no
unresolved backend faults.

Implementation confidence is medium-high from deterministic lifecycle,
restart, stale-ledger, TUI, and shutdown tests. Live execution confidence remains
low until a freshly authorized run records real acknowledgements, fills, costs,
markouts, and a verified flat shutdown. A mismatched backend/TUI value, an
unattributed owned fill, non-flat cleanup, or materially worse execution than
the forward robustness envelope falsifies canary readiness.

## Evidence Paths

- `data/logs/research/20260801_hulk_local_signal_autotune_v1.json`
- `data/research/strategy_trials.duckdb`
- `data/logs/research/20260801_hulk_short_robust_v3_btc_*.json`
- `data/logs/research/20260801_hulk_short_robust_v3_*.signals.parquet`
- `data/logs/research/20260801_hulk_short_robust_v3_*.trades.parquet`
- `data/logs/research/20260801_hulk_mm_active_shared_*_v1.json`

Focused verification:

```bash
uv run pytest tests/test_hulk_smash_autotune.py \
  tests/test_hulk_smash_autotune_script.py \
  tests/test_market_cipher_replay.py \
  tests/test_market_cipher_strategy_research.py \
  tests/test_market_cipher_strategy_screen_script.py -q
uv run ruff check src/hypervector/research/hulk_smash_* \
  src/hypervector/research/market_cipher_* \
  scripts/hulk_smash_autotune.py \
  scripts/market_cipher_strategy_screen.py

uv run pytest tests/test_hulk_smash*.py \
  tests/test_hyperliquid_btc*.py tests/test_runtime_lock.py -q
cargo test -p hypervector-tui
cargo clippy -p hypervector-tui --all-targets -- -D warnings
```
