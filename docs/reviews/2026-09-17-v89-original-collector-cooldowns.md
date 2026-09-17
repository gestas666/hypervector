# Original collector cooldowns: completed candidate evidence

Recommendation: retain the offline audit repairs and the three completed
cooldown qualifications. Complete the separately declared delayed-header peer
experiment and exact archived reproduction before proposing adoption.
High confidence is scoped to the completed controls and independently verified
saved evidence; financial benefit and deployment readiness remain unproven.

## What changed and why

Research commit `b45eec30069a77b8b9cfc1457378641eb70e8e9b` separates delivered
HTTP responses from usable market data in the independent observation-grid
checker. A delivered 429 or 503 cannot supply expected market observations,
even when its body resembles successful data. Another repaired audit assumption
now accounts for original attempts deferred before dispatch without erasing
their local obligation or inventing a subscription.

The peer verifier reconstructs the exact ordered read prefix and the original
early-return counters. The native verifier reconstructs each reservation against
both original attempt spacing and the received-429 cooldown. Intervention scope
uses the actual producer identity: quarter collectors also request one-minute
candles, so interval alone was an invalid way to identify the native source.
These are research transport and audit changes, not identified live order bugs.

The saved all-429 control retained 151 attempts, 5 admitted subscribers, 3
transports, 2 shared subscribers and 146 deferrals, with zero observations in all
five original stores. Current combined controls passed 89 tests with one optional
test skipped; seven additional boundary checks passed. Counts overlap with
earlier measurements and are not a unique total.

## Completed original-loop experiments

Each study declared 1,300 seconds, full-day requests, all five original collectors,
real clocks and unchanged source policy. The OS sandbox denied network access.
All twenty original collector processes exited normally, but that alone did not
qualify every intended intervention. Independent verification was completed again
at 23:16:21 UTC against the original raw files, indexes, grids and accounting.

| Scenario | Qualification | Native requests | Native indexed observations | Minimum retry delay after a received 429 |
|---|---|---:|---:|---:|
| Single native 429 | Passed; subsequent HTTP 200 recovery | 13: one 429, twelve 200 | 4,434 | 450,290 ms |
| Repeated native 429 | Passed; four failed responses and three cooldown resumptions | 4, all 429 | 0 | 360,032 ms |
| Peer 503 | Passed; unknown-weight refusal followed by allowed recovery | 19, all 200 | 4,428 | Not applicable |
| Zero-delay peer 429 | Intended 429 branch not exercised; test failed its explicit coverage assertion | 13: one unavailable, twelve 200 | 4,434 | Not applicable |

Repeated 429 covered native slots 0–3 and one history request. It did not cover
all six slots or claim successful native market data under persistent errors.
The other three studies covered all six slots. Each quarter collector pair
completed 2/23/2/23 original cycles in its own study. The measured simultaneous
intervals were 1,301,714–1,302,068 ms; final verification added runtime afterward.

| Scenario | Local attempts | Admitted subscribers | Deferred before dispatch | Distinct transports | Shared subscribers |
|---|---:|---:|---:|---:|---:|
| Single native 429 | 543 | 273 | 270 | 171 | 102 |
| Repeated native 429 | 781 | 139 | 642 | 122 | 17 |
| Peer 503 | 299 | 299 | 0 | 208 | 91 |
| Zero-delay peer 429 | 555 | 283 | 272 | 193 | 90 |

These are separate synthetic studies, not additive economic samples. Delivered
HTTP errors can be marked response-available by the transport while remaining
invalid market data. In particular, all four repeated-native 429 responses were
delivered, but they created zero native market observations.

The zero-delay peer study delivered 429 to peer 27818 while earlier peers in the
native read order recorded deferrals. The original guard refused unknown recent
weight before reaching that 429. The sole 429 then aged out of the five-minute
lookback. Its raw/index/accounting evidence passed; the explicit branch-coverage
assertion correctly failed. This result has not been relabeled as a successful
peer-429 qualification.

## Separate delayed-header experiment and archived work

Commit `72df09a49db4cd001045d40f3c079e648d70eba2` declares a new scenario with
2,000-ms first-response latency using the existing synthetic transport. It
preserves original ten-second deadlines, budgets and cooldowns. The candidate
has passed 105 combined regression tests, 66 scope/declaration controls with two
optional skips, and seven header-evidence checks; these counts overlap. Its
scenario module has all 21 statements and 10 branches covered.

The actual original native guard observed eight explicit peer-429 refusals in
the retained delayed-run prefix. Full qualification is still pending: it must
show subsequent allowed recovery and saved evidence proving that all first
caller and worker admissions preceded the first 429 headers. The candidate run
is PID 81741, creation time 1789686434.393404, tool session 99619.

Exact archived source now runs the three previously qualified scenarios and
the expanded regression suite in separate processes. Those archived results
remain pending. The delayed-header archive scenario will start only after its
candidate result is assessed. Neither archive activity nor early branch
observation authorizes live deployment.

All 11,532 source/archive file hashes for the first candidate matched after its
completed experiments. Its 33,823,339-byte archive SHA-256 is
`632ad1e590d9db6a2961944f3ae89bdf05d504936cb5bf476ba906ae2586c32c`.
The delayed successor initially matched all 11,542 source/archive hashes; its
33,827,742-byte archive SHA-256 is
`894061bc8cf2e51fe018d5827ed613ee06fc44a9b043e0e81544a55e25a67ff0`.

## Interpretation and remaining limits

Applicable regime: research acquisition across market conditions. Expected
upside: preserve trustworthy input data and prevent false audit conclusions.
No profitability, venue charge, external-IP headroom or real-network capacity
estimate is established. Proposed live change: none.

| Alternative | Trade-off |
|---|---|
| Leave audit assumptions unchanged | Retain demonstrated HTTP-error and deferred-obligation misclassification. |
| Disable cooldowns or alter peer order to force coverage | Change the original policy being qualified. |
| Preserve completed studies and separately declare delayed headers | Adds qualification time while keeping the original failures and source policy inspectable. |

An unavailable market observation, lost obligation, early reservation, fabricated
read prefix or mismatched immutable source falsifies the corresponding claim.
Exact failing peer-health bytes, quarter acquire-to-begin timing, service restart,
power loss, study-scale cost and operational migration remain unqualified.
Nearby published health is not proof of the exact bytes consumed by a check.
Rollback is leaving these research branches unadopted; no live approval is
requested for this evidence increment.

At 23:14:54 UTC all eleven preserved process identities matched. The backend
reported 6,659 polls, zero faults and unchanged configuration. Five collector
health ages were below 19 seconds. The three native comparison jobs remained
running without terminal failure or qualification files. Sealed economics were
not evaluated.

Primary evidence:
`data/logs/research/bidirectional_cohort/v89_public_collector_cooldown_20260917_v1/sustained_final_independent.json`.
Delayed prefix, controls and process identities are under
`v89_public_collector_cooldown_delayed_20260917_v1/`. Journal revision 10 pins
completed evidence and explicit pending-process snapshots, excluding the
unfinished delayed and archive outputs.
