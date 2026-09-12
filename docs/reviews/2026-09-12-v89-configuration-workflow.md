# V89 configuration workflow: complete context, preserved policy, exact acknowledgements

Candidate `ca8247b3c01ac408a190cffe3cf3fb16e90bc6be` repairs three configuration-workflow defects on top of the previously reviewed recovery, compact controls and chart changes. Its **52-file package and exact TUI executable** passed installation/rollback/reinstallation on disposable copies. The candidate is **not installed** and no trading process was restarted.

**Recommendation:** retain this tested technical candidate for review, then resolve the newly observed backend-freshness ambiguity before claiming complete operational acceptance. The configuration workflow passed its bounded acceptance; the overall trading-system objective remains incomplete.

**Why now:** actual key-by-key use exposed missing configuration lines, rejected disable requests, and a stale pending message after successful backend staging. These defects prevented reliable inspection and review of restart profiles.

**Evidence reviewed:** the [prior combined review](2026-09-11-v89-complete-chart-controls.md), [current study](../../data/logs/research/bidirectional_cohort/v89_config_workflow_acceptance_20260912_v1/), exact fresh observer/checkpoint inputs, native requests and backend outcomes, red/green regressions, current Rust/Python checks, three inspected native-cell images, and seven new unsigned venue responses.

**Observed problem or opportunity:**

| Observed defect | Candidate behavior | Evidence |
|---|---|---|
| Page Down advanced five rows through a four-row viewport; live sizing and other lines were skipped | Paging uses the rendered viewport, wraps long fields, and bounds both directions | Reproduced native failure, regressions, complete row coverage for 21 asset/size cases |
| Compact identity/source and operator keys were clipped or absent | Full identity is reachable in the scope pane; safety notice and edit/action keys remain visible | All 11 editor rows per case; source-path parity and visual inspection |
| Disabling a provider rejected its retained overrides; ETH/SOL also required an active execution scope | Overrides remain valid for observed symbols; disabling removes execution authority while retaining direction, stops, sizing and other policy | Seven disable/re-enable round trips; real route-authority checks; all six override families and invalid-policy rejection |
| Successful staging left `BACKEND VALIDATION PENDING` in the notice | Run/profile/request-bound received, accepted, completed or rejected evidence replaces the pending notice | Exact outcomes for 21 native requests; unrelated-request and changed-identity regressions |

The changes do not make an inactive route executable. `execution_symbols` and executable direction mappings still determine routing authority. Discard restores the local draft; it does not delete a profile already staged by the backend. None of the experiment's 16-second polling drafts was applied to a running configuration.

**Applicable market regime:** operational configuration behavior across regimes. Asset selection and trading parameters remain unchanged. The observed roster is BTC, ETH, SOL, HYPE, SPCX, SNDK and BRENTOIL; this study does not promote their strategies or alter their leverage/sizing.

**Alternatives considered:**

| Alternative | Benefit | Trade-off |
|---|---|---|
| Keep installed code | Avoids deployment | Retains reproduced recovery/display/configuration defects |
| Delete overrides when disabling a route | Avoids one validator rejection | Loses the policy required for an exact later re-enable; rejected |
| Relax policy validation generally | Accepts more drafts | Would permit unintended direction/protection drift; rejected |
| Preserve inactive policy and retain explicit execution scopes | Supports exact reversible scope edits | Changes validator acceptance and requires regression coverage |
| Complete freshness repair before installation | Supports one consolidated later deployment | Defers the already tested corrections |

**Proposed live change:** only the [52 explicitly listed source, test and documentation files](../../data/logs/research/bidirectional_cohort/v89_config_workflow_acceptance_20260912_v1/installation_candidate.json) and retained candidate TUI. Production rehearsal base: `ea296489029aef346f94d6a3bbd2f82e6de52bcd`. Optional candle-session candidate `f59d54c` remains excluded.

- Patch SHA-256: `12c9462e581ad5ddf5ad7dccacd41e3b3e75402e42d01428304e7dfa3735d070`.
- Candidate TUI SHA-256: `eb15bff8928fc4e9d4d56030e0379e3be52c9cb25faa40b38de3376789961225`.
- Installed TUI, unchanged: `382253cacea78e51c2dbc0c7e396eda0d24d2c025ae7854e867cd2c78ad329d1`.

**Expected upside:** complete reviewable configuration, exact retained provider policy, and accurate staging feedback. No measured return, trade-frequency or win-rate improvement follows from these technical checks.

**Main risks and failure modes:** an inactive override leaking into executable authority, drift on re-enable, stale acknowledgement reuse after identity changes, inaccessible wrapped rows, and a source/binary mismatch. A separate remaining freshness concern is now directly observed: an exited observer still renders `BACKEND CONNECTED`. Source inspection shows the inactivity check applies only to armed live ledgers and uses file modification time; operator acknowledgements also advance the shared last-observation clock. This does not establish a currently live market feed. Live heartbeat-versus-acknowledgement behavior still requires a focused test.

**Validation completed:**

