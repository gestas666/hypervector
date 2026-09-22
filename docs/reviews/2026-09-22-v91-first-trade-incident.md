# V91 first trade: loss attribution and authorized pause

The user authorized pausing V91 after its first trade lost $44.950445 net.
Run `bidirectional-live-1790073983560` accepted transition drain request
`56999fac5da145bd8d21c408ca568353` and completed it at
2026-09-22 15:43:20.365457 UTC. The backend exited normally, code 0, at
15:43:39 UTC. Its supervisor persisted
`hold_reason = clean_exit_operator_stop_or_bounded_run` and
`session_active = false`. Do not clear this hold or restart live trading under
the earlier deployment approval; the latest user instruction is to pause.

An independent unsigned venue check at 15:44:06.949917 UTC confirmed zero open
positions, zero open orders and account equity $4,825.33307049. At 15:46:16 UTC,
the backend remained absent and the durable supervisor hold remained present.
`pause_verification.json` records these checks; `evidence_sha256.json` hashes the
captured evidence and production policy source used for the replay.

## Verified trade

High confidence: native acknowledgements, fills, the checkpoint reflection and
the policy replay agree. Revised venue evidence or a mismatched lifecycle would
invalidate this attribution. All dollar amounts below are USD/USDC accounting
values used by the backend.

| Item | Recorded value |
|---|---:|
| Instrument and direction | xyz:SNDK long |
| Entry time | 2026-09-22 14:00:20.110 UTC |
| Entry quantity / price | 1.026 / 1,895.50 |
| Entry notional | $1,944.783 |
| Leverage | 8x isolated |
| Initial native stop trigger, venue rounded | 1,853.70 |
| Gross loss at that trigger | $42.8868 |
| Exit time / price | 15:02:18.872 UTC / 1,852.00 |
| Exit reason | protective_stop |
| Gross realized loss | $44.631 |
| Total fees | $0.332201 |
| Funding credit | $0.012756 |
| Net realized loss | $44.950445 |
| Loss as fraction of initial V91 equity | 0.92295% |
| Initial / final V91 equity | $4,870.28351549 / $4,825.33307049 |

Entry order 553037759337 filled in two pieces at the same price. Stop order
553037832440 was accepted at 14:00:23.284907 UTC, approximately 3.175 seconds
after the venue entry fill. Subsequent reconciliation observed the full-size,
reduce-only stop resting until the final pre-exit poll. The exit consumed this
same stop order. The $1.7442 loss beyond the rounded trigger was a small portion
of the total: most of the loss was permitted by position size and stop distance.
Hyperliquid documents a stop-market order as a trigger for market execution;
the trigger does not fix the eventual fill price
([venue documentation](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/order-types)).

## Why the adaptive exit did nothing

The best recorded executable quote was 1,899.10, approximately $3.6936 gross
profit, or 18.99235 basis points of entry. This is a sampled quote maximum,
not a guarantee of a realizable historical fill or an exhaustive tick maximum.

At the first observation, the activation requirement was 123.08098 basis
points, approximately $23.93658 gross profit: twice the trailing minute ATR.
Across the full trade, activation never fell below its 60-basis-point minimum.
The position therefore never armed a profit floor.

Replaying all 247 persisted observations through the deployed
`advance_adaptive_exit` produced zero state mismatches, zero armed observations
and zero adaptive exit decisions. No degraded-input events appeared in the
captured current-run ledger. This supports the narrow conclusion that the
recorded behavior followed the implemented policy. It does not validate the
policy's economic value or prove the entire system is bug-free.

The material design limitation is that the overlay manages profit retention
only after activation. It has no independent failed-entry exit before activation.
Existing provider exits, native stops and deadlines remain the available exits.
Canonical alignment was positive throughout the recorded observations, and
opposing book evidence reached at most two consecutive confirmations. Merely
removing the profit activation requirement would not demonstrate a successful
regime/book deterioration exit on this trade.

