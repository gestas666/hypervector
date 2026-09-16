# V89 confirmed-fill protection during a venue read failure

**Recommendation:** install and activate candidate
`0fa2940c369c2b11cfca1b17e98787d2ad74340e` through a controlled, verified restart.
It is committed and pushed on `research/v89-entry-protection-20260916`, but is
not installed in the live source tree. High confidence applies to the tested
failure and recovery behavior; economic benefit and all possible outage
conditions remain unproven.

**Why now / observed problem:** investigating the new SPCX short exposed a
reproducible protection defect. After an accepted entry fill, the engine performs
full venue reconciliation before submitting the stop. If that read raises a
terminal transport or parsing error, the installed code propagates the error
without attempting protection. The failing baseline test shows zero stop calls
after the acknowledged fill. The outer runtime guard records and re-raises the
error; it does not supply that missing protection attempt.

The actual September 16 18:00 SPCX trade received its stop. This failure was
reproduced offline, not observed on that live trade. The current backend and its
Brent/SPCX protective orders were left unchanged during qualification.

**Evidence reviewed:** the SPCX entry receipts and the actual running generation's
pre-start backup. Eleven relevant installed source files match that backup.
The reader executes account state, unified spot balance, open orders and recent
fills serially through the shared SDK lock; signed mutations invalidate shared
read caches. One or more such reconciliations, including possible retries, occur
in the observed entry-acknowledgement-to-PROTECTING interval. Exact per-request
durations were not recorded, so the 3.885160 seconds cannot be attributed to one
endpoint or assumed to be four equal network calls.

**Applicable market regime:** this execution failure is independent of the
strategy's directional or volatility regime. It applies when an opening fill
has been directly acknowledged and subsequent venue reads fail. The candidate
does not add a regime, performance or bankroll rejection gate.

**Proposed live change:** three runtime paths, plus one test file and the
implementation plan in the same commit:

| Runtime path | Candidate SHA256 |
| --- | --- |
| `src/hypervector/live/sol_entry_read_recovery.py` (new) | `54e19b11bf11599efce1d640bfa1bc62a45a32678078b8d26e47d9a8684cc2ff` |
| `src/hypervector/live/sol_range_onset_engine.py` | `36637c87be492b66497422790ee9da3de193f2b0d94c2d39d42bd49dcf1e76e5` |
| `src/hypervector/live/sol_range_onset_ledger.py` | `db1c03dfeaee8eeb4711026288886aa458333893054d95f4d5c23768148b12e3` |

Ordinary successful execution retains reconciliation before protection. On a
known post-entry venue read error, the candidate accepts only a direct,
accepted IOC filled acknowledgement with the exact order identity and finite,
positive executed size and average price. It excludes resting/canceled orders,
non-IOC plans, ambiguous/recovered acknowledgements and unqualified values.
The order-submission layer still checks the durable client identity first.

The candidate records `entry_reconciliation_failure` with the exception class,
provenance and recovery action; it does not put exception text in that event or
manufacture an account/reconciliation snapshot. For qualified fills it binds
the original entry time and execution plan, then uses the existing durable
reduce-only stop submission and full post-stop verification. Persistent read
failure propagates while preserving PROTECTING state and any stop receipt.
OPEN/FLAT still require venue evidence. Existing stop-rejection handling attempts
a reduce-only emergency close. Strategy, sizing, leverage, price limits, retry
counts, assets and normal order sequencing remain unchanged.

**Alternatives considered:**

| Option | Trade-off and disposition |
| --- | --- |
| Keep installed behavior | No deployment cost; leaves the reproduced missing-stop-attempt path. |
| Protect a qualified direct fill after read failure | Selected candidate; improves this failure path while retaining ordinary sequencing and final verification. |
| Place stops before ordinary reconciliation or parallelize reads | Potential latency reduction, but changes successful execution ordering or SDK concurrency. Not measured or included here. |
| Retry indefinitely | Does not establish protection and can leave the lifecycle unresolved indefinitely; not selected. |

**Expected upside:** a transient failure of read endpoints no longer eliminates
the stop attempt for a qualified direct fill. This may reduce exposure to a
missing protective order. No profit, win-rate improvement or numerical risk
reduction is established. Normal-path latency is unchanged.