| Check | Result | Scope |
|---|---|---|
| Final Rust checks | 587 passed, zero failures, 23 existing ignored | Full crate suite, 72 harness reports; locked/offline |
| Clippy, formatting, release build | Passed | All-target warnings denied; exact native-captured binary unchanged |
| Python checks | 439 passed across 89 test files | Configuration, staging, route authority and runner regressions; network-marked tests excluded |
| Ruff | Passed | Two changed Python modules and the new test file |
| Changed-module coverage | Provider validation 90.0% statements / 82.35% branches; directional validation 91.67% / 66.67% | Broader branch coverage remains incomplete; aggregate live-package coverage from this selected suite is only 30% |
| Native acceptance | 588 frames, 21 asset/size cases, three normal exits | Seven assets at 100x28, 120x36 and 190x52; all 231 selected editor rows checked |
| Backend staging | 21 exact profiles, 63 received/accepted/completed rows | Actual disarmed processor, serializer and reload; isolated request inbox and copied ledger only |
| Source parity | Complete scope and outcome strings; chart closes and provider decision clocks match | Native cell/text parity for every frame; original observer prefix and checkpoint hashes preserved |
| Visual acceptance | Three representative images inspected | Native-cell reconstructions; disclosed Menlo Regular fallback, not the installed user Terminal |
| Installation/rollback | 52 files and exact binary apply/reverse/reapply | Disposable copy only; original sources and executable retained |

The selected Python tests need gitignored historical fixtures. Missing copies caused retained failures before exact fixture copies were provided; no assertions were weakened. A coverage invocation using dotted imports failed during collection, and the directory-based coverage invocation succeeded. The final Ruff module invocation found no module in the project interpreter; the installed `/opt/homebrew/bin/ruff` passed. The independent image-text verifier initially joined two side-by-side chart panes incorrectly and was corrected to inspect the provider pane. These are retained harness/environment errors, not strategy failures.

The new unsigned observer completed five polls. Its ledger observations span **01:49:15.853771–01:50:27.312286 UTC**, 71.459 seconds; the outer process took about 75 seconds including setup. It produced 7/7 provider scopes, 10 unique evaluations, 35 books and 361 consecutive completed minute candles per asset. All latest provider decisions were HOLD. Incremental candle/canonical publications split six symbols and SPCX across separate updates; the verifier merges updates by symbol and checks causal ordering. It does not incorrectly require every incremental payload to contain all seven symbols. The roughly 76-second wording in the original assessment refers to the approximate process window, not the exact ledger span.

The original checkpoint's publication source age was 1.092688 seconds. The observer had exited before native staging tests began. The native captures therefore establish correct projection and staging against recorded input, not a continuously fresh backend. No fills, fees, live sizing or outcome profitability were synthesized. This short sample cannot establish how often entries will occur or support an expectation of large positive swings.

**Validation still required:** distinguish current backend heartbeat and per-asset market-data age from a recent operator acknowledgement; verify actual advancing observer/checkpoint/TUI lifecycle and restart identity; inspect the installed user Terminal after approved installation; complete final source-wide operational acceptance; and reconcile ownership, collateral and venue precision before any separately authorized live operation. Strategy economics, realistic execution costs, portfolio interaction and sealed prospective evaluation remain separate incomplete parts of the full goal.

**Success metrics:** complete reachable configuration, exact effective/draft separation, unchanged inactive policy, no route authority while disabled, exact re-enable, matching backend outcome, no financial adapter/order in observer work, source parity and exact rollback.

**Failure / rollback triggers:** unintended direction, stop, sizing or runtime changes; an inactive route accepted for execution; stale request identity presented as current; hidden evidence; or a package hash mismatch. Stop the installation procedure on mismatch, restore only archived installation paths and prior executable, and preserve ledgers and venue state.

**Confidence level:** high for the reproduced configuration defects, current tests, exact recorded-data/native request parity and disposable rollback. Confidence in full live readiness or improved profitability remains unestablished. Contradictory native frames, policy drift, stale authority or unexpected adapter activity would invalidate the corresponding scoped result.

At **02:51:59 UTC on September 12**, seven authenticated unsigned responses showed the existing **0.306 SNDK short at 1629.2, 10x isolated**, with **−$2.0808 unrealized PnL**. The full-size reduce-only buy Stop Market remained open at **1669.9**, OID **542326955281**. Twelve native funding cash-flow rows total **+$0.095905**; funding-position accumulator signs are not substituted for cash direction. Core was flat/order-free. The bounded fill query contained no fill after the original stop boundary. Original trading PIDs were absent and original ledger hashes/terminal rows were unchanged. These sequential observations need refreshing before a current-state claim.

**Explicit approval requested:** no restart or financial action is requested. The concrete installation scope is candidate `ca8247b`'s exact 52 files and TUI, subject to separate explicit approval under the objective's Human control clause. The recommendation is to resolve the identified freshness issue before presenting a consolidated installation request; this report grants no deployment authority.

**Highest-value next investigation:** reproduce and correct heartbeat/market freshness reporting for an inactive observer and for an armed snapshot receiving only operator acknowledgements, then verify recovery with an advancing public observer and checkpoint. Keep both prospective hypothetical outcome seals unopened and continue the independent economic pipeline.
