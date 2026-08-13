# Cross-Asset Impulse Development Review

**Decision:** Reject this exact impulse-propagation contract. No strategy replay,
runtime adapter, TUI strategy tile, or live authority is justified by the
development evidence.

## Problem and frozen contract

The experiment asked whether a completed five-minute BTC or ETH impulse predicts
a delayed catch-up move in ETH, SOL, or HYPE. The selectable family contained
five directed leader/follower pairs and three forward horizons, for 15 primary
cells. Forty-five leader-only, follower-momentum, and one-day-lag placebo cells
were nonselectable controls.

The signal was frozen before outcomes were loaded: a 10,080-minute trailing
standardization window, leader impulse z-score at least 2.5, follower catch-up
gap at least 0.75, 30-minute cooldown, and 5/15/30-minute horizons. The artifact
reports gross forward returns and compares them with 13 bps nominal and 20 bps
stressed round-trip costs. It has `execution_authority=none` and does not claim
an executable fill model or portfolio PnL.

The scoring window is `2025-07-28T00:00:00Z` through
`2026-01-28T00:00:00Z`, split into three fixed chronological folds. This is a
development result, not a sealed holdout: the project previously inspected the
same broad historical period in other research families.

## Source correction before outcomes

The original four 365-day cache files began at the scoring boundary and lacked
the required warmup. The run stopped before computing outcomes. The amendment
was recorded in the plan before the experiment continued and did not change a
signal parameter.

For each symbol, an immutable Hyperliquid one-minute 0xArchive candle bundle was
added for `2025-07-20T23:55:00Z` through `2025-07-28T00:00:00Z`. A common
0xArchive candle outage on July 27 was verified against public trades. Immutable
public-trade bundles for `2025-07-27T00:00:00Z` through
`2025-07-27T12:03:00Z` reconstructed 526 missing candle minutes per symbol.
Native candles take precedence. Verified minutes with no public trades are
explicit `hl_gap_fill` carry bars and are excluded from signal validity.

| Symbol | Selected rows | Native rows | Reconstructed warmup | Explicit gap rows |
|---|---:|---:|---:|---:|
| BTC | 275,045 | 274,937 | 526 | 108 |
| ETH | 275,045 | 274,940 | 526 | 105 |
| SOL | 275,045 | 274,893 | 526 | 152 |
| HYPE | 275,045 | 274,923 | 526 | 122 |

## Primary-cell evidence

Numbers below are gross basis points. `Base` and `Delay` contain the three fold
means. `N` contains resolved events per fold. No cell was eligible for replay.

| Leader→follower | Horizon | Base fold means | Delay fold means | N by fold | Long mean | Short mean |
|---|---:|---:|---:|---:|---:|---:|
| BTC→ETH | 5m | -2.651 / 1.531 / 0.105 | -0.826 / 0.326 / -0.470 | 379 / 336 / 315 | -0.239 | -0.657 |
| BTC→ETH | 15m | -2.053 / 3.506 / 4.012 | -0.214 / 3.744 / 3.015 | 379 / 336 / 315 | 2.384 | 0.816 |
| BTC→ETH | 30m | -2.493 / 5.543 / 7.764 | -1.585 / 6.168 / 6.961 | 379 / 335 / 315 | 4.283 | 2.201 |
| BTC→SOL | 5m | -3.396 / 7.471 / 2.312 | -0.329 / 0.857 / 2.308 | 394 / 406 / 356 | 5.226 | -0.756 |
| BTC→SOL | 15m | 0.830 / 5.226 / 5.987 | 2.414 / -0.432 / 4.921 | 394 / 406 / 356 | 6.160 | 1.847 |
| BTC→SOL | 30m | -1.895 / 10.173 / 5.055 | -0.488 / 4.252 / 5.659 | 394 / 405 / 356 | 6.642 | 2.400 |
| BTC→HYPE | 5m | -1.348 / -1.477 / 2.329 | -0.292 / -2.076 / 1.130 | 435 / 479 / 446 | 2.126 | -2.375 |
| BTC→HYPE | 15m | -3.401 / -4.997 / 3.621 | 0.262 / -4.081 / 1.502 | 435 / 479 / 446 | 2.573 | -5.664 |
| BTC→HYPE | 30m | -6.073 / -2.930 / 1.532 | -5.066 / -3.361 / 0.314 | 435 / 478 / 446 | 5.752 | -10.259 |
| ETH→SOL | 5m | -2.408 / -1.909 / 0.912 | -0.478 / -2.942 / 2.605 | 331 / 334 / 360 | -0.621 | -1.517 |
| ETH→SOL | 15m | -1.542 / -7.467 / 5.906 | -0.952 / -10.998 / 5.434 | 331 / 334 / 360 | 3.480 | -4.987 |
| ETH→SOL | 30m | -2.653 / 4.516 / 4.680 | -2.258 / 2.678 / 4.750 | 331 / 333 / 360 | 2.230 | 2.282 |
| ETH→HYPE | 5m | 2.800 / -0.163 / -1.019 | 1.418 / -2.183 / -2.124 | 386 / 440 / 464 | 2.709 | -1.808 |
| ETH→HYPE | 15m | -1.182 / -5.785 / 5.630 | -2.197 / -9.561 / 4.979 | 386 / 440 / 464 | 7.285 | -7.657 |
| ETH→HYPE | 30m | -6.919 / -1.792 / 2.891 | -7.604 / -3.418 / 0.781 | 386 / 439 / 464 | 4.450 | -7.537 |

