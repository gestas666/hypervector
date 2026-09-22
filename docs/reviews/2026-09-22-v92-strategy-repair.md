# V92 repair: explicit loss sizing, failed strategy hypotheses, and continued pause

## Decision and confidence

Keep V91 paused. The code now supports an explicit estimated dollar stop-loss
budget, with tests through order sizing, protection, persistence and restart.
The replacement entry/exit hypotheses tested here did not establish a durable
advantage. This is a completed engineering repair and research comparison, **not
a claim that profitable trading has been fixed**.

High confidence in the recorded incident and arithmetic, conditional on the
captured venue evidence and simulator assumptions. Medium confidence in the
historical comparisons as mechanism diagnostics; low confidence that any tested
variant will outperform prospectively. Different point-in-time inputs, executable
cost evidence, or an untouched forward sample could update these conclusions.

The 16:26:21 UTC unsigned venue preflight confirmed **flat, zero orders, equity
$4,825.33307049**. The authorized drain remains completed and the supervisor hold
remains `clean_exit_operator_stop_or_bounded_run`, with `session_active=false`.
No live process, live profile, approval, or release binary was replaced.

## What the incident establishes

The [V91 incident review](2026-09-22-v91-first-trade-incident.md) reconciles the
$44.950445 SNDK loss. Its native stop existed and executed. The configured size
allowed approximately $43 gross loss at the trigger. Sampled favorable movement
was only $3.69 gross, so the adaptive profit lock never armed. Replaying all 247
recorded observations reproduced the deployed policy. Correct execution does not
validate the entry or establish that the exit policy improves returns.

The signal close was 1,897.10 versus a prior hourly entry-channel high of 1,793.70
and ATR 21.69156: 4.7668 ATR beyond the channel. That motivated a frozen
maximum-one-ATR entry extension hypothesis. Its historical results below do not
support deploying it solely because it would have avoided this particular loss.

## Implemented correction and concrete proposal

`stop_risk_budget` is an optional typed provider execution contract. It sizes
quantity from the bound stop, an explicit cost allowance and the modeled entry
fill interval, then caps it by the existing notional/margin envelope. Structural
stop-clamp turning points are included; looking only at an adverse endpoint was
insufficient for shorts. The actual adapter still performs venue lot rounding.

The engine durably emits `entry_stop_risk_sizing` before submitting an order.
The budget survives configuration staging and bound-plan ledger recovery. The
TUI's staged configuration label exposes the estimated allowance. Legacy payloads
omit an absent budget, preserving V91's original fingerprint and behavior.

The separate [proposal profile](../../configs/multi_asset_v92_risk_control_proposal.toml)
uses **$10 estimated stop loss per position including 20 bps cost allowance**.
It retains the V91 entry/exit rules because the replacements failed this screen.
It has no transition approval, and is not selected by the supervisor. Fingerprint:
`669fe6e3bfae1b08fa204f92fe6177a3803511538421e33cc988f1be9123a0f3`.

For the recorded SNDK setup, modeled notional becomes $372.13 and venue-rounded
quantity 0.196 instead of 1.026. Assuming identical observed entry/exit prices and
linear fee/funding scaling, the loss would be approximately **$8.59**. This is a
sizing counterfactual, not an executable historical fill claim or a profit claim.
Eight simultaneous positions imply $80 of nominal modeled allowances (about
1.66% of the last observed equity), before overruns or accumulated losses.

This is **not a hard loss guarantee**. Market gaps, stop execution slippage,
rounding, cumulative funding and fills outside the modeled interval can exceed
it. An IOC limit bounds adverse entry execution, not every favorable price; the
symmetric modeled interval is a sizing assumption. Existing maximum notional
remains an upper envelope. Read-only preflight cannot know a future structural
stop and therefore does not project the final reduced entry quantity.

## Frozen economic comparisons

The [plan](../plans/2026-09-22-v92-strategy-repair.md) froze four comparisons:
hourly Donchian 20/10; the same with a maximum-one-ATR extension; persistent
hourly EMA21/55 trend participation; and its long-only version. Stops use ATR20x2
with existing clamps, next-open execution and a 24-hour maximum hold. Persistent
rules can re-enter at the next eligible hourly decision while flat.

A matched-entry overlay exits after 30 minutes if the completed close is at least
0.5 initial stop risk adverse and the best completed close stayed below 0.25
initial risk favorable. Native exits and gap censoring take precedence. The
overlay omits additional entries made possible by freed capital; it is not a
complete alternative portfolio simulation.

All 96 completed symbol/candidate/cost cells are retained. Values below sum
independent $500 notional sleeves; they are **not shared-portfolio returns**.
The recent screen has seven assets over July 19–September 19 and TSLA over
July 30–September 20. The year screen covers four crypto assets, July 28, 2025–
July 27, 2026. Measured/adverse scenarios include fees, slippage and recorded
funding from the existing V90 cost contract.

| Recent eight-asset comparison | Measured net | Adverse net | Adverse with early-failure overlay |
|---|---:|---:|---:|
| Donchian baseline | $381.12 | $176.56 | $68.69 |
| Donchian, extension bounded | $221.64 | $45.95 | -$69.69 |
| Persistent trend, both directions | -$466.38 | -$896.18 | -$971.40 |
| Persistent trend, long only | $330.50 | $109.90 | $12.69 |

| One-year four-crypto comparison | Measured net | Adverse net | Adverse with early-failure overlay |
|---|---:|---:|---:|
| Donchian baseline | -$672.25 | -$1,183.93 | -$1,137.13 |
| Donchian, extension bounded | -$845.32 | -$1,302.92 | -$1,213.62 |
| Persistent trend, both directions | -$1,114.88 | -$2,050.43 | -$2,243.98 |
| Persistent trend, long only | -$995.89 | -$1,430.22 | -$1,495.73 |

