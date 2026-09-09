# Signal-time occupancy correction and routing scope

The research coordinator could turn a close-only strategy decision into a
replacement entry. A signal generated while its asset position was open became
eligible after the coordinator processed that opening's exit. Confidence is high
in this reproduced defect and its bounded correction; its historical financial
impact remains unmeasured. No live code, configuration or process was changed.

Source `9a2def6` corrects the coordinator's admission semantics. Source
`bb5c302b8018bf6546a389320daef64e1cebf869` adds the separate offline routing
projection and is the frozen source used for archived verification.

## Reproduction and correction

Five controlled ETH, SOL, SPCX, SNDK and Brent comparisons show the unchanged
original bar engine produces one trade while the old coordinator leaves a
replacement position open. The original engine handles an open position's
close-only decision without scheduling a new entry when reversal is disabled.

Eight complete one-hour synthetic source-calendar cases cover ETH/SPCX, both
source revisions and both registered execution clocks. Each includes the full
seven-asset source grid and a second coherent entry proposal at the held side's
recipe-exit decision. Restoring the exact old admission function produces two
closed target trades in all eight cases. The corrected coordinator produces one,
leaves no target position open and retains the excluded proposal in its audit.
These are artificial 2030 cases, not observed trades or prospective outcomes.

Admission now uses the position state after earlier-bar risk and due exits but
before current-opening exits and current-bar risk. It records
`provider_signal_while_position_open` when otherwise-valid entry geometry belongs
to an occupied asset at that decision. Invalid geometry retains its existing
reason and precedence. The change adds no cooldown: a later fresh decision can
enter, and a stop resolved before the decision can free the asset.

The low-level shared account still applies explicitly admitted closes and entries
in its established order. Prices, costs, sizing, funding, barriers and holding
rules are unchanged. One older overlapping-clock fixture expected replacement
after a same-decision recipe exit; that expectation was corrected while retaining
its exit-time, prior-stop and stale-risk checks.

## Verification and limits

- Twelve focused occupancy tests compare original-engine behavior, later fresh
  entries, a prior-bar stop and a current-bar stop.
- Eight source-calendar tests pass; restoring the authenticated old function
  makes all eight fail on the expected two-versus-one trade count.
- The targeted 68-test run covers all 77 statements and 22 branches in the
  changed entry-admission module and the new routing-projection module.
- The frozen archive passes 1,205 tests across 64 files: all allocation tests,
  native bidirectional routing, canonical preference and three poller files.
  Its exact test list is retained in `archive_test_manifest.json`. This selection
  differs from the earlier worktree run; the counts are not interchangeable.
- All 5,399 tracked Git blobs and executable modes match before and after the
  archived tests. All eleven rehydrated historical dependency files remain exact.

An older default-collector construction test initially lacked its historical
source-follow report and vendor cache in the research worktree. Restoring the
original report and nine profile-pinned vendor files, plus the imported storage
helper authenticated against vendor commit
`ad15f2bdc949619be495a5f516babd08f7f52a90`, resolves it. The archive uses the same
eleven files and a recorded link to the existing backtest-lab directory, which
this construction test only checks for existence. No provider is polled by that
test. The retained `legacy_test_dependency_green.log` is an intermediate failure
despite its filename; `legacy_test_dependency_complete.log` contains the pass.

The separate routing projection orders supplied fresh intents by decision time,
configured asset order and provider priority, then reuses native canonical
preference and routing. Ten controlled checks cover seven simultaneous assets,
input permutations, independent versus legacy canonical identity, future
evaluation exclusion, opposing sides, limited capacity, UNKNOWN and inactive
authority. It is not wired into the source calendar. Configured exits, complete
historical eligible sets and dynamic account application remain unqualified.

## Historical comparisons and operational boundary

The independently verified September 9 10:53:17 UTC snapshot contains 259,200
of 552,960 core minute comparisons and 21,024 of 27,648 XYZ quarter comparisons,
with zero differences. BTC has both source streams complete; SPCX and SNDK each
have both history conventions complete. This is partial comparison evidence,
not profitable-strategy evidence. The missing twelve-day XYZ initialization
and HYPE UNKNOWN compatibility limitations remain explicit.

At 11:00:33 UTC the existing core parent/four workers and XYZ worker are present.
Both source collectors have matching live PIDs, heartbeats under 27 seconds,
no reported error and all 26 code pins unchanged. Both live-profile hashes remain
`696fa385d588d29ca0a6dcc1539a7e11d37af58c9523fd6ed3e5a473bc4a08a3`.
No account outcome or sealed prospective strategy result was read.

## Decision, alternatives and next investigation

| Alternative | Consequence | Research decision |
|---|---|---|
| Retain the old admission behavior | Reproduced close-only decisions can create extra trades | Reject for the new evaluator |
| Correct signal-time occupancy | Matches the tested original close-only behavior and retains excluded proposals | Accept within the tested research scope |
| Declare the complete evaluator qualified now | Omits remaining native routing, exit and historical integration checks | Defer |

Next, qualify complete historical eligible sets, canonical selection and native
routing against the research adapter, preserving configured exits and account
state. Then measure the correction on permitted historical data ending September
7. The September 8–22 and September 9–23 outcome seals remain intact. Existing
24-cell synthetic accounting results retain their declared programmed-signal
scope; those cases did not exercise the newly reproduced collision.

An original-strategy counterexample, incorrect decision-position boundary,
changed source or a failed independent/archive reproduction would update the
correction's confidence. Broader historical agreement and account reconciliation
are required before full evaluator qualification. No profitable change or live
deployment is proposed by this finding; execution authority remains none.

Evidence root:
`data/logs/research/bidirectional_cohort/v89_routing_contract_20260909_v1/`.
Journal revision 19 preserves revision 18's evidence prefix.
