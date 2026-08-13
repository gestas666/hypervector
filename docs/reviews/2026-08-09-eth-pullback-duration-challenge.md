# ETH pullback exit-duration challenge

## Problem restatement

The latest exact ETH short reached 50.46 bps of favorable excursion but closed
at the 12-hour deadline with a small after-cost loss. The bounded question was
whether a global four-hour or eight-hour maximum hold retains more of that move
without degrading the established fixed-entry ETH cohort.

## Frozen experiment

The comparison reused the exact 282-trade development and 56-trade opened-final
entry cohorts. Only maximum hold changed: 240, 480, or 720 minutes. Every path
retained the 60-bps stop, 4.5-bps fee per side, 2-bps slippage per side, official
funding series, next-open entry semantics, and fixed long/short signal identity.
The command is report-only and has no execution authority.

## Results

| Hold | Development net / PF | Final net / PF | Net excluding largest winner | Decision |
|---|---:|---:|---:|---|
| 4h | -2,322.37 bps / 0.809 | +395.53 bps / 1.213 | -2,793.83 / +88.63 bps | Reject global change |
| 8h | +235.32 bps / 1.017 | -37.72 bps / 0.984 | -520.23 / -330.32 bps | Reject |
| 12h | +1,657.98 bps / 1.111 | +322.33 bps / 1.121 | +487.67 / -346.32 bps | Retain unchanged |

Four hours is the strongest recent-window result and reduces final-window
drawdown, but it reverses the larger development sample to a material loss.
Eight hours is not positive in the opened-final block. Twelve hours is the only
tested duration positive in both partitions, although its final result remains
winner-concentrated.

The resolved live short does not contradict this conclusion by itself. It
closed `-$0.006099` after costs, with 50.46-bps MFE, 23.93-bps MAE, and 45.78
bps of giveback. This establishes an exit-capture question, not a globally
better duration.

## Decision and next experiment

Keep the exact 12-hour exit. Do not install the four-hour, eight-hour, or tested
25/15/10 profit-lock rules. Continue side- and breakout-relation attribution.
The next exit candidate must be state-aware and preregistered, and must beat the
unchanged control in both chronological partitions before receiving prospective
live observation. No entry gate, route, size, stop, order, or runtime changed.

Confidence is high that four and eight hours should not replace the current
control under this evidence, and medium that 12 hours remains the least
contradicted tested duration. A cohort-identity mismatch, altered friction,
changed stop, or a shorter/state-aware exit winning both partitions and later
independent live paths would update the decision.

## Evidence

- Immutable duration artifact:
  `data/logs/research/bidirectional_cohort/eth_pullback_mechanism_duration_20260809T203358Z.json`
- Immutable live audit:
  `data/logs/research/bidirectional_cohort/v25_live_prefix_successor_refresh_20260809T201446Z.json`
- Append-only revision:
  `docs/research-journal/eth-breakout-precompression-pullback-v5.json`

