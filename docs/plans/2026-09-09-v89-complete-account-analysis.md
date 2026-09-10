# Analyze complete historical account evidence

The objective remains the original 48 source/cost/clock/allocation cases and
their independent reproduction. Reporting work is separate from the frozen
`a86bd6f` engine and its waiting first-case operator. It may use explicit
synthetic controls while historical results remain unavailable.

1. Authenticate complete case artifacts and retain the existing independent
   account audit. Enforce the original historical window and both prospective
   outcome seals; do not relabel incomplete or synthetic output as historical.
2. Compute full-path and original earlier/later-period equity changes, daily
   attribution, drawdown, capital use and concurrent exposure from every account
   phase. Avoid closed-trade-only return accounting because open exposure and
   previously paid fees/funding carry across the split.
3. Intermediate daily boundaries use the `before_actions` snapshot: boundary
   marks and funding close the preceding period; boundary orders affect the
   following period. The final boundary includes the account's actual final
   phase. Do not reset equity or force terminal closes.
4. Time-weight capital use using the last account phase at each timestamp.
   Multiple same-time action snapshots and the two exit clocks must not distort
   averages. Preserve nonpositive-equity results and undefined ratios explicitly;
   do not turn poor performance into a trial error or a numeric-zero fallback.
5. Report accepted/rejected entries, closed wins/losses/breakevens, holding time,
   entry frequency and gaps, gross PnL, fees, funding and terminal marked exposure.
   Reconcile closed plus open contribution to whole-account equity change.
6. Preserve all 48 case identities and report source, cost, clock and allocation
   sensitivities, per-asset/strategy/direction contributions, daily concentration
   and original-period robustness. Earlier/later historical segments are not
   newly unseen holdouts. Economic recommendations require the full matrix.

Validation starts with hand-calculated complete synthetic snapshot series for
daily boundaries, same-time actions, both clocks, duration weighting, negative
equity and invalid/missing chronology. Then use complete native synthetic cases
and frozen reproduction before reading actual historical outcomes. Full source
price/native-routing qualifications remain distinct from the accounting oracle.

The existing shared-trade report aggregates closed trades and their exit months.
Its model does not supply the required marked-equity path, carried exposure or
original split attribution, so it is unsuitable as the account-report contract.
Reuse existing account models and validation helpers where their semantics match.

No live configuration, asset, strategy, sizing, leverage, risk, execution or
deployment change is part of this analysis. Changed source identities, omitted
phases, ambiguous boundary attribution, double-counted costs or unreconciled
equity changes invalidate the affected report.

## Path arithmetic qualification, September 9 23:58 UTC

The first component is implemented in the isolated
`/Users/gestas/Prototypes/hypervector-v89-history-analysis-20260909` worktree.
Its 29 focused tests pass in 2.22 seconds, covering all 118 measured statements
in `historical_account_path_metrics.py`. This includes both complete clocks,
all account phases, intermediate and final boundaries, time-weighted capital
use, nonpositive equity and malformed/incomplete evidence. Percentage return
and percentage drawdown are explicitly undefined when the period starts with
nonpositive equity; dollar losses remain reported.

The retained complete two-day synthetic accounts also pass the existing
independent Decimal audit and the new path calculation: 2,885 and 5,765
snapshots for the recorded and late clocks. Daily and original-partition equity
changes reconcile to each full terminal account. The probe reauthenticated 15
source/artifact references before and after evaluation. Its 13,405-byte report
has SHA-256 `96ab37b94f3354c29d343d43f226f924fe032eee98514d84bd6c8819e81a5b0c`
under `data/logs/research/bidirectional_cohort/v89_historical_account_path_metrics_qualification_20260909_v1/`.
The earlier missing-module run failed nine tests as expected; the first
implementation passed all nine before the expanded checks.

This establishes bounded path arithmetic, with high confidence for these
controls. It is not an independently reproduced release or historical economic
result. The authenticated account reader, trade/cost/open-exposure attribution,
full matrix comparison and complete frozen reproduction remain required. The
original producer and the qualified `a86bd6f` replay engine were not changed.
