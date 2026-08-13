# Short liquidation-cooldown review — 2026-07-30

## 1. Problem restatement

The recent source-follow short replay contained two liquidations. The second
losing entry arrived less than 48 hours after the first liquidation. This
experiment asks whether consuming same-direction signals for 48 or 72 hours
after a full liquidation removes a repeated tail loss without filtering normal
target continuations.

Success requires a lower liquidation count, positive net PnL, PF above one,
lower drawdown, and survival on an older interval that did not select the
cooldown. The rule is report-only; runtime and ML authority remain unchanged.

## 2. Known facts and assumptions

- The rule activates only after a full liquidation and only for the same side.
- An opposite-direction signal remains eligible after the ordinary cooldown.
- A blocked signal is consumed; it cannot become a delayed stale maker order.
- Both comparisons use source-follow shorts, $15,000 initial equity, 35%
  allocation, 20x leverage, an 8% gross margin target, 60-second maker expiry,
  a 24-hour maximum hold, authentic funding, and public trade-through fills.
- The recent 91-day interval selected the candidate. The preceding interval is
  approximately 272 days and did not select the duration.

## 3. Exact replay results

### Development: 2026-04-28 through 2026-07-28

| Policy | Trades | Targets | Liquidations | Time exits | Net PnL | PF | Max DD |
|---|---:|---:|---:|---:|---:|---:|---:|
| 20x control | 26 | 23 | 2 | 1 | -$2,081.17 | 0.80 | -48.26% |
| 48h after liquidation | 25 | 23 | 1 | 1 | +$2,670.15 | 1.40 | -29.23% |
| 72h after liquidation | 25 | 23 | 1 | 1 | +$2,670.15 | 1.40 | -29.23% |

The recent candidate removed one losing June entry and appeared profitable.
Because that loss motivated the rule, this was selection evidence only.

### Independent older interval: 2025-07-30 07:00 UTC through 2026-04-28

| Policy | Trades | Targets | Liquidations | Time exits | Net PnL | PF | Max DD |
|---|---:|---:|---:|---:|---:|---:|---:|
| 20x control | 64 | 55 | 3 | 6 | -$2,629.82 | 0.90 | -46.50% |
| 48h after liquidation | 62 | 53 | 3 | 6 | -$3,246.63 | 0.87 | -47.85% |
| 72h after liquidation | 62 | 53 | 3 | 6 | -$3,246.63 | 0.87 | -47.85% |

The cooldown removed two target winners and no liquidations. Relative to the
control it lost another $616.81 and worsened maximum drawdown by 1.35 points.
The 72-hour variant also consumed two additional signals that had expired in
the control, so it produced the same trades and economics as 48 hours.

## 4. Uncertainties, risks, and failure modes

- The older archive contains 386 empty-book hours and one approximately
  18.5-hour price-context gap. None overlaps an active lifecycle, but the replay
  conservatively remains economically inconclusive.
- The validation interval did not select cooldown duration, but it did use the
  same source-revision logic. A future source revision would require a new
  frozen comparison.
- Public trade-through cannot reveal private queue position or cancellations.
- The cooldown primitive remains available in research code with a zero
  default. Its existence does not authorize runtime use.

The hypothesis is falsified on the available independent interval: it did not
reduce the loss tail and instead discarded profitable continuations.

## 5. Validation result

Reject both 48-hour and 72-hour post-liquidation cooldowns for runtime or
shadow promotion. Do not retune the duration on the validation interval. A new
prospective window could update this conclusion only if a predeclared duration
repeatedly removes liquidations without suppressing target winners.

Confidence is high for rejection under this source-following 20x contract. It
would be reduced by a replay-accounting defect, changed source logic, or venue
evidence showing that an active lifecycle crossed an unobserved gap.

## 6. Trade-off matrix

| Option | Benefit | Main risk | Decision |
|---|---|---|---|
| 48h cooldown | Helped selected 91-day path | Removed two older winners | reject |
| 72h cooldown | Same selected result | Extra consumed signals, no benefit | reject |
| Zero cooldown | Preserves continuations | Tail remains unresolved | retain control |
| Retune duration | Could fit observed clusters | Further selection bias | do not pursue |

## 7. Evidence identity

- Development artifact:
  `data/logs/research/hypervelocity_short_liquidation_cooldown_20260428_20260728_trade_through_v1.json`
- Development SHA-256:
  `81834e6fa04636f6b0bf5d22a974f24ef6aeacf762dc115e6f27f8931bddea56`
- Independent artifact:
  `data/logs/research/hypervelocity_short_liquidation_cooldown_validation_20250730T07_20260428_trade_through_v1.json`
- Independent SHA-256:
  `4e974a1004ea3b0f3977394054303f5a049f500054d078616f7ba9ec1c0649cf`
