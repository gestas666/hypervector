# Hypervelocity regime alignment and retune review — 2026-07-26

## Problem and decision

The system needed one point-in-time regime truth for backend execution, TUI
telemetry, playback, evaluation, and tuning. Success means venue-aligned 5m
authority, no 1m override of a non-directional 5m state, explicit 15m context,
no hidden model gate, and reproducible chronological evidence.

Decision: retain the current faithful parameters. The train-selected trial did
not improve holdout direction recall and increased label churn. Statistical
challengers remain annotation-only.

Confidence: high that the corrected code paths now share the same contract,
based on native-candle parity, prefix-invariance, Python integration, and Rust
projection tests. Confidence is medium in the retune comparison and low in its
venue-specific profitability implications because 98.02% of the 180-day cache
is Binance backfill rather than Hyperliquid.

## Frozen experiment contract

| Item | Frozen value |
|---|---|
| Execution / primary / context | 1m / authoritative 5m / non-veto 15m |
| Entry states | `TREND_UP`, `TREND_DOWN`, direction-confirmed `BREAKOUT` |
| Blocked states | `RANGE`, `TRANSITION`, `UNKNOWN` |
| Score policy | EMA-gap structure strength, report-only |
| Position labels | `manual_positions_unified_2026-07-09_to_today_20260724_150845.csv` |
| Recorded rows / unique decisions | 37 / 35 |
| Bars | BTC 1m, 259,200 rows, no reported gaps |
| Bar provenance | Binance 254,068; Hyperliquid 5,132 |
| Search | 100 deterministic candidates; seed 42 |
| Split | 70% chronological; 24 train and 11 holdout decisions |
| Split timestamp | 2026-07-22T12:24:23.415474Z |
| Forward quality horizon | 30 one-minute bars |
| Target move | 0.2% price, equivalent to 8% margin at 40x before costs |
| Trial policy | Every technically valid result retained; no performance abort |

Artifacts:

- `data/logs/research/hypervelocity_regime_eval_aligned_20260726.json`
- `data/logs/research/hypervelocity_regime_tuning_aligned_20260726.json`
- `data/logs/research/hypervelocity_regime_challengers_20260726.json`

## Corrected baseline evidence

The faithful `5/13` EMA profile recovered 26 of 35 unique recorded directions
at decision time (74.29%). It marked one recorded entry as 5m RANGE and four as
not entry-eligible. Recall rose to 85.71% when asking whether the matching state
appeared within the prior 30 minutes; that lookback diagnostic does not change
execution.

The baseline produced 3,276 evaluable breakout episodes, of which 96.67% did
not reach the directional 0.2% target within 30 bars. This is evidence that the
current breakout label is not a strong standalone 30-minute target predictor on
this mixed-venue dataset. It does not prove those events are unprofitable under
maker timing or longer holding periods.

Of 25,795 evaluable RANGE rows, 50.15% were followed by a one-sided 0.2%
expansion within 30 bars. This falsifies any claim that the current RANGE label
cleanly isolates non-directional 30-minute paths. It does not justify adding an
extra entry gate; range classification should be improved and retested.

## Tuning comparison

| Metric | Faithful trial 0 | Train-selected trial 5 |
|---|---:|---:|
| Train direction recall | 75.00% | 79.17% |
| Holdout direction recall | 72.73% | 72.73% |
| Train no-entry decisions | 2 | 1 |
| Holdout no-entry decisions | 2 | 2 |
| Label churn | 7,897 | 11,753 |
| Holdout false breakout rate | 95.00% | 95.00% |
| Holdout RANGE one-sided expansion | 50.73% | 50.83% |

Trial 5 used EMA `3/8`, structure lookback 240, trend/range percentiles 70/30,
minimum trend gap 0.5 bps, choppiness threshold 85, and the same breakout
settings as the baseline. Its training gain did not survive holdout and came
with 48.8% more churn. No trial satisfied the strict zero-missed-entry contract
on training. Trial 99 reached 81.82% holdout recall but only 45.83% training
recall with nine training no-entry decisions, so it is not credible promotion
evidence.

Recommendation: do not modify `configs/hypervelocity_faithful.toml` from this
search. A venue-pure, overlapping Hyperliquid dataset could update that decision.

## Realized-position slices and cost sensitivity

The position log is profitable on average in every observed canonical state,
including the single RANGE observation. That sample is too small and selected
by the real strategy, so it must not be interpreted as causal evidence that a
state creates edge. Direction-match percentages were 80.95% for `TREND_DOWN`
and 90.91% for `TREND_UP`; four BREAKOUT rows were not direction-confirmed at
the exact decision timestamp.

Gross margin return was reconstructed from reported net return plus reported
fees. Holding recorded funding constant, mean position margin return was:

