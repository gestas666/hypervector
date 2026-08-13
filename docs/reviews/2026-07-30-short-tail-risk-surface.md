# Short-tail risk surface review — 2026-07-30

## 1. Problem restatement

The source-follow short produced 23 targets but remained unprofitable because
two liquidations and one 24-hour exit dominated the winners. This report tests
whether bounded allocation or leverage changes repair that tail without
changing signals, the 8% gross margin target, entry timing, or strategy
authority.

Success requires positive net PnL and profit factor above one, materially lower
drawdown, exact reproduction of the frozen control, and later survival on an
independent interval. The experiment is report-only; ML remains observe-only.

## 2. Known facts and assumptions

- The interval is 2026-04-28 through 2026-07-28 with $15,000 initial equity.
- All 33 source-follow short signals remain eligible.
- The maker entry lifetime is 60 seconds, the target is 8% gross margin, and
  the maximum hold is 24 hours.
- Hyperliquid maker/taker fees, authentic funding, mark/oracle context,
  isolated liquidation, and public trade-through fills are replayed.
- The two recent liquidations motivated this experiment, so this interval is
  development evidence rather than an untouched holdout.

## 3. Exact replay results

The replay processed 12,202,083 canonical L2 snapshots and 36,931,672
deduplicated public trades. Its 35%/30x control exactly reproduced the frozen
shared-portfolio short control after canonical JSON normalization.

| Allocation / leverage | Trades | Targets | Liquidations | Time exits | Net PnL | PF | Max DD |
|---|---:|---:|---:|---:|---:|---:|---:|
| 35% / 30x control | 26 | 23 | 2 | 1 | -$5,413.90 | 0.56 | -60.74% |
| 25% / 30x | 26 | 23 | 2 | 1 | -$3,622.29 | 0.59 | -46.53% |
| 35% / 25x | 26 | 23 | 2 | 1 | -$3,170.44 | 0.71 | -52.09% |
| 35% / 20x | 26 | 23 | 2 | 1 | -$2,081.17 | 0.80 | -48.26% |

Every challenger improved final equity relative to the control, but none
crossed PF 1 or removed either liquidation. At 20x, lower leverage delayed the
two liquidation exits to about 90 minutes and 15.5 hours after entry; it did
not make those positions recover to target.

## 4. Uncertainties and failure modes

- Twenty-one empty-book hours make the full-window report conservatively
  non-conclusive. The 20x candidate had two active gap windows and is therefore
  additionally unsuitable for promotion from this artifact.
- Lower leverage changes target price distance, queue-volume requirements,
  hold duration, fees, and funding exposure. It is not merely a smaller loss
  multiplier.
- Testing further nearby leverage values after seeing this surface would
  increase selection bias without addressing the repeated tail path.
- Public trade-through cannot reveal private queue position or cancellations
  ahead of the simulated order.

The claim that allocation/leverage alone repairs the recent short is falsified
by every predeclared candidate remaining negative with the same two
liquidations.

## 5. Validation and next experiment

The next bounded hypothesis is a same-direction cooldown applied only after a
liquidation. Ordinary target continuations remain untouched. A signal arriving
inside the cooldown is consumed so it cannot become a stale delayed order.

The current window can only develop this rule. Any positive result must retain
exact controls and then survive older exact evidence without changing the
cooldown, leverage, allocation, target, or signal definition.

## 6. Recommendation and trade-offs

| Option | Benefit | Main risk | Decision |
|---|---|---|---|
| Keep 35%/30x | Matches current control | PF 0.56 and -60.74% DD | reject for promotion |
| Reduce allocation to 25% | Best tested DD | PF remains 0.59 | reject as solution |
| Reduce leverage to 25x | Some tail reduction | PF remains 0.71 | reject as solution |
| Reduce leverage to 20x | Least-negative PnL/PF | two liquidations and gap overlap | retain only as cooldown control |
| Do nothing to runtime | Preserves the live comparison | no immediate tail fix | current safe action |

Confidence is high that these four variants do not solve the recent short
under the tested replay. This would be updated by a discovered replay-accounting
error or materially different venue evidence.

## 7. Evidence identity

- Artifact:
  `data/logs/research/hypervelocity_short_risk_surface_20260428_20260728_trade_through_v1.json`
- SHA-256:
  `557fc376765e9a4d5eea61677eae856bebd9af3f382ee518d7198d011e83400c`
