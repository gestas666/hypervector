# Short maximum-hold review — 2026-07-30

## 1. Problem restatement

The source-follow short contract exits any surviving position after 24 hours.
This experiment asks whether removing that deadline and holding until the 8%
gross-margin target or isolated liquidation better matches the intended
target-only behavior and improves the recent loss tail.

Success requires exact control parity, higher net PnL and PF, no added
liquidations, and no worse drawdown. The comparison is report-only; runtime and
ML authority remain unchanged.

## 2. Known facts and assumptions

- Window: 2026-04-28 through 2026-07-28.
- Portfolio: $15,000 initial equity, 35% isolated margin, 30x leverage.
- Entry and exit evidence: 60-second maker expiry, public trade-through fills,
  venue fees, authentic funding, and mark/oracle liquidation context.
- Signals, target, same-direction re-entry policy, and occupied-signal behavior
  are identical between arms.
- Only `maximum_hold_seconds` differs.

## 3. Experiment-harness correction

The first v1 run changed only the replay-config default. Source decision rows
carry their own 24-hour deadline, so both arms inherited the same value and
produced identical results. That artifact is invalid as a hold comparison and
is retained as an audit record rather than presented as evidence.

A failing regression test reproduced the defect. V2 copies the candidate
decision frame and clears its per-signal `maximum_hold_seconds`, while leaving
the control frame untouched. The corrected control exactly reproduces the
frozen shared-replay short.

## 4. Corrected exact result

| Policy | Trades | Targets | Liquidations | Time exits | Net PnL | PF | Max DD |
|---|---:|---:|---:|---:|---:|---:|---:|
| 24-hour control | 26 | 23 | 2 | 1 | -$5,413.90 | 0.558 | -60.74% |
| Target or liquidation | 26 | 23 | 3 | 0 | -$6,119.70 | 0.509 | -60.74% |

Removing the deadline lost another $705.80 and added one liquidation. The
affected short entered near $75,119, exited at 24 hours near $76,222 for
-$2,413.56 in the control, and instead liquidated after about 31.2 hours near
$76,659 for -$3,340.27. Subsequent compounding makes the final-equity
difference smaller than the direct trade difference.

## 5. Uncertainties and failure modes

- The interval contains 21 empty-book hours, so the report remains
  conservatively economically inconclusive. No gap overlaps an active
  lifecycle in either arm.
- Public trade-through cannot expose private maker queue cancellations.
- This is one path and only one time exit changed. A different market path can
  favor a longer hold, but this candidate already fails its development test.
- Maximum marked drawdown is unchanged because a later loss cluster dominates
  both equity paths; that does not make the extra liquidation harmless.

## 6. Recommendation and validation decision

Reject target-or-liquidation holding for the source-follow short. Retain the
24-hour maximum hold and do not spend an older validation interval on a
candidate that is already strictly worse in development.

Confidence is high for this local rejection because control parity and the
changed lifecycle are exact. A replay-accounting error or new independent
evidence with multiple predeclared long-duration survivors would update it.

## 7. Evidence identity

- Invalid v1 artifact:
  `data/logs/research/hypervelocity_short_maximum_hold_20260428_20260728_trade_through_v1.json`
- Invalid v1 SHA-256:
  `e49f795dff84cf6cfaacfdee5e794c012f88c189971fc4970d80f45dda4eb7b7`
- Corrected v2 artifact:
  `data/logs/research/hypervelocity_short_maximum_hold_20260428_20260728_trade_through_v2.json`
- Corrected v2 SHA-256:
  `7364f10c16d721148541b8a551a96ac1de768f326c2920d485dc55491dc24c68`
