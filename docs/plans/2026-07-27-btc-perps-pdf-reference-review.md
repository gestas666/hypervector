# BTC Perps PDF Reference Review

Status: research reference only; no runtime or active-config changes authorized.

## Decision summary

The PDF is useful as a hypothesis catalog, not as an authoritative strategy
specification. Its most relevant testable idea is fresh structural entry rather
than chasing an established 5m move. That hypothesis is independently supported
by the current archive diagnosis: signals at least 15 minutes into a 5m regime
had 7 liquidations in 18 fills, including 6 liquidations in 8 late shorts.

Confidence is medium because the association is post-hoc and the late sample is
small. A controlled, point-in-time L2 replay would falsify it if fresh-entry
variants avoid no liquidations, miss enough targets to reduce expectancy, or do
not reproduce across fill assumptions and a later shadow window.

## Internal inconsistencies in the reference

1. The heading calls 15m a `Non-Veto Context`, but the body says it dictates
   direction and strictly vetoes flat or opposed conditions.
2. The surrounding blueprint uses BBWP length 20 and lookback 240, while page 2
   specifies BBWP length 7, lookback 100, and SMA 5.
3. `1.0 bps minimum` is described as both EMA separation and EMA slope angle.
   Those are different measurements.
4. The statement that compression guarantees expansion is not an empirical law.
5. The document is anonymous and supplies no inspectable source calculations or
   backtest. Claims labeled `optimal` remain unverified.

## Differences from current Hypervelocity

| PDF concept | Current implementation | Research implication |
|---|---|---|
| 15m direction veto | 15m is non-veto context | Test aligned/opposed/RANGE slices offline before considering policy |
| 5m 240-bar horizontal wick-to-close zones | 240 bars rank EMA-gap strength; no explicit zone-proximity entry | Add annotation-only structure distance first |
| BBWP compression then breakout | BBWP20/240 participates in classification; strict tactical conjunction is annotation-only | Test recent-compression windows, not an immediate hard gate |
| Actual EMA slope | Signed EMA gap is measured | Keep slope and gap as separate challenger features |
| Range-reclaim close exit | Open positions hold until 8% target | Test as a report-only exit counterfactual |
| Wick/pivot emergency stop | No stop in faithful contract | Sweep explicit stop definitions without changing runtime |
| RSI divergence or PMARP/BBWP profit exit | Fixed 8%-margin target only | Lower priority; it changes the source strategy's exit contract |

## Bounded experiment order

1. Preserve the current faithful shadow config and the saved EMA-only research
   candidate. Do not promote either result from this review.
2. Add point-in-time annotations for 5m regime age, distance to prior 5m
   wick/close structure, 15m relationship, and BBWP compression recency.
3. Replay one hypothesis at a time across touch, one-tick-through, and public
   trade-through fills. Retain trade count, missed targets, avoided
   liquidations, expectancy, maximum drawdown, and long/short results.
4. Test exits separately from entries: target-only control, range-reclaim close,
   and wick/pivot emergency stop. Do not mix entry and exit changes in the same
   attribution trial.
5. Use a later shadow window as confirmation. Treat the 90-day archive as
   exploration because the hypotheses were selected after inspecting it.

## Highest-value first tests

- Fresh-regime/structure-proximity annotation: strongest link to the observed
  late-short failure concentration and least likely to create an opaque gate.
- Range-reclaim and wick-stop counterfactuals: directly test whether the payoff
  asymmetry can be reduced before liquidation.
- 15m context slices: useful challenger, but hard-veto promotion risks
  overfiltering and is unsupported by the PDF's contradictory wording.
- BBWP 7/100/SMA5 versus 20/240: isolated feature-definition comparison only.
  Do not combine it with RSI, clearance, volume, and context in the first trial.

## Evidence boundary

The archive window is April 28 through July 26, 2026 UTC. Historical funding,
authentic venue mark price, queue rank, cancellation state, and depth-aware
liquidation fills remain unavailable. Those limitations can change exact PnL
and liquidation timing. The result should be updated if venue-authentic evidence
or a materially different forward-shadow distribution contradicts it.
