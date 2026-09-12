# V89 backend health: heartbeat clocks, explicit termination and market ages

**Recommendation:** install the consolidated technical candidate
`1b5eaa90118b868e5084cd750fb0fa96faabbd40` after explicit approval. Its
**64-file package and exact executable** passed installation, rollback and
reinstallation on disposable copies. Production code and the installed TUI
remain unchanged; this proposal includes no trading restart.

**Why now:** an exited observer could still appear connected, and an old armed
ledger could appear healthy after an unrelated acknowledgement or file copy.
These are operational display defects, not evidence about strategy returns.

**Evidence reviewed:** [the preceding configuration review](2026-09-12-v89-configuration-workflow.md),
the [current study](../../data/logs/research/bidirectional_cohort/v89_heartbeat_freshness_20260912_v1/),
red/green source and lifecycle tests, a 14-poll public observer, its checkpoint,
66 native terminal frames, source-clock comparisons, inspected native-cell
images, exact-source rollback checks and seven unsigned venue responses.

**Observed problem and resulting behavior:**

| Problem | Candidate behavior | Evidence |
|---|---|---|
| Fresh file modification time concealed old backend health | Cohort health uses its actual run-bound heartbeat and the existing 60-second inactivity limit | Copied observer and armed acknowledgement-only regressions |
| Operator outcomes advanced the shared synchronization clock | Header explicitly displays the heartbeat clock | Exact native header-to-ledger parity; three advancing heartbeat clocks |
| Normal observer return left running as the final state | A separate `runtime_stopped` event records normal completion | File and signal stop tests; actual observer exit; stopped native views |
| Adding a stopped heartbeat would inflate poll evidence | Normal termination is separate from polling heartbeats | Real emitter-to-audit regression; unchanged poll counts and cadence |
| Chart source age was not independently visible | Inspector reports completed source-1m candle age and venue book age | All seven assets at three sizes; 21 source-clock comparisons |
| Stale or stopped displays implied a running backend would persist | Header and dashboard quit text describe monitor-only exit | Stale and stopped native views; manual controls retain their connection checks |

Terminal faults remain terminal for their run, including after unrelated writes.
A later actual poll can resume a normally stopped observer of the same run.
A new run uses its own health evidence. Missing, degraded, malformed, unsupported
and future health evidence cannot claim a healthy connection. A terminal fault
is not presented as a clean shutdown.

**Applicable market regime:** operational telemetry across regimes. The current
roster remains BTC, ETH, SOL, HYPE, SPCX, SNDK and BRENTOIL. No trading policy,
asset selection, leverage, sizing, entry/exit rule or parameter is promoted.

**Alternatives considered:**

| Alternative | Benefit | Trade-off |
|---|---|---|
| Keep installed code | No deployment | Retains reproduced recovery/configuration and freshness defects |
| Continue using file age | Simple | Unrelated writes misrepresent backend health; rejected |
| Emit stopped as another polling heartbeat | Reuses an event type | Inflates observer poll evidence; rejected |
| Separate terminal events and market clocks | Preserves polling meaning and makes lifecycle explicit | Requires coordinated Python/Rust installation and rollback |

**Proposed live change:** the exact files in the
[64-file manifest](../../data/logs/research/bidirectional_cohort/v89_heartbeat_freshness_20260912_v1/installation_candidate.json)
and its retained TUI executable. This includes the previous reviewed recovery,
chart, control and configuration fixes. The optional candle-session candidate
remains excluded. Base production commit: `fbd0b3c4f065e8657f06e942ef6e46b88bcd5711`.

- Patch SHA-256: `9c866a0a8e0b18e82c876a5f3bcf3447b80a7150defb1f13724b6f7f8a135e9e`.
- Candidate executable SHA-256: `eaf4d25836ff0533b6b451f887921d97eed9af9aa021a70fade47408c5aeb9a1`.
- Installed executable SHA-256: `382253cacea78e51c2dbc0c7e396eda0d24d2c025ae7854e867cd2c78ad329d1`.

**Expected upside:** accurate operational health, reachable market-age evidence
and reliable normal-stop reporting. No measured improvement in returns, trade
frequency or win rate follows from these technical results.

