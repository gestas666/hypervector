# Next investigation: exact peer-health inputs to the original traffic guard

Priority: highest remaining acquisition-evidence investigation after the archived
cooldown and admission-audit qualifications. This is an offline research proposal,
not authority to change live collectors, strategy or deployment.

## Evidence and hypothesis

The current sustained observer records publications and the exact receipt lists
returned to the native guard. It does not retain the health-file bytes consumed
by each check. A nearby publication cannot prove those exact bytes.

A two-case synthetic experiment ran the original
`native_minute_traffic.PeerTrafficGuard` while replacing the first health file
after its actual byte read and before JSON parsing. A stale consumed heartbeat
still caused refusal despite a healthy replacement. A healthy consumed heartbeat
still allowed the original check despite a stale replacement. The reproduced
experiment ran under OS network denial and retained exact source/probe hashes.

Evidence:
`data/logs/research/bidirectional_cohort/v89_public_collector_admission_audit_20260917_v1/health_read_probe_reproduced/result.json`
and `probe_health_read_bytes.py` in the parent directory.

High confidence: the demonstrated snapshot/read race exists in these controls.
Unproven: full producer integration, overhead, exception evidence and independent
reconstruction of every health refusal. No live health failure is inferred.

## Proposed experiment

1. Create a successor from the qualified admission-audit source; preserve prior
   source archives, journal revisions and completed runs.
2. Instrument only the owned research check. A scoped Python return profiler can
   observe the original `Path.read_bytes` result without replacing the method or
   changing the guard's policy. Verify code/path identity, restore prior profiling
   state, and reject missing or ambiguous evidence explicitly.
3. Retain ordered read paths, exact bytes and checksums, the supplied check clock,
   and the original result or exception type. Distinguish a failed read from an
   empty file. Preserve exception propagation and the original read order.
4. Independently reconstruct blackout precedence, each health condition, the
   receipt-read prefix and early refusal counters. Do not infer a health read
   from a publication or synthesize unread later peers.
5. Add controlled stale, future, boolean/missing heartbeat, non-null error, wrong
   authority, malformed JSON and missing-file cases. Verify both immediate
   health refusal and refusal after an earlier healthy peer. Include mutation
   after read, forged result, reordered/omitted read and changed-byte controls.
6. Run all five exact original collectors with real clocks and unchanged request
   deadlines/cooldowns. Measure observer overhead and qualification duration.
   Reproduce from the exact archive, then journal and publish the bounded result.

Success: each asserted peer-health decision is attributable to its actual ordered
inputs, and instrumentation preserves the original return/exception behavior.
A mismatch, missing consumed bytes, leaked profiling state, changed original
source, unexpected extra read or altered deadline falsifies the relevant claim.

## Alternatives and limits

| Alternative | Trade-off |
|---|---|
| Keep the limitation explicit | No new observer overhead; health decisions remain incompletely auditable. |
| Read health again after the check | Lower implementation effort but contradicted by the reproduced race. |
| Retain exact consumed bytes | More reliable evidence with observer overhead and profiling compatibility to validate. |

This does not prove an atomic four-peer snapshot, global IP headroom, historical
concurrent occupancy, real-network capacity or economic benefit. Restart/power-loss
qualification and quarter acquire-to-begin timing remain separate obligations.
Rollback is leaving the research successor unadopted. No live approval is requested
until a concrete deployment proposal has independently passed its required checks.