The bounded rule lowered recent SNDK adverse net from $121.34 to -$21.32.
Earlier loss cutting also removed recovered winners. These outcomes reject
promoting these particular changes as demonstrated improvements. They do not
prove that no trend or exit policy could work. ML remains report-only: this
repair supplies no new evidence overturning V91's failed executable-value tests.

Historical blocks are descriptive entry-time groups, not purged folds; exits
can cross block boundaries. Data were previously examined, so none of these
results is a newly sealed holdout. The one-year check removes synthetic
`hl_gap_fill` minutes, requires 15 native minutes per retained bar, resets
indicators across gaps and censors open positions at the first subsequent quote.
The recent screen reuses stitched inputs. OHLC cannot establish tick ordering or
historical order-book fills. Per-symbol drawdowns cannot be added.

## Review, verification and reproducibility

Review corrected three defects in the initial implementation before staging:
structural short sizing missed interior clamp maxima; nested budget dictionaries
serialized as invalid TOML; and integer/float budget construction changed identity
across load/save. Regression tests exercise each. Unreachable clamp boundaries
and nonfinite modeled prices now fail or skip explicitly as appropriate.

The focused causal/sizing/recovery/staging suite passed 58 tests. The sizing
module has 99% statement coverage; its uncovered branch is defensive validation
for an incomplete already-validated structural plan. The Rust suite passed
659 tests, with 25 tests ignored. The final Python non-network suite passed
**10,244 tests**, with 4 network tests deselected and 27 warnings, in 623.34 seconds.
Ruff passed for every changed Python file. The unchanged V91 fingerprint test,
proposal runtime validation and exact reproduction of all eight BTC cells passed.

The first isolated Python run had 277 failures, primarily absent archival data;
those failures were retained and not represented as a pass. Focused repair tests
passed. The final whole-suite run passed using the main checkout's complete historical
fixtures. Coverage execution required preloading NumPy/Pandas to avoid a coverage
import-hook error; normal test execution does not require this workaround.

Artifacts live under
`data/logs/research/bidirectional_cohort/v92_strategy_repair_20260922/`:
`screen_v2/report.json`, `screen_365d_v1/report.json`, per-cell trades/configs,
`inputs_365d/manifest.json`, `sndk_sizing_counterfactual.json`,
`current_venue_preflight.json`, test logs and `source_staging_manifest.json`.
The manifest records exact source hashes and the prior versions backed up before
staging. `screen_v1` is retained as an incomplete attempt that lacked TSLA inputs.

Reproduce the recent screen from the repository root, selecting a new output:

```sh
PYTHONPATH=src:scripts .venv/bin/python scripts/v92_strategy_repair_screen.py \
  --inputs data/logs/research/bidirectional_cohort/v90_expansion_screen_20260920_v1/inputs_15m_stitched \
  --supplemental-inputs data/logs/research/bidirectional_cohort/v90_expansion_screen_20260920_v1/inputs_15m \
  --output /tmp/hypervector-v92-recent-replay
```

For the year screen, use the retained `inputs_365d` directory and
`--symbols BTC ETH SOL HYPE`. Output directories must not already exist.
Input file hashes, coverage, gaps, costs, trade rows, block results, worst trades,
profit factors, drawdown, buy-and-hold and cut-winner counts are in each report.

## Operating choice and rollback

| Choice | What changes | Principal limitation |
|---|---|---|
| Continue the authorized pause | No new live trade exposure; retain research capture | No live opportunity capture |
| Review the $10 sizing proposal | Explicit smaller estimated loss per position | Does not improve entry expectancy; still unapproved for live |
| Restart unchanged V91 | Restores the existing trading rules | Retains the sizing that permitted the incident loss |
| Deploy tested replacement rules | Changes entry/exit behavior | Current evidence does not support an improvement |

Recommendation: retain the pause and the tested implementation; do not describe
an unvalidated replacement as ready. A future restart requires a concrete
strategy/risk decision and a fresh flat/order-free check. Rollback of the new
optional sizing behavior is omission of its contract while disarmed; existing
V91 configuration already omits it. Do not revert the shared dirty tree or clear
the operator hold as part of rollback. The backup and manifest identify only
this repair's source changes.

## Post-review correction, 2026-09-22 17:07 UTC

A resumed session found that `size_for_stop_risk` raised
`CohortExecutionPlanError` before submission whenever a structural stop anchor
lay inside the modeled entry fill interval: evaluating the favorable fill bound
made the anchor non-adverse. Nothing in the routing execution, the route cycle or
the runner handles that exception, so the backend would have faulted and been
restarted on a market condition rather than a technical failure. With the
proposal's `entry_slippage_cap_fraction = 0.002` and `minimum_stop_bps = 20`, the
condition is an anchor within 20 bps of the mark, which hourly ATR anchors make
uncommon but not impossible.

`_worst_loss` now requires the stop to resolve at the mark itself and skips a
modeled fill that is more favorable than the anchor, because such a fill cannot
bound the loss and the post-fill protection path rejects it independently. The
worst loss remains at the adverse bound or the short-side clamp turning point, so
every previously valid sizing is unchanged; the recorded SNDK counterfactual
recomputes identically. Ten regression tests were added across the sizing and
engine suites (41 focused tests pass; the full non-network suite passes
10,254 tests); the changed files are Ruff clean. The
staging manifest still records the pre-fix hashes; the post-fix hashes are in
`HANDOFF.md`. This correction does not alter the economic conclusions, the
recommendation, or the proposal's unapproved status.
