# V89 passive observer deadline and handoff repair

The agent-owned event observer could miss a complete event appended during its
last sleep: its loop checked the deadline before reading again. A synthetic
fill reproduced `observation_deadline` instead of `native_transition`. This is
an observation defect. The reproduction does not establish a missed live order
or a trading-engine defect.

## Evidence and correction

The original watcher actually ended at **22:39:23.988303 UTC September 15**,
returning `observation_deadline` and tool exit 0. Its terminal receipt and source
remain unchanged. The retained source SHA256 is
`ceff99aa201701ce06ea5b3f53407250a4645487243da1a95b8edded672d016b`.

An overlap anchor captured at **22:37:54.202074 UTC** retained each of eight
ledger inodes, byte offsets and incomplete-row prefixes, plus the backend
identity hash. The successor adapter requires an actual prior deadline and the
same backend/run identity. It restores those offsets, checks replacement or
truncation, and reuses the pinned reader. Before publishing a deadline it checks
backend identity and reads complete final rows. Qualifying rows change the
result to `native_transition`; terminal cursors retain any partial suffix.

The successor started at **22:49:45.457768 UTC**, after the prior process was
confirmed absent. Its PID is **17371**, tool session **27304**, and maximum
duration is 7,200 seconds. A first-scan receipt exists for all eight ledgers.
This is a bounded observation, with a deadline near **00:49:45 UTC September
16**; scheduling can delay its final receipt. A tool wait returning without a
terminal result does not authorize another observer.

## Validation

Seven synthetic tests passed in 0.71 seconds. They cover the late final-sleep
event, a quiet final heartbeat, an event between anchor and successor startup,
a partial row completed across the handoff, changed backend identity during
the final sleep, refusal to continue automatically after a real event, and a
truncated overlap ledger. No venue or financial process participates in them.

A separate byte reader authenticated **3,916,995 bytes / 1,530 complete rows**
between the saved offsets and the eight first-scan endpoints. It independently
matched event counts and incomplete suffix lengths. There were **zero matching
lifecycle/fault events** in those retained intervals. This closes the observed
turnover interval; it does not infer that later intervals are event-free.

Financial-session PIDs **29190, 29191, 30603, 62016 and 62017** retained their
recorded birth times. The successor only reads local ledgers and process
identity and writes its own evidence files. No financial process was started,
stopped, restarted or signalled; no live strategy, execution client, profile,
leverage, sizing, route or production source changed.

## Decision, alternatives and limits

**Recommendation / why now:** retain the scoped observer repair because the
synthetic failure demonstrates a blind interval at a real observer turnover.
The defect applies regardless of asset, strategy or market regime.

**Alternatives:** retaining the original loop preserves the reproduced final
interval miss. A successor starting at EOF also discards the turnover interval.
Saved offsets plus a final read require modest local parsing and retain the
original journal-referenced implementation intact.

**Expected upside:** more complete evidence collection for the next diagnosis.
This is not evidence of improved trading returns. The trigger set remains the
explicit order, fill, protection, close, fault and runtime-stop events; this
observer does not classify every funding or market-data row as an alert.

**Confidence / success / falsifiers:** high confidence in the tested deadline
and saved-offset behavior and the authenticated first-scan intervals. A missed
qualifying row, source-hash mismatch, changed inode, truncated ledger, wrong
run/backend binding, duplicate owner or incomplete terminal receipt requires
investigation. The native two-hour terminal outcome is still pending; it is
not counted as completed acceptance.

**Rollback:** preserve both source versions, anchors and results. Retire only
the specifically identified agent-owned observer if its validation fails.
The existing user session and its financial processes remain outside this
observer's lifecycle. No live-change approval is needed for this passive
diagnostic repair under the continuous research mandate.

**Next investigation:** inspect the same observer's first real lifecycle,
protection or fault result. If it ends at its deadline, inspect that actual
receipt and terminal cursors before another bounded observation. Verify the
installed startup-candle and band-history fixes after a normal user-controlled
backend start. Previously completed studies and the September 22/23 prospective
seals remain closed.

Evidence is retained under
`data/logs/research/bidirectional_cohort/v89_native_observer_handoff_20260915_v1/`.
