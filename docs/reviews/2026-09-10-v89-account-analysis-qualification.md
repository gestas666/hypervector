# Complete account reporting qualification

Status: bounded reporting qualification and frozen test reproduction completed
September 10, 2026, 00:33 UTC.
The historical experiment and release readiness remain unproven. No live process,
configuration, strategy or execution behavior changed.

The reader requires the caller's exact completed report identity and original
case. It binds allocation through distinct expected control/equal fingerprints,
verifies all declared account and original source files, checks the inactive
historical or explicitly synthetic scope, and reruns the independent Decimal
posting ledger. It does not trust a preexisting independent-success file.
Only then does it expose immutable account bytes, typed snapshots and explicit
terminal marks for all seven original assets. Source identities are checked again
after reading. Source-price and native-routing validity still depend on their
separate qualifications; this reader does not independently prove them.

Trade reporting attributes each modeled opening to either its recorded close or
its terminal open mark. Open positions retain paid entry fees and funding; no
terminal exit or exit fee is invented. Contributions reconcile to terminal
cash/equity, realized/unrealized PnL, fees, funding, margin and directional exposure.
Accepted entry identities and timestamps must match every contribution. Reports
include closed wins/losses/breakevens, entry frequency and gaps, closed holding
times, average opening notional, and account-level rejection reasons. Native
pre-account routing exclusions remain a separate unfinished reporting component.

A hand-calculated control contains a winning long, losing short, breakeven long
and carried open short: closed net $4, open marked net $28, total equity change
$32 after all incurred fees/funding. A separate adverse open-short mark produces
negative terminal equity and remains a reported loss. Empty accounts retain
undefined per-trade ratios. These are synthetic arithmetic controls, not strategy
returns. The final implementation preserves each audited closed posting's sign;
a recorded $0.0000000005 loss cannot become a breakeven merely because an
independent recomputation differs within the $0.00000001 reconciliation tolerance.
That regression was observed failing before the correction and passing afterward.

The combined worktree qualification passed **87 tests in 172.11 seconds**.
Coverage is 400/413 measured statements: path arithmetic 118/118, trade arithmetic
166/166, and artifact reader 116/129. The reader's full native two-day controls
pass under both exit clocks; path and trade totals reconcile to the freshly
audited terminal account while preserving terminal open positions. The tests also
exercise changed report bytes, rehashed corrupt balances, changed/missing source
references, wrong case/allocation identities, sealed/partial scope and execution
authority. These checks do not establish whole-system coverage or a profitable
historical improvement.

`manifest.json`, `tests.log` and `result.json` under
`data/logs/research/bidirectional_cohort/v89_historical_account_analysis_qualification_20260910_v1/`
retain the command, implementation and seven selected test/support identities,
completion and post-run verification. The earlier reader run passed 30 tests;
the expanded trade-only run passed 27 before the additional posting-sign test.
Missing-module red runs and the sign-specific red/green logs are retained in the
parent research directory. No completed test job should be restarted.

The reporting implementation is frozen as
`e3b55984bfeb3aef3276facb86f37598a232482c`. Its 33,599,287-byte archive has SHA-256
`e9a3e44400ef52369b0d63808544932e50c3ce4799c7f56f86f3300eab1f4f55`.
All 1,927 Python/lock members match the tested implementation. The same suite
passed from the extracted archive: **87 tests in 172.00 seconds**, with identical
400/413 measured statement coverage. Post-run verification at 00:33:33 UTC
checked all 5,559 regular archive members and executable bits, commit metadata,
the full implementation and seven pinned test/support files. `source.json`,
`archive_manifest.json`, `archive_tests.log` and `archive_result.json` retain this
reproduction. Worktree session 18830, archive session 81628 and both verifications
are complete; preserve their sources and artifacts.

Confidence is high within the measured controls. A changed source identity,
unreconciled contribution, incorrect boundary or altered closed-result sign
would invalidate the corresponding qualification. Native exclusion attribution,
complete matrix report assembly and the full historical outcomes remain required.
The reproduced synthetic tests do not substitute for those results. Preserve the qualified
`a86bd6f` replay engine and the already-running first-case operator.