## Strongest cell and contradiction

BTC→SOL at 15 minutes ranked first. Its immediate fold means were positive and
it dominated both the leader-only and lagged-placebo controls in every fold.
That is evidence of a small conditional association, but not an executable
edge:

- immediate fold means were only `0.830 / 5.226 / 5.987` bps;
- delayed fold means were `2.414 / -0.432 / 4.921` bps;
- immediate medians were `0.000 / -2.735 / 1.942` bps;
- immediate trimmed means were `-0.435 / -1.178 / 0.691` bps;
- only `39.1% / 36.2% / 37.9%` of events exceeded 13 bps gross;
- long and short means were 6.160 and 1.847 bps, respectively;
- cadence was 6.28 resolved events per calendar day, with a 541-minute p90
  interarrival time.

The delayed entry reversal in fold two and negative robust-location estimates
contradict a stable, tradable propagation mechanism. Applying realistic fees,
slippage, funding, liquidation, or shared-portfolio constraints would not repair
gross means already below cost.

## Portfolio and integrity checks

The sidecar contains 168,798 event rows. Across the primary family there were
5,861 nominal pair events, 5,446 unique follower/timestamp events, 415
same-follower collisions, 1,737 cross-pair overlap timestamps, and 1,623
same-leader clusters over 184 calendar days. These counts prevent nominal event
volume from being mistaken for independent portfolio opportunities.

Independent validation reconciled 15 primary cells, 45 controls, all event
rows, 20 source files, and 11 declared generator modules:

- JSON SHA-256:
  `5721bf0a11b7616068b2fd5d563cd7415ccd464062ef1cf73a68088faafbd5e4`
- Parquet SHA-256:
  `6978a03ca0a29fd0f66fc7e19520feeb80531c0134b46d49ef4e87397b5c72d7`

The validator module cannot require its current bytes to equal the historical
self-hash without making validation self-invalidating. Its historical snapshot
must be well formed; every non-self output-generating module is compared exactly
with current bytes. This is a disclosed integrity limitation, not economic
evidence.

## Recommendation, uncertainty, and falsifier

Do not tune nearby z-score, gap, cooldown, or horizon thresholds on this window.
That would convert a preregistered family rejection into post-hoc selection.
Move to a causally distinct hypothesis while the disarmed observer continues to
measure real setup and decision cadence.

**Confidence: high for rejecting this exact contract on this development
window.** Event counts are large and no primary cell approaches nominal cost.
Confidence is lower about all possible cross-asset information because this
screen tests one standardized close-to-close formulation and candle-resolution
execution only.

The rejection would be updated by either a corrected material causality/data
defect or a separately frozen mechanism that produces stable, delayed,
directionally symmetric gross returns above measured costs across chronological
folds. A post-hoc threshold variant or one favorable pair/fold would not
falsify it.