| Execution-cost scenario | Mean | Median | Win rate |
|---|---:|---:|---:|
| Maker 1.5 bps per side | 6.93% | 7.36% | 59.46% |
| Taker 4.5 bps per side | 4.53% | 4.96% | 56.76% |
| Maker plus 1 bp slippage per side | 6.13% | 6.56% | 56.76% |

These are sensitivity calculations, not fill simulations. Queue position,
partial fills, latency, liquidation, and path-dependent funding require the
event shadow/replay path.

## Annotation-only challengers

All challengers use only information available at their row. Expanding
volatility thresholds are shifted by one row. GMM scalers and mixtures are fit
inside expanding training folds. Wasserstein state prototypes are training-only
k-medoids over sorted empirical return windows; equal-window city-block distance
is the exact one-dimensional empirical Wasserstein-1 distance.

| Arm | Status | Out-of-sample/causal rows | Notable 30-bar observation |
|---|---|---:|---|
| Expanding volatility terciles | Complete | 258,900 | No state exceeded 50.27% positive paths |
| GMM, three volatility-ordered states | Complete | 129,585 | Highest-vol state mean +2.89 bps |
| Wasserstein, three volatility-ordered states | Complete | 129,570 | Highest-vol state mean +8.31 bps, 55.00% positive, 3,647 rows |
| Filtered HMM | Unavailable | 0 | `hmmlearn` not installed |
| MS-AR | Unavailable | 0 | `statsmodels` not installed |

The Wasserstein high-volatility slice is a research lead, not established
edge: it is a relatively small state, was discovered among multiple arms, and
comes mostly from Binance data. A venue-pure walk-forward replication with
costed Hypervelocity entries would increase confidence. Failure to replicate
would falsify the lead.

## Failure modes and falsifiers

- A venue-native 5m/15m candle disagreement would falsify timestamp alignment.
- Any entry submit while `state_5m` is RANGE, TRANSITION, or UNKNOWN would
  falsify backend policy enforcement.
- Any TUI value without a matching ledger or canonical snapshot field would
  falsify projection integrity.
- A fresh Hyperliquid-only window that reverses the holdout comparison would
  update the no-promotion decision.
- HMM work must use filtered probabilities at decision time; smoothed states
  would invalidate the experiment.
- Challenger states remain non-executable unless a separate, explicit policy
  change is approved and independently validated.

## Remaining empirical gap

The supplied real positions end on 2026-07-24, while the corrected fresh shadow
window starts after this implementation. There is no new overlapping real log
yet. The next comparison must use a newly collected venue-matched shadow window
and real-strategy records covering the same UTC interval. Until then, exact
live-strategy alignment remains unverified.

## Fresh shadow smoke validation

The first corrected launch falsified the CLI startup assumption: the command
passed `enable_funding_refresh=true` even though `nautilus_event_v1` requires
the public WebSocket `activeAssetCtx` stream to be the single funding/mark
authority. The daemon failed closed before a ledger row or order intent. The
CLI now passes `false`, reports the WebSocket authority explicitly, and has a
regression test covering the command boundary.

The next smoke exposed flat-start telemetry amplification: every trade event
could append `execution_evidence_uncertain` before any actionable signal or
order existed. The runtime now emits that annotation only when an entry signal,
pending entry, or open position makes stale evidence operationally relevant;
the ledger bridge suppresses identical contiguous annotations. It does not
turn freshness into a strategy gate: uncertain evidence only prevents the
event simulator from claiming an unsupported fill.

Fresh run `04648f7cfa65` then demonstrated:

- session policy declares authoritative 5m, non-veto 15m, blocked
  RANGE/TRANSITION/UNKNOWN, and `confidence_is_gate=false`;
- real `hyperliquid_ws_l2Book` rows carry five measured bid and ask levels;
- a `TREND_UP` row published the non-model strength score and source;
- the backend created a no-submit post-only long shadow intent while the
  observe-only metalabel probability was `0.0`, empirically confirming that
  the model did not filter the entry; and
- the requested quantity used 70% isolated margin at 40x while all rows kept
  `submitted=false` and `place_attempted=false`.

This is high-confidence evidence for startup wiring and shadow safety in this
run. It is not profitability evidence and does not substitute for the missing
same-window comparison to new real-strategy logs.

The same run also exposed a presentation-boundary defect once the post-only
entry filled incrementally: the backend correctly maintained one position, but
the TUI parser replaced the open journal record for every `enter_long` partial
fill. That would report the last fill timestamp and only one fill fee. The
parser now aggregates successive fills into one size and volume-weighted entry,
preserves the first fill timestamp, and sums entry margin and fees. Focused
Rust regressions cover both an eventual close and an active partial position.
This repair changes only the read-only TUI projection; it does not alter backend
order, position, target, or strategy state.
