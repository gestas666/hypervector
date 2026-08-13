# v25 ignored-provider-exit scorecard

**Observed through:** 2026-08-08 19:54:39 UTC  
**Live run:** `bidirectional-live-1786182011216`  
**Profile:** `multi_asset_bidirectional_complete_portfolio_canary_v25`  
**Profile fingerprint:** `ec7715f671fa369d0a415d8941061eb9a577b232bbd4e06367a7342267ff7ecc`

## Problem restatement

v25 deliberately ignores provider recipe exits and retains venue-native stops,
targets where configured, and maximum-hold exits. The open GOLD and SPCX
lifecycles produced provider exit signals. The required question is whether
those ignored signals support changing the live exit policy without pooling
unfinished paths with resolved trades or allowing research output to mutate
execution.

Success means one immutable, report-only scorecard that:

1. separates resolved and provisional-open lifecycles;
2. preserves exact strategy, symbol, exit mode, reason, and signal count;
3. labels missing historical exit-mode metadata rather than inventing it;
4. has no execution, promotion, sizing, or gating authority; and
5. is validated against the real v25 prefix and the full non-network suite.

## Known facts and analysis

- Four compatible-profile trades are resolved. None contains an observed
  ignored-provider-exit lifecycle, so resolved exit-policy evidence is zero.
- Four lifecycles remain open. GOLD and SPCX contain observed ignored provider
  exits; BTC and HYPE do not.
- GOLD's gross directional continuation from its first ignored `ha_flip` is
  `+5.9843 bps` at the frozen boundary, across 18 ignored signals.
- SPCX's gross directional continuation from its first ignored
  `alignment_loss` is `+316.9120 bps`, across 19 ignored signals.
- The provisional mean is `+161.4481 bps`, but removing the largest path leaves
  `+5.9843 bps`. This sensitivity prevents SPCX from being presented as a
  repeatable portfolio-level estimate.
- The 13.82-minute prefix delta adds no fill, close, fee, funding, win, loss, or
  realized net-PnL change. The delta therefore recommends no research-journal
  revision.
- The scorecard's five-resolved-lifecycle threshold is a research-maturity
  label. It cannot abort, gate, pause, or alter an execution trial.

The evidence contradicts an immediate universal `honor` policy: both observed
open paths moved favorably after their first ignored exit, and SPCX did so
materially. It does not prove that universal `ignore` is profitable because
neither lifecycle has resolved and counterfactual fills, fees, funding, and
slippage remain unknown.

## Implementation and validation

- Added
  `src/hypervector/research/cohort_ignored_provider_exit_scorecard.py`.
- Integrated root audit field
  `ignored_provider_exit_policy_scorecard` into
  `src/hypervector/research/cohort_live_audit.py`.
- Added test-first coverage in
  `tests/test_cohort_ignored_provider_exit_scorecard.py` and the live-audit
  integration test.
- The first integration test failed with the expected missing report key.
- The expanded focused run then exposed historical exit records without an
  `exit_mode`. A second test failed on that case before the implementation was
  changed to publish explicit
  `unavailable_in_recorded_readiness_metrics` provenance.
- Focused exit/audit suite: `20 passed`.
- Full non-network suite: `4,124 passed`, four deselected, 27 known warnings.
- Ruff lint and format checks passed for the changed files.
- No network call occurs in tests.

Immutable audit:

`data/logs/research/bidirectional_cohort/v25_live_prefix_ignored_exit_scorecard_20260808T195443Z.json`

SHA-256:

`e6f315bcd3c86f62a17ed9160cd9b9a6bd2293ed36d4b24b3650aa5e4a806cec`

Immutable delta:

`data/logs/research/bidirectional_cohort/v25_live_prefix_delta_20260808T194042Z_20260808T195443Z.json`

SHA-256:

`5040257d32d69f2c98984bfd3aaac9cab4d66e30112c05eb47417318f8250931`

## Recommendation and trade-offs

| Option | Evidence | Trade-off | Recommendation |
|---|---|---|---|
| Keep current `ignore` policy | Two favorable provisional paths; zero resolved ignored-exit paths | Can give back open profit before stop or timer | Retain for the active v25 lifecycles |
| Honor every provider exit | Contradicted by both current provisional paths, especially SPCX | Earlier exits may reduce adverse tails but can cut strong continuation | Do not apply universally |
| Strategy/exit-mode-specific policy | Mechanistically plausible | Requires resolved, venue-costed observations by exact mode | Continue measuring |
| Do nothing to telemetry | Avoids code growth | Leaves exit decisions unauditable | Rejected; report-only scorecard is now present |

No live process, profile, route, order, position, stop, target, allocation,
exit policy, or strategy changed in this increment.

## Uncertainty and falsifiers

Confidence is high that the scorecard separates lifecycle states and has no
execution authority, because the contract and test coverage are direct.
Confidence is medium that universal immediate exits would have harmed these two
open paths, because the gross path evidence is causal but not a simulated venue
fill. Confidence is low for long-run exit-policy profitability.

The recommendation would be updated by resolved lifecycles showing that exact
provider exits improve net PnL after counterfactual fees, funding, and slippage;
by repeated adverse continuation after ignored signals; or by strategy/exit
mode groups with materially different results. A pooled open/closed statistic,
missing provenance presented as observed, changed immutable hash, report-only
side effect, profile drift, missing venue stop, or runtime fault would falsify
the corresponding technical claim.
