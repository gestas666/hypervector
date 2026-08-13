# HYPE breakout cross-asset transfer review

**Evaluated:** 2026-08-05 EDT  
**Execution authority:** report-only; no route, position, process, active profile,
or staged profile changed

## Question and frozen contract

Test whether the exact `hype_breakout_onset_bidirectional_v1` mechanism transfers
from HYPE to BTC, ETH, or SOL without tuning it to each coin.

The comparison preserves the completed five-minute `BREAKOUT` onset, completed
one-hour SMA10/SMA30 direction, next-minute adverse entry, 80 bps protective
stop, fixed eight-hour exit, 4.5 bps fee per side, 2 bps slippage per side,
hourly Hyperliquid funding, and one-position-per-coin accounting. The adaptive
HYPE eight-to-24-hour extension was measured separately and did not influence
the fixed-eight-hour transfer decision.

Each asset has 525,600 contiguous Hyperliquid one-minute bars from
`2025-07-28T00:00:00Z` through `2026-07-27T23:59:00Z`, with zero gaps and zero
duplicate timestamps, plus 8,760 matched hourly funding observations. The
chronological comparison uses a development block ending May 28, a one-day
purge, and the final 60 days beginning May 29 as a descriptive holdout. That
holdout was already opened by prior HYPE work and is not a newly sealed test.

## Frozen fixed-eight-hour results

| Asset | Development trades | Development PF | Development net bps | Final-60d trades | Final-60d PF | Final-60d net bps | Final-60d max DD bps |
|---|---:|---:|---:|---:|---:|---:|---:|
| BTC | 669 | 0.7873 | -7,068.02 | 121 | 1.2211 | +1,064.83 | 703.78 |
| ETH | 797 | 0.8426 | -7,679.54 | 154 | 0.8220 | -1,593.88 | 2,797.99 |
| SOL | 854 | 0.8336 | -8,948.62 | 162 | 0.6344 | -3,596.19 | 4,241.21 |
| HYPE control | 1,009 | 0.8917 | -7,565.78 | 214 | 0.8750 | -1,795.12 | 3,203.62 |

The HYPE row differs slightly from the earlier development count of 1,011
because this transfer comparison gives the adaptive-extension variant a full
24-hour purge and applies the same split to its fixed-eight-hour control.

## Final-holdout direction attribution

| Asset | Long trades | Long PF | Long net bps | Short trades | Short PF | Short net bps |
|---|---:|---:|---:|---:|---:|---:|
| BTC | 58 | 0.9270 | -165.56 | 63 | 1.4831 | +1,230.40 |
| ETH | 77 | 0.8400 | -735.05 | 77 | 0.8029 | -858.83 |
| SOL | 81 | 0.6877 | -1,458.99 | 81 | 0.5862 | -2,137.19 |
| HYPE control | 109 | 0.9855 | -106.91 | 105 | 0.7587 | -1,688.22 |

BTC's recent aggregate improvement comes entirely from shorts. The same BTC
short mechanism was negative in the preceding development block: 339 trades,
PF 0.7777, and -3,930.95 bps. This is evidence of regime sensitivity, not a
stable transferable edge.

## Decisions

- **BTC:** keep the exact short side as a report-only prospective observer. Do
  not grant execution authority. It is the only cross-asset result worth
  collecting forward, but its development/holdout sign reversal prevents a
  promotion claim.
- **ETH:** reject the unchanged transfer for execution; both directions are
  negative in development and holdout.
- **SOL:** reject the unchanged transfer for execution; both directions are
  materially negative in development and holdout.
- **HYPE:** the historical control remains negative. Preserve the current live
  HYPE contract only under its separate sparse live evidence decision; six
  favorable live closes do not rewrite the historical result.

The collector already preserves BTC, ETH, SOL, and HYPE symbol attribution,
and the inactive observer configuration measures all four while retaining
HYPE-only execution authority. The active canary observes this provider only
on HYPE. Expanding observation on the next safe restart would not require or
justify expanding live order authority.

## Uncertainty and falsifiers

**Confidence: high** that the frozen historical comparison was applied to
complete, equal-length local inputs and includes configured fees, fixed
slippage, and funding. File-backed evidence and causal source tests support
that claim. A hash mismatch, cadence gap, timestamp duplication, or different
entry/exit contract would invalidate it.

**Confidence: medium** that ETH and SOL should not receive this exact rule as
an execution route. A prospectively frozen, materially changed mechanism may
perform differently, but that is a new hypothesis rather than a rescue of this
one.

**Confidence: low** that BTC shorts have a durable recent edge. Positive
after-cost prospective BTC-short outcomes across multiple market regimes would
increase confidence; a new forward block reverting to PF at or below one or
negative net bps would falsify the challenger.

One-minute OHLC cannot reproduce intrabar path ordering, private queue state,
IOC latency, rate-limit failures, or realized live slippage. Therefore these
results can reject weak transfers and prioritize observers, but cannot certify
live profitability.
