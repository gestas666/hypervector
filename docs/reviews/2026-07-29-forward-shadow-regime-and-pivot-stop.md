# Forward Shadow Regime and Pivot-Stop Review

Date: 2026-07-29

## Problem restatement

This checkpoint evaluates two bounded questions without changing execution:

1. Did the first completed July 29 shadow trade behave coherently under live
   Hyperliquid order-book and trade evidence, and how did its entry regime
   compare with the pinned strict and legacy source detectors?
2. Can a causally confirmed 1-minute pivot stop reduce the liquidation tail of
   the profitable legacy Recipe C source-follow short candidate without
   destroying its target winners?

Success requires internally reconciled quantities, fees, target and
liquidation boundaries, zero live submissions, causal source annotations, and
an economic improvement before any stateful stop replay is justified.

## Fresh shadow lifecycle

Run `51f44ff36f6b` completed one simulated long:

| Field | Observed value |
|---|---:|
| Entry intent | 2026-07-29 00:10:03 UTC |
| Full entry fill | 2026-07-29 00:11:38 UTC |
| Entry | $64,029.00 |
| Quantity | 4.37301 BTC |
| Entry fills | 3 |
| Entry fees | $41.9999 |
| Isolated liquidation boundary | $63,228.2323 |
| Target | $64,158.00 |
| Target distance | 20.1471 bps |
| Target fills | 38 |
| Target completion | 2026-07-29 00:45:57 UTC |
| Gross trade PnL | $564.1183 |
| Exit fees | $42.0845 |
| Funding | $0.00 |
| Net realized PnL | $480.0338 |
| Final equity | $10,480.0338 |

The 20.1471-bps target is slightly above the ideal 20 bps because the target
was tick-aligned. Gross margin return was 8.0588%; fees reduced the portfolio
gain to 4.8003%. Every ledger row remained `submitted=false`, and no
`place_attempted=true` row exists for the run.

### Restart integrity correction

The final target arithmetic persisted `position_qty=-4.44e-16 BTC` rather than
exact zero. The running engine already treated that value as flat, but the
resume bridge compared persisted quantities with exact zero and would have
reconstructed a tiny short plus a migrated target after restart. Two failing
regression tests reproduced both the loader and event-runtime failure.

Resume now normalizes absolute quantities at or below `1e-12 BTC` to an
authoritative flat state before profile checks or runtime restoration. It also
clears the stale average, unrealized residue, and active targets. Applying the
new loader to the actual ledger returns quantity 0, average 0, unrealized PnL
0, zero targets, and unchanged $10,480.0338 equity. Material positions above
the tolerance remain untouched. The explicit fill engine now applies the same
shared tolerance to close/flip arithmetic, preventing future aggregate target
fills from emitting the residue in the first place. This was a continuity fix,
not a strategy or execution-policy change.

## Source-regime comparison

The live ledger and event archive were imported idempotently into the research
database. Strict and legacy Hypertrader labels were regenerated from the same
continuous Hyperliquid public-trade history through 00:40 UTC, with full prior
history retained for warmup and state continuity.

All 46 completed shadow 5-minute bars then had both source labels:

- strict versus legacy disagreements: 6;
- backend versus strict disagreements: 25;
- backend versus legacy disagreements: 28;
- unlabeled completed bars at comparison time: 0.

At the exact entry decision, the completed 00:05-00:10 bar was `TREND_UP` in
the backend but `TRANSITION / TR_BOTTOM_FORMING` with confidence 0.65 in both
source detectors. Both source detectors changed to
`TREND_UP / TU_WEAK_CHOPPY` at 00:15. The backend therefore led the two source
detectors by five minutes on this event.

That lead is not evidence of a bad entry: the trade completed its target about
35 minutes after the intent. It is also not proof that faster confirmation is
generally superior. The source detectors are challengers rather than outcome
ground truth, and one winner cannot estimate a liquidation tail. Historical
blanket source-agreement and minimum-age gates already worsened geometric
equity, so no delay or agreement gate is justified by this observation.

## Confirmed-pivot stop result

The frozen stop used the latest strict 1-minute swing high published only after
two right-side bars completed. The level was frozen at entry, with no buffer.
The screen preserved the source-follow leader's exact fills and lifecycles.

| Window | Fills | Stop hits | Target regrets | Liquidations avoided | Original trade PnL | Counterfactual trade PnL |
|---|---:|---:|---:|---:|---:|---:|
| Development | 30 | 11 | 10 | 1 | $15,219.35 | -$2,903.89 |
| Fresh Jul 27 | 1 | 1 | 1 | 0 | $476.87 | -$289.44 |

The development delta was -$18,123.24. The stop sacrificed ten eventual
targets to avoid the sole liquidation and also stopped the only fresh target.
It fails both predeclared qualification conditions. No buffer tuning or
stateful replay is warranted, and the candidate is rejected.

## Recommendation and trade-offs

| Option | Benefit | Failure mode | Decision |
|---|---|---|---|
| Add confirmed-pivot stop | Avoided one development liquidation | Destroyed ten targets and the fresh winner | Reject |
| Delay backend until source agreement | Closer source label timing | Prior broad replay failed; current early entry won | Reject now |
| Keep canonical shadow runtime | Preserves live forward collection | One completed trade is sparse | Continue |
| Keep legacy source-follow short leader | Best cross-window research economics | Short-only and only two later fills before this run | Continue as annotation |

The next useful evidence is a frozen sequence of completed shadow trades with
entry-time strict/legacy labels and realized outcomes. The causal hypothesis is
that backend/source timing disagreement may identify entry timing, not an
automatic veto. It would be falsified as useful telemetry if disagreement
shows no stable relationship to target latency, adverse excursion,
liquidations, or net expectancy as the forward sample grows.

Confidence is high that this shadow lifecycle and stop-screen accounting are
internally reconciled. Confidence is high that the exact unbuffered 2/2 pivot
stop should be rejected on the inspected candidate. Confidence is low about
general entry-timing conclusions because only one July 29 shadow trade has
resolved.

## Immutable evidence

- strict labels: `d20d1060028081008b742a712aa5371a09984af11788415b909b18f904bfd0a4`;
- strict metadata: `0e965a2b77d90a52bc0831c2dd6b875d2e5278d5617ee887521e3a8848a8075b`;
- legacy labels: `65906a410159654c3a367674861a5588a28ff620b6a22d7c87fd8a2ccd6ffbf2`;
- legacy metadata: `f3d7b9e2aa8fd4f9af86636afe8b9141b91c17b6d7daef5a85bbf60ff4e8e504`;
- pivot-stop screen: `90b651c665d98ebd5748e5da5e8df7caaab5236380895d2528b64ca0b878546e`.
