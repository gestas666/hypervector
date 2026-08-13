# V25 live-prefix path-dependent exit review

## Problem restatement

The ignored-provider-exit scorecard previously compared only the current or
final price with the first ignored provider exit. That endpoint is insufficient
for exit research: it cannot distinguish a smooth continuation from a path that
made a large favorable move and subsequently surrendered most of it. The
required improvement was a report-only, point-in-time path diagnostic that
preserves resolved/open separation and cannot change live execution.

## Known facts and provenance

- Active run: `bidirectional-live-1786182011216`.
- Profile: `multi_asset_bidirectional_complete_portfolio_canary_v25`.
- First new prefix:
  `data/logs/research/bidirectional_cohort/v25_live_prefix_20260808T202339Z.json`,
  SHA-256 `559c80907f95c79d8dfeafb60ac98bf6458007bb292bfa696640b672021f7456`.
- Delta from the prior 20:03:56 UTC prefix:
  `data/logs/research/bidirectional_cohort/v25_live_prefix_delta_20260808T200356Z_20260808T202339Z.json`,
  SHA-256 `f68789b70b8d475b21a36cadedc5ae36083c55b658a9481c469820949481ac84`.
- Path-dependent destination audit:
  `data/logs/research/bidirectional_cohort/v25_live_prefix_ignored_exit_trajectory_20260808T202827Z.json`,
  SHA-256 `57501abe6ab9f65bcaaf908564949edf24858f0829473a68445e7f29e585e73f`.
- The 19.88-minute delta added 149 cohort rows, zero fills, zero closes,
  zero fees, zero funding, and zero resolved PnL.
- The ten added metric-value gaps are the already diagnosed five HIP-3
  pressure fields on two old-run evaluations. No technical-gap identity was
  added or removed.

## Implementation and validation

`ignored_provider_exit_policy_scorecard_v2` now retains, separately for
resolved and provisional lifecycles:

- completed-path coverage;
- maximum favorable excursion;
- maximum adverse excursion;
- peak giveback from favorable excursion to the current/final mark;
- portfolio and exact provider/exit-mode statistics;
- leave-largest sensitivity for every distribution.

Unavailable completed-candle paths remain counted as unavailable. Their
current mark is not transformed into invented excursion values. The command
contract remains `execution_authority=none`, report-only, and unable to honor,
ignore, route, resize, close, or promote an exit.

The red-green scorecard tests passed, the focused audit/exit suite passed 33
tests, Ruff lint and formatting passed, and the full non-network suite passed
4,131 tests with four deselected and 27 known warnings.

## Findings

No resolved lifecycle has yet observed an ignored provider exit, so the policy
decision remains `insufficient_resolved_exit_evidence`.

The two provisional open paths are materially different:

| Symbol / exit mode | Current continuation | MFE | MAE | Peak giveback |
|---|---:|---:|---:|---:|
| `xyz:GOLD` / `ha_flip` | +5.2938 bps | 17.0322 bps | 3.4525 bps | 11.7384 bps |
| `xyz:SPCX` / `alignment_loss` | +193.7519 bps | 566.2361 bps | 27.0351 bps | 372.4842 bps |

SPCX therefore remains favorable relative to the first ignored exit, but the
prior endpoint-only interpretation concealed a 372.48-bps surrender from its
best completed-candle path. Its already frozen open-profit-lock observer says
all three predeclared policies triggered before the current boundary. The most
patient `a60_floor15_trail30` path activated after 60 bps and recorded a
139.37 trigger reference, while the audit mark was 135.74. This is a
counterfactual reference, not a submitted order or fill.

The newest HYPE paths do not justify weakening entry gates. One newly matured
Hulk 15-minute path cleared the cost hurdle, but the cumulative
`expansion_trigger_not_present` means remain negative after the 13-bps hurdle:
`-2.66`, `-1.77`, `-3.14`, and `-11.52 bps` at 5/15/30/60 minutes. Removing
the largest close remains negative at every horizon. HYPE
`5m_not_breakout` is also negative at every horizon across 128/42/21/10
independent resolutions. A single positive addition does not reverse those
distributions.

## Uncertainties and failure modes

Confidence is high for path arithmetic, source-run isolation, resolved/open
separation, and zero execution authority. Economic confidence is low because
both trajectory examples remain open and only one is large enough to motivate
a provider-specific challenger.

The conclusions would be updated or falsified by:

- an SPCX close whose actual venue-costed result contradicts the recorded
  lifecycle path;
- a counterfactual trigger that cannot be reproduced from the exact prior
  completed bars;
- changed or missing immutable hashes;
- a path admitting candles unavailable by its audit cutoff;
- counterfactual fee, funding, or slippage values presented as actual;
- execution authority or a live strategy mutation appearing in the report;
- profile drift, duplicate orders, a missing stop, or a runtime fault.

## Recommendation and trade-offs

| Option | Evidence | Trade-off | Decision |
|---|---|---|---|
| Honor all provider exits immediately | No resolved ignored-exit sample; SPCX remains +193.75 bps after the first signal | Could prevent giveback but may discard profitable continuations | Do not promote |
| Apply one pooled portfolio profit lock | Prior normalized all-live policies remain negative and contract-mixed | Simpler, but hides provider-specific behavior | Do not promote |
| Preserve v25 and resolve the exact SPCX lifecycle | Maintains current protected ownership and produces actual fees/funding/exit evidence | Delays policy activation | Recommended |
| After SPCX closes, compare its actual result with the three frozen trigger paths | Causal trigger references and full open path already exist | Still a two-lifecycle provider sample | Next hypothesis |

The next evidence-driven question is narrowly scoped: does SPCX Swing/HA
benefit from a provider-specific profit-protection overlay after measured MFE?
Resolve the current lifecycle first, then compare actual venue-costed PnL with
the three predeclared trigger paths and their causal fill assumptions. Do not
generalize to GOLD, HYPE, or the portfolio from this open observation.

The delta itself reports `journal_revision_recommended=false`; no append-only
economic research-journal revision was fabricated from provisional marks.