**Main risks and failure modes:** a source/binary mismatch, dropped terminal
events during compaction, incorrect run attribution, clock skew, hidden source
errors, or stale authority being presented as current. Abrupt death without a
terminal event takes more than 60 seconds to become inactive through the
heartbeat check. The check does not prove a process is alive at every instant.
Full live-package branch coverage and installed-terminal acceptance remain
incomplete. Existing unrelated file/function size violations were not expanded.

**Validation completed:**

| Check | Result | Scope |
|---|---|---|
| Rust suite | 605 passed, zero failures; 23 existing ignored | Full crate, 73 harness reports |
| Python suite | 176 passed across 34 files | Observer, telemetry, checkpoint, audit and ledger compatibility; network excluded |
| Changed Python modules | Runner 90.08% statements / 66.67% branches; telemetry 92.86% / 73.81% | New terminal emitter executable lines and branches fully covered |
| Clippy, formatting, Ruff, release build | Passed | Exact captured executable preserved |
| Public observation | 14 successful polls, 7 provider scopes, 19 unique evaluations, no eligible entries or routed actions | 363 completed candles per asset, 364 for SPCX; 98 books; normal isolated stop and checkpoint exit 0 |
| Native acceptance | 66 frames at 100x28, 120x36 and 190x52 | All nine advancing views, seven chart inspectors per size, stopped and stale PORT/OPS/CFG views |
| Independent source comparison | 21 chart cases and every visible heartbeat clock matched | Exact cell/text parity; source-to-render/capture timing checked within a disclosed two-second capture allowance |
| Visual inspection | Three representative native-cell images inspected | Actual native cells; disclosed Menlo fallback; not installed user Terminal |
| Installation and rollback | 64 files and exact binary passed apply/reverse/reapply | Disposable copies; original source archive and executable retained |

The failed test attempts and the initially incompatible stopped-heartbeat
prototype remain in the experiment record. An initial module-targeted coverage
run failed during NumPy import; directory-targeted coverage completed all 176
tests. No tests were excluded to hide that collection error.

**Validation still required:** installation verification in the actual user
terminal after approval; any separately approved backend start and account
reconciliation; execution, fee/slippage and strategy evidence at the scope of
each live-readiness claim. This short observer supplied no fills or return
sample. Both prospective hypothetical outcome seals remain unopened.

**Success metrics:** heartbeat and terminal status match the active run;
acknowledgements cannot revive inactivity; market ages match their source
timestamps; normal exit preserves polling counts; every packaged source and
binary matches its verified hash; no unintended execution authority.

**Failure / rollback triggers:** restore the retained exact source/binary pair
if these invariants fail, the package does not match, or installed acceptance
reveals a regression. Stop the acceptance operation on technical failure and
retain its evidence. The rehearsal receipt contains prior and candidate hashes
for every file. A trading start requires its own explicit authorized scope.

**Confidence level:** high for the tested display, source-health and observer
lifecycle corrections; limited for untested installed operation; no new
confidence claim about profitability. Reproducing a stale-as-current display,
incorrect source clock, altered poll evidence or failed rollback would falsify
the corresponding technical result.

At **03:54:54 UTC on September 12**, unsigned reads showed the existing
**0.306 SNDK short at 1629.2, 10x isolated**, with **−$1.8666 unrealized**.
The full-size reduce-only Stop Market, OID **542326955281**, remained open at
**1669.9**. Thirteen funding cash-flow rows totaled **+$0.096169**. Core was
flat and order-free; no later fill appeared in the bounded query. Original
trading PIDs were absent, and original ledger/profile/binary hashes matched.
These are sequential observations, not continuing guarantees.

**Explicit approval requested:** install candidate `1b5eaa9` using the 64-file
package and exact executable. The proposal does not restart or arm trading.
The objective's Human control clause requires explicit approval for deployment
changes. Earlier installation approval does not identify this new package.

**Highest-value next investigation:** complete installed-runtime acceptance
after approval. While approval is pending, assess entry frequency and opportunity
cost across the seven configured routes using available unsealed historical
and public evidence; separate recipe cadence from implementation delay and
selection effects. Full live and economic readiness remains unproven.
