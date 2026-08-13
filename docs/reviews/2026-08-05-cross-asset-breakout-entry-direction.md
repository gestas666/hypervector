# Cross-Asset Breakout Entry-Direction Review

**Evaluated:** 2026-08-05 EDT  
**Execution authority:** none; report-only comparison  
**Question:** Does using the actual completed 5m breakout direction transfer
better than the current completed 1h SMA10/SMA30 side?

## Frozen comparison

Both arms use the same shared directional breakout onsets. The control chooses
side from the completed hourly SMA relation. The challenger chooses long for
the authoritative 5m `BK_UPWARD` structure and short for `BK_DOWNWARD`.
Everything else remains fixed: next-minute adverse entry, 80 bps protective
stop, fixed eight-hour hold, 4.5 bps fee per side, 2 bps slippage per side,
hourly Hyperliquid funding, and one position per coin.

The one-year venue window is `2025-07-28..2026-07-28`. Development ends on
May 28, followed by a one-day purge. The final 60-day block beginning May 29
was already opened by earlier HYPE research and is descriptive rather than a
new sealed holdout. No parameter was tuned in this comparison.

## Results

| Asset | Shared onsets | Development control / breakout net bps | Development breakout PF | Final-60d control / breakout net bps | Final-60d breakout PF |
|---|---:|---:|---:|---:|---:|
| BTC | 1,433 | -7,042 / -8,633 | 0.742 | +1,065 / -1,774 | 0.719 |
| ETH | 1,546 | -7,549 / -4,805 | 0.894 | -1,594 / -4,540 | 0.537 |
| SOL | 1,637 | -8,937 / -9,303 | 0.819 | -3,596 / -4,930 | 0.531 |
| HYPE | 2,029 | -7,626 / -14,910 | 0.781 | -1,795 / -4,365 | 0.698 |

The actual-breakout-side arm was negative in all eight asset/period cells. It
improved ETH development relative to the hourly-side control but remained
negative, then degraded sharply in the final 60 days. It underperformed the
control in every final-60-day asset cell.

## Decision

Do not create or arm an always-follow-the-breakout provider with the existing
80 bps stop and eight-hour exit. The shared idea remains portable as a market
event, but this exact entry-side/lifecycle combination does not show a
transferable after-cost edge.

Keep actual 5m breakout side and its aligned/opposed relation to the hourly SMA
side in live telemetry. That supports prospective attribution without changing
orders. A future challenger must change a distinct mechanism, such as causal
breakout failure/reclaim, volatility-normalized lifecycle geometry, or
order-flow confirmation; another post-hoc threshold filter on this already-open
window would not provide independent evidence.

## Artifact integrity and correction record

The first v1 artifacts used the composite 1m-confirmed `breakout_direction`
field and therefore compared only a filtered subset of 5m breakouts. They are
retained as invalidated audit evidence and must not support a strategy claim.
V2 uses the authoritative 5m regime `structural_direction`, which is derived
from the completed 5m breakout high/low clearance direction.

Validated V2 SHA-256 identities:

- BTC: `6684e7b59be8694eee0d84bc81c2176c1e6118b8ea38bae1449e0dda7a464083`
- ETH: `90c0c5fa288c55ca2b423eb67bc15dcc985b74a9fc2e5ad1d04de1a6a1ca4175`
- SOL: `b7293ecad0bac7c6d25351114d17884ee6e575b5a1a40c70056ce0908804ed3c`
- HYPE: `16f168acd93d3d87a992e6c420bea9fe14433a78693b899fce71f0c47050d475`

## Confidence, risks, and falsifiers

**Mechanical confidence: high.** The V2 contract uses complete, equal-length
venue bars, exact hourly funding, a shared-onset intersection, and a
test-covered source-field distinction. A hash mismatch, timestamp gap,
different onset mask, or non-causal 5m direction would invalidate it.

**Economic confidence: medium that this exact challenger should not execute.**
All final-60-day cells and all development cells were negative, but the recent
block was already inspected and one-minute bars cannot reproduce private queue
state or actual IOC latency. Prospectively frozen live/shadow outcomes with
positive after-cost results across multiple assets and market states would
update this assessment.