**Main risks and failure modes:** the order endpoint may also be unavailable or
reject the stop; venue exposure can change after the acknowledgement; malformed
or ambiguous fills remain unresolved without sufficient evidence. A complete
venue outage cannot be solved by this patch. Existing full verification still
rejects contradictory exposure and ownership. The new diagnostic is retained in
the native ledger; this commit does not add a dedicated TUI pane for it.

**Validation completed:** 440 tests passed across 52 execution, reconciliation,
restart, adapter, deadline, ledger and runner test files. Network access and
`.env` reads were denied; writes to the root live/runtime/research database,
configuration and source directories were denied. The new recovery module has
84/84 statements and 12/12 branches covered. The new entry orchestration helper
is fully covered. This is not a whole-system coverage claim.

Controls include both directions, persistent/recovering read outages, SDK and
parser errors, malformed/ambiguous acknowledgements, structural stop anchors,
stop rejection, restart adoption without resubmission, changed post-stop
exposure, rejection/no-fill behavior and prevention of a second entry while
protection remains unverified. Unexpected programming errors are not converted into
this known read-error policy.

Four separate baseline/candidate experiments—long, short, stale-read retry and
IOC no-fill—produce identical complete outputs: adapter operations, state,
delays, errors and native ledger records. Each output is 66,429 bytes, SHA256
`8d13bf0c554eed7bb5ba9232ed5bc55b81cd847485f382bb641a4430058aad3e`.
These controlled traces use fake venue adapters and fixed clocks/order IDs.

The tested worktree, Git blobs and five-file archive match byte for byte. Actual
reverse patch application in a separate scratch repository restored baseline
files and removed only the candidate additions; forward application restored
every candidate hash. Ruff checks pass; new files are formatted, and changed
source/test files satisfy the 500-line/50-line-function limits. Initial test
failures are retained, including two test expectation corrections and a coverage
module-import issue resolved by selecting the source directory instead.

**Validation still required:** explicit deployment approval, fresh current
position/order reconciliation, verified backup, exact source installation and
focused checks, then controlled activation with the current approved profile.
Verify adoption of existing entry/stop identities and fresh live/TUI telemetry
after restart. Do not manufacture a live outage or submit a test trade to qualify
the patch. Future naturally occurring failures can update the offline evidence.

**Success metrics / failure and rollback triggers:** one durable protection
attempt from qualified executed exposure; correct direction, quantity and
anchor; preserved lifecycle time/ownership; no duplicate entry/stop; no false
successful reconciliation; unchanged ordinary traces. Source mismatch, failed
adoption, an attributable new exception, duplicate mutation or different stop
parameters invalidate the candidate. Before activation, restore authenticated
baseline files and remove only the new candidate additions. After activation,
file restoration alone does not replace loaded code: use a verified maintenance
boundary preserving venue-native protection and the original profile.

**Confidence / falsifiers:** high for the reproduced baseline defect and tested
correction; limited to the specified direct-fill and known read-error cases.
Contradictory source bytes, acknowledgement provenance, restart behavior or
venue receipts would reopen the finding. Original ATR-seed qualification and
the fourteen-day native-history studies are separate, unfinished investigations.

**Explicit approval requested:** install this exact candidate and activate it
through the existing controlled restart procedure, preserving the current
profile and verifying adoption of existing positions/stops. This does not
authorize the separate pending startup optimization, lifecycle receipt or
persistent collector deployments.

The governing [user mandate](/Users/gestas/.codex/attachments/0c1c6f2b-0568-4de5-a63c-f7f1e826d3a4/pasted-text-1.txt)
states: “You must obtain explicit human approval before changing any live
strategy, asset universe, route, parameter, leverage, sizing, risk control,
execution behavior, or deployment configuration.” This candidate changes the
execution failure path, so the earlier approval to unstop the installed backend
does not activate it.

Hyperliquid documents IOC cancellation of unfilled residuals and filled-order
acknowledgements containing executed quantity, average price and order ID.
[Official exchange endpoint](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/exchange-endpoint).
The implementation also validates the locally normalized acknowledgement and
retains post-stop venue verification; the documentation alone is not its proof.

Evidence:
`data/logs/research/bidirectional_cohort/v89_entry_protection_read_failure_20260916_v1/`.
