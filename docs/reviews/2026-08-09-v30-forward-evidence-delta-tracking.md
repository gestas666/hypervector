# V30 forward-evidence delta tracking acceptance

Date: 2026-08-09

## 1. Problem restatement

The successor decision needs an explicit answer to two questions: what changed
since the last frozen v30 readiness report, and whether that change is material
enough to revise the research journal or consider a transition. Routine
completed-bar evaluations must not be confused with new economic evidence.

Success requires same-run and same-candidate identity, monotonic cumulative
counters, immutable inputs and output, explicit protection and flat-boundary
tracking, and zero execution authority.

## 2. Known facts and assumptions

- The compared source is active v25 run
  bidirectional-live-1786182011216, profile fingerprint ec7715...7ecc.
- The inactive candidate is v30, fingerprint 4cb3ca...ecf54, with exact
  executable routes ETH Range Onset, SOL Range Onset, and SPCX Swing/HA.
- Aggregate readiness reports do not expose individual closed lifecycle
  identities. The comparator therefore rejects changed economics when the
  closed count is unchanged, but it cannot prove prior-lifecycle immutability
  after a new close.
- The command is report-only and cannot start, stop, place, cancel, close,
  resize, route, or authorize execution.

## 3. Implemented contract

v30-live-forward-delta now:

- rejects changed source run, runtime profile, candidate identity, route set,
  symbol set, direction contract, or maximum-position contract;
- rejects backward checkpoint time, route counters, performance counters, or
  live fault count;
- rejects disappearing performance and rewritten aggregate economics when no
  new close occurred;
- separates evaluation cadence from eligible signals, resolved signal
  horizons, exact closes, and new side evidence;
- detects protection degradation, a newly reached flat boundary, transition
  state changes, and recommendation changes;
- recommends a journal revision only for a close, new side, fault, protection
  degradation, flat boundary, transition change, or recommendation change; and
- refuses to overwrite an existing artifact.

## 4. First real same-run delta

The authoritative v2 delta compares checkpoint times 17:45:33Z and
17:59:07Z.

| Measurement | Change |
|---|---:|
| Route evaluations | +29 |
| Eligible signals | 0 |
| Resolved signal horizons | 0 |
| Exact selected-route closes | 0 |
| New directional evidence | none |
| Runtime faults | 0 |
| Open positions | 6 to 5 |
| Protection degraded | no |
| Flat boundary reached | no |
| Transition state | inactive to inactive |
| Recommendation changed | no |

The decrease from six to five open positions is a live lifecycle change but not
new v30 route evidence. No economic journal revision is warranted. V30 remains
inactive with the recommendation
retain_v30_inactive_collect_exact_forward_evidence.

## 5. Validation

- Thirteen focused readiness and delta tests pass.
- Ruff lint and format checks pass on all four new files.
- The real delta binds both readiness artifacts by SHA-256.
- The later readiness artifact binds decision-ledger prefix 881,517,305 bytes
  with SHA-256
  a3ed5ea64a257528cb551f55de3a0a29c9252ba04bafb55ee2533fcda9211124;
  an independent prefix rehash reproduced it.
- Candidate SHA-256
  303c8e9ae1c8947481ab64e2894cffb964c9de4b17811bb44ae6d8ce9dd3d81c
  matches the staged v30 configuration.

Artifacts:

- data/logs/research/v30_live_forward_readiness_20260809T174500Z.json
- data/logs/research/v30_live_forward_readiness_20260809T180200Z.json
- data/logs/research/v30_live_forward_delta_v2_20260809T174500Z_180200Z.json

## 6. Risks, falsifiers, and decision

Confidence is high that the comparator detects the declared identity,
monotonicity, protection, flat-boundary, and aggregate evidence changes. This
is falsified by a test or real report that accepts identity drift, backward
counts, unreported protection loss, output overwrite, or same-count economic
mutation.

Economic confidence in v30 remains low. A new exact close, genuinely new short
evidence, positive repeatability excluding the largest winner, or a corrected
source defect would update the recommendation. Routine evaluation growth alone
will not.

Decision: keep v25 unchanged, keep v30 inactive, retain the economic journal at
revision 2, and produce another immutable delta only after a material event.
