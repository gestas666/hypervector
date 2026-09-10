# Daily portfolio concentration on the corrected complete account

SNDK accounts for **64.51% of daily portfolio variance under current sizing and
72.86% under equal caps** in the full-fee historical scenarios. At least two
assets lose marked cash on **26 of 48 days** under both allocations. Equal caps
therefore do not produce equal contributions to the observed portfolio variance.
Confidence is high in these reconciled measurements; they do not establish
future diversification or justify a live allocation change by themselves.

This updates the September 7 interaction study, which used 176 legacy trades
and five HYPE trades. The corrected account has 177 trades and six HYPE trades.
The new study retains the same original July 21–September 7 window, seven assets,
and six fixed cost/allocation cases (0/1, 4/5, 8/9). The six scenarios reuse the
same history and trade identities; they are not independent samples.

| Full-fee measure | Current sizing | Equal caps |
| --- | ---: | ---: |
| Net equity change | -$33.44 | +$92.00 |
| Positive marked days | 25/48 | 24/48 |
| Days with at least two losing assets | 26/48 | 26/48 |
| Maximum losing assets within a day | 4 | 4 |
| Worst marked day, August 7 UTC | -$69.94 | -$149.88 |
| SNDK contribution to daily variance | 64.51% | 72.86% |
| SNDK contribution in earlier 28 days | 70.74% | 73.36% |
| SNDK contribution in later 20 days | 54.16% | 71.24% |

| Asset | Current-sizing variance contribution | Equal-cap variance contribution | Current-sizing net cash | Equal-cap net cash |
| --- | ---: | ---: | ---: | ---: |
| BTC | 3.14% | 0.29% | $4.11 | $1.76 |
| ETH | 0.22% | 0.30% | -$8.99 | -$19.26 |
| SOL | 1.44% | 0.72% | $2.75 | $5.90 |
| HYPE | 8.07% | 0.45% | -$99.25 | -$42.52 |
| SPCX | 11.72% | 14.15% | $1.71 | $3.55 |
| SNDK | 64.51% | 72.86% | $82.81 | $178.05 |
| Brent | 10.90% | 11.24% | -$16.58 | -$35.48 |

The full-fee current-sizing pairwise correlations range from -0.1234 to +0.3328.
The largest are BTC/HYPE (+0.3328), BTC/Brent (+0.3041), and SOL/HYPE (+0.3026).
All 21 pairs, all seven contributions and full/earlier/later views are retained
for every scenario. Nominal-cost cases have 23 joint-loss days; adverse-cost
cases have 25; full-fee cases have 26. The updated adverse-cost count differs
from the legacy study's 23-day count. Both the account basis and exact daily
boundary accounting changed, so the difference is not attributed solely to HYPE.

These correlations use daily strategy PnL, including inactive days, fees,
funding and marked open exposure. They are not underlying-market return
correlations. A joint-loss day does not prove that the losing positions were
open at the same instant. Variance contribution is covariance(asset daily PnL,
portfolio daily PnL) divided by portfolio daily variance; contributions sum to
one before rounding and can be negative. Constant or insufficient samples remain
undefined. Raw negative counts and counts below the existing $1e-8 reconciliation
tolerance are both retained; they happen to agree for these joint-loss results.

## Validation and scope

Frozen research source is `1e85d79a578f40028913ebf0de3d4945fb2f481f`.
All 5,655 archived Git blobs/modes match; 1,946 implementation/dependency files
are pinned. The source archive is 33,857,193 bytes, SHA256
`708279253263594b27cf23fb93ff0d891aa8019fbf9cf7913398092b8b25228e`.
The 100-test qualification passes in the worktree and archive. New modules have
146/146 statements and 52/52 branches covered. Controls include boundary funding,
entry/exit ownership, terminal-open marks, negative equity, inactive assets,
missing/duplicate inputs, sealed windows, and offsetting variance contributions.

The operator authenticates 2,354 input references. It proves common market-source
routes before extracting the exact 49 daily mark events once from original case 8.
The initial snapshot, each original before-actions boundary and actual terminal
snapshot are retained. Funding at an interior boundary belongs to the preceding
day; entries/exits at that clock belong to the following day. Every cumulative
component reconciles to the original account. All 288 scenario-day records agree
with the qualified daily reports and all full/28/20-day asset cash components
agree with the earlier period attribution.

An independent implementation starts from raw closed trades and actual funding
settlements, using Decimal arithmetic. All **16,128 cash comparisons** pass;
the maximum difference is **$5.703e-13**. DuckDB independently checks **1,548
statistics** on those reconciled daily observations. Maximum residuals are
$1.1e-13, 1e-12 dollars squared and 5e-16 for unitless statistics; count differences
are zero. The separate checker explicitly requires the observed flat terminal
accounts; terminal-open behavior is qualified by the synthetic module tests.

The six-member operator archive is independently verified. Operators pass Ruff
and the file/function-size, annotation and public-docstring checks. Initial
source-record assembly used the wrong system interpreter and failed before
publication; it was completed with the existing Python 3.13 research environment.
No dependency was installed or changed. No live client or order was invoked.

## Decision and next action

Retain this corrected concentration evidence for the complete allocation review.
The equal-cap proposal remains inactive: its larger historical net result comes
with substantially more SNDK variance concentration and a larger worst marked day.
Keeping current sizing retains its HYPE loss contribution; replacing it solely
because of this explored sample could overfit. No asset, weight, leverage,
strategy, entry or exit rule changes here.

The highest-value next decision is to combine the complete original 48-case
cost/source/clock contrasts with this concentration evidence and the retained
SNDK follow-through trace. A subsequent sizing experiment should compare economic
concentration and exposure, rather than treating equal margin caps as proof of
diversification. No new variant is selected by this diagnostic.

Both prospective outcome seals remain intact. Changed source hashes, boundary
phases, cash identities or independent residuals would invalidate these results.
The 48 explored days and smaller slices do not prove stable future performance.
The full matrix report and fresh deployment/account/TUI acceptance remain pending.

Evidence root:
`data/logs/research/bidirectional_cohort/v89_daily_asset_interactions_20260910_v1/`.
Key files: `source.json`, `source.tar.gz`, `archive_tests.log`, `archive_coverage.json`,
`daily_boundary_events.jsonl`, `case_00/01/04/05/08/09.json`, `diagnostic.json`,
`independent_verified.json`, `independent_case_00/01/04/05/08/09.json`,
`operators.tar.gz` and `operators_verified.json`.