The Ridge model's initial continuation prediction was negative, but its authority
was explicitly report-only. Prior chronological validation did not establish
profitable model authority. Selecting that forecast after observing this loss
would not validate using the model to close future trades.

## Crypto participation

High confidence for the recorded V91 window: there were no eligible crypto entry
signals and no router-withheld entry intents. The first armed cohort observation
was 11:01:23 UTC. The comparison below uses completed minute bars from 11:02 to
15:40 UTC, excluding startup warmup candles. It is not an assessment of the
broader bull market or a counterfactual trading return.

| Asset | Price change | Maximum advance from window start | Recorded entry requirement absent |
|---|---:|---:|---|
| BTC | +0.493% | +0.602% | Downside liquidity sweep; absent in all five hourly evaluations |
| ETH | +0.040% | +0.813% | Fresh hourly SMA crossover; absent in 280 of 281 evaluations; the remaining evaluation was an exit condition |
| SOL | +0.394% | +1.044% | Fresh completed-hour Donchian entry; absent in all 19 provider evaluations |
| HYPE | -0.274% | +0.773% | Full compression/breakout/pullback conjunction; zero eligible entries in 281 evaluations |

Repeated evaluations are not independent opportunities. The crypto entry
definitions were retained in V91. They do not create a general instruction to
participate in an ongoing uptrend. The adaptive exit cannot improve entry
participation when no entry is emitted.

## Required next comparison

Medium confidence: entry participation and explicit loss exposure are the next
components to evaluate, given the mechanisms above. One loss cannot establish
that a replacement would improve future returns. Freeze candidate definitions
before reading their held-out outcomes, include the losing SNDK trade as a
diagnostic case rather than a tuning target, and report all tested variants.

| Option | Purpose | Main trade-off | Verification |
|---|---|---|---|
| Retain V91 unchanged as offline baseline | Preserve a reproducible comparison | Retains sparse setups and pre-activation stop exposure | Same data, costs, capital and entry clocks |
| Simple trend-participation baseline | Measure whether additional entry opportunity has economic value | More exposure, turnover and whipsaw | Chronological unseen periods across rising, falling and ranging markets; net PnL, drawdown, turnover and time exposed |
| Explicit stop-risk sizing proposal | Make the dollar loss permitted at entry visible and configurable | Reduced size also reduces upside; gaps can exceed planned risk | Per-asset quantity/precision tests, stop-distance extremes, concurrent exposure, fees and adverse-fill sensitivity |
| Failed-entry exit candidate | Test earlier exit when the entry premise fails | May cut recoveries and add re-entry costs | Causal executable-price replay including lost winners, incremental net PnL and stress fills |
| ML continuation candidate | Compare conditional hold value with simple rules | Overfit, overlapping labels and drift | Purged chronological folds, train-only transforms, prospective forecasts and cost-aware stopping outcomes |

No replacement strategy, smaller live size, new entry gate or model authority was
deployed during this incident. The authorized mutation was the run-bound drain.

## Evidence and limits

Frozen evidence directory:
`data/logs/research/bidirectional_cohort/v91_first_trade_20260922/`.

- `native_trade_events.json`: native order acknowledgements, fills and close.
- `adaptive_observations.json` and `policy_replay.json`: all 247 observations and
  exact production state-transition comparison.
- `checkpoint_snapshot.json`: account, trade reflection and routing evidence.
- `recorded_candles.json`, `crypto_provider_evaluations.json` and
  `crypto_participation.json`: observed market paths and absent entry conditions.
- `authorized_drain_request.json` and `completed_drain.json`: authorized control
  and backend-confirmed completion.
- `venue_preflight.json` and `post_drain_venue_preflight.json`: independent,
  unsigned venue checks before and after the pause.

The generic health command reports the stopped backend as
`backend_process_absent`. The checkpoint can retain a stale-running-heartbeat
label after all eight assets become STOPPED. These labels are monitoring
limitations; use the completed drain, normal process exit, durable supervisor
hold and fresh venue reconciliation together to establish this intentional
pause. Do not restart trading just to make the generic health indicator green.
