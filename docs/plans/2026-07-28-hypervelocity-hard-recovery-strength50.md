# Hypervelocity Hard-Recovery Strength-50 Follow-up

## Problem restatement

Test whether the causal regime-strength association found in the fixed
lifecycle audit survives a stateful, execution-identical Hyperliquid replay.
This is a report-only falsification trial. It does not change the faithful
runtime strategy, TUI, 8% gross target, 70% isolated allocation, 40x leverage,
one-position policy, or observe-only ML authority.

## Frozen candidates

Both candidates use hard 5m BBWP range precedence and a six-bar 1m recovery
delay. Only the declared entry mask differs:

| Candidate | Minimum causal regime-strength percentile |
|---|---:|
| `hard_bbwp_recovery6_control` | none |
| `hard_bbwp_recovery6_strength50` | 50 |

Entries with missing strength are ineligible only in the strength candidate.
All exits and holds remain identical. RANGE does not force an open position to
close.

## Frozen execution and evidence

- Window: 2026-04-28 through 2026-07-27 UTC.
- Initial equity: $10,000.
- Position: 70% isolated margin at 40x BTC leverage.
- Exit: 8% gross return on margin; maker target, taker liquidation.
- Entry: maker-only, trade-through fill, 300-second TTL.
- Re-entry: 300-second cooldown plus regime reset.
- Evidence: 2,160 checksum-verified Hyperliquid hourly bundles, authentic
  mark/oracle prices, and official funding.
- Regimes: completed-bar 1m/5m/15m features from the faithful config checksum
  `801d2c7af3c1211c13fea49dda673fdb8ed40ff0909692e9cebad070c0e3246f`.

## Measurements and success criteria

The immutable report must retain submissions, fills, targets, liquidations,
partial liquidations, fees, funding, final equity, maximum drawdown, three
chronological 30-day slices, full lifecycles, decision hashes, and creator
entry attribution.

The trial is complete regardless of performance. Runtime promotion would
require higher full-window final equity, lower drawdown, no losing
chronological slice, and no material loss of creator-source fidelity. These
criteria are deliberately strict because the strength threshold was selected
from development evidence.

## Risks and falsifiers

- Fixed-lifecycle screening may not survive portfolio path substitution.
- The threshold removes many directional bars and already reduces exact
  creator eligibility, so it may be an overfilter.
- Creator screenshots are selected evidence and do not expose a complete loss
  distribution.
- Public trade-through cannot reconstruct private queue rank or hidden depth.

A stateful result that reverses the fixed-lifecycle advantage falsifies the
strength association. A survivor remains provisional until a sealed later
window and fresh shadow execution agree.

## Measured result and decision

The replay completed across all 2,160 checksum-verified bundles, 127,814
authentic mark/oracle observations, and 2,160 official funding rows. A direct
object comparison confirmed that the control replay is byte-equivalent after
canonical JSON serialization to the prior factorial's hard/recovery result.

| Candidate | Fills | Targets | Full liq. | Partial liq. | Final equity | Max drawdown |
|---|---:|---:|---:|---:|---:|---:|
| Control | 408 | 369 | 39 | 15 | $2,466.13 | -97.83% |
| Strength 50 | 322 | 287 | 35 | 25 | $244.62 | -99.37% |

The strength candidate reduced full liquidations by four but increased
partial liquidations by ten and lost 97.55% of initial equity. Its first two
independent 30-day slices grew by 1.071x and 1.589x, but the latest slice
collapsed to 0.0144x with 17 full liquidations and -99.32% drawdown. The
control's slice growth multiples were 0.465x, 0.362x, and 1.463x. This is a
regime-dependent path substitution, not a stable risk improvement.

Source fidelity also worsened. Executable creator-direction matches fell from
17/35 to 14/35 and no-candidate rows rose from 14 to 19. Only 198 resolved
signal identities were shared; the candidate created 124 candidate-only paths
and removed 210 control paths.

Strength 50 fails every promotion criterion and is rejected. Runtime, TUI,
fixed target, allocation, leverage, and ML authority remain unchanged.
Confidence is high for the exact replay rejection and medium for external
generalization because the threshold was selected and tested on development
evidence. A later sealed, venue-matched window with improved equity, drawdown,
every chronological slice, and creator eligibility would falsify the broader
rejection.

Artifact:
`data/logs/research/hypervelocity_hard_recovery_strength50_20260728.json`,
SHA-256
`1b6ad570f187efe1d5c02b9038956dbc5babdc9385e55ab179ad23cc5e19602a`.
