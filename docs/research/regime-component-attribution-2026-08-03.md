# Regime component attribution — 2026-08-03

## Decision

The current canonical detector has strong evidence as a **range/movement
classifier**, but not as a standalone **direction predictor**. Keep all new
components observe-only. Use RANGE and strength telemetry to describe market
structure and setup maturity; do not add an execution gate or directional
weight from this report.

Confidence is medium-high for the range/movement conclusion because it is
consistent across four assets, three chronological segments, and four forward
horizons. Confidence is low for any tradable edge claim because this report
does not simulate orders, fills, fees, funding, slippage, or shared-portfolio
contention.

## Frozen evidence

- Artifact: `data/logs/research/regime_component_attribution_20260803_v2.json`
- SHA-256: `ab896e85bdd4f96f33d57aec1e780171f6f8ed9361fb840c982f04552b9cf7a3`
- Gap sensitivity: `data/logs/research/regime_component_attribution_20260803_gapq240.json`
- Gap sensitivity SHA-256: `fda651536db4c55ae9f39719c3d9da2ca35c124f95e63f487ed7f259b2acb2e1`
- Assets: BTC, ETH, SOL, HYPE
- Venue: Hyperliquid 1-minute candles
- Coverage: 2025-07-28 through 2026-07-28
- Horizons: 5, 15, 30, and 60 minutes
- Chronology: development, validation, and explicitly non-pristine
  pseudo-holdout
- Effective non-overlapping paths: 664,925 overall; 111,050 in pseudo-holdout
- Authority: report-only; no execution, model, threshold, fill, or PnL authority

Future labels begin one minute after the completed decision bar. A label path
cannot cross its segment boundary. Decisions or future paths touching an
`hl_gap_fill` row are excluded and counted. Gap-filled bars can still influence
later rolling features until their causal memory decays; this remains a stated
limitation rather than a hidden assumption.

## Principal results

Canonical non-RANGE observations had greater mean absolute future close movement
than RANGE observations in all 48 asset × segment × horizon cells. The uplift
ranged from 13.49% to 51.53%, with a cell median of 34.37%.

Magnitude-oriented daily Spearman results against future absolute excursion:

| Component | Positive cells | Median daily IC | Disposition | Intended use |
|---|---:|---:|---|---|
| Canonical RANGE vs non-RANGE | 48/48 | n/a | PROCEED | Range/movement annotation |
| Regime strength score | 48/48 | 0.178 | PROCEED | Movement-intensity cue |
| EMA 21/55 absolute gap | 48/48 | 0.188 | PROCEED | Movement-intensity cue |
| Trend-slope absolute magnitude | 48/48 | 0.152 | PROCEED | Movement-intensity cue |
| SMA 100/200 absolute gap | 48/48 | 0.123 | PROCEED | Slow structure cue |
| Absolute HARSI displacement | 47/48 | 0.050 | REVISE | Secondary intensity cue |
| Self-Aware TQI | 47/48 | 0.032 | REVISE | Secondary quality cue |
| Trend R-squared | 43/48 | 0.021 | REVISE | Secondary persistence cue |
| Choppiness 14 | 32/48 | 0.008 | STOP | Do not weight; mixed sign |

`PROCEED` means continue collecting and displaying the component as an
observe-only hypothesis. It does not authorize an entry filter, position-size
change, model feature, or live threshold. `REVISE` means the formulation is
plausible but weak or inconsistent. `STOP` means do not spend execution
authority on the current formulation.

## Gap-memory sensitivity

The predeclared sensitivity excluded the 240 completed minutes after every
`hl_gap_fill` row in addition to decisions and label paths directly touching a
gap. This removed 215,808 horizon-specific observations and left 647,681
greedily non-overlapping paths.

The primary conclusion survived:

- non-RANGE mean absolute movement exceeded RANGE in 48/48 cells;
- uplift remained 12.48% to 50.00%, with a 32.84% cell median;
- regime strength, absolute EMA gap, absolute SMA gap, and absolute trend
  slope remained positive in 48/48 daily-IC cells;
- absolute HARSI displacement became positive in 48/48 cells;
- Choppiness remained mixed at 32/48 cells.

This raises confidence that the measured range/movement separation is not an
artifact of short-lived rolling-feature contamination around reconstructed
minutes. It does not eliminate every possible gap effect because recursive
EMAs have a decaying memory beyond 240 minutes.

## Directional falsification

The canonical long/short structural direction did not survive pseudo-holdout:

| Segment | Positive direction cells | Median signed return | Range across cells |
|---|---:|---:|---:|
| Development | 19/32 | +0.053 bps | -3.227 to +1.270 bps |
| Validation | 16/32 | +0.027 bps | -3.742 to +1.281 bps |
| Pseudo-holdout | 0/32 | -0.576 bps | -3.910 to -0.030 bps |

These are pre-cost price-path labels, not trade returns. Even the favorable
development cells are generally too small to support an after-cost directional
claim. Exact EMA, SMA, Cipher A, HARSI, and MTF categorical states and their
onsets are retained in the artifact, but their signed outcomes are inconsistent
across assets and segments.

Disposition by directional function:

| Function | Disposition | Reason |
|---|---|---|
| Canonical 5m direction | STOP as standalone predictor | 0/32 positive pseudo-holdout cells |
| EMA/SMA direction signs | REVISE | Magnitudes explain movement; signs do not generalize |
| Cipher A/HARSI direction | REVISE | Mixed state and onset outcomes |
| Completed 5m/15m bias | REVISE | Exact categories are inconsistent by asset |
| L2 OPI | CONTINUE LIVE OBSERVE | Not available in the one-year candle artifact |

## Operational contract

Screen 9 may use these results to explain why RANGE and strength widgets are
useful visual diagnostics. It must continue to say:

- backend-authored;
- not a win probability;
- weights observe-only;
- live forward resolved and independent counts;
- missing or censored evidence is not a resolved sample.

No runtime classifier threshold, provider scope, entry, exit, stop, leverage,
or allocation changed as a result of this report.

## What would update the decision

The range conclusion weakens if fresh live forward evidence repeatedly shows
equal or larger movement during canonical RANGE, or if the 48/48 separation
disappears after quarantining the full rolling-memory window following every
gap-fill minute.

The directional conclusion improves only if independently collected live
completed-bar outcomes show stable same-sign directional association across
assets and market conditions, with non-overlapping counts and a magnitude that
plausibly clears measured live costs. A strategy replay with authentic fills,
fees, funding, latency, slippage, stops, and shared capital is then required;
this attribution cannot substitute for it.
