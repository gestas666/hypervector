# Actual shared-service owner loss: retained evidence and explicit incomplete state

The corrected experimental harness passed **36 tests** from committed source
and its verified archive, in **26.59 s** and **26.52 s**. Both handles returned
zero inside the same network-denying sandbox. Source commit
`3e9e9e0c3a9b276f26c1a32f8ea78afa262a95e2` is pushed on
`research/v89-owner-process-observation-20260918`. It changes experimental
process observation and cleanup checks; production implementation is unchanged.

The experiment kills its actual service-owner process with SIGKILL while five
original collector interpreters are attached. The exact failure boundary and
synthetic delays are hashed into every namespace before any collector starts.
Original schedules, guards, request deadlines and the eight-second worker
deadline remain intact. No production process is targeted.

| Boundary | Working source | Archived source | Interpretation |
|---|---|---|---|
| All five original indexes committed | Five successful stopped reopens | Five successful stopped reopens | Existing evidence survives this owner-loss boundary |
| All five admissions, with incomplete transport bodies | Five explicit unresolved recovery errors | Five explicit unresolved recovery errors | Incomplete original attempts remain incomplete |
| Shared transports abandoned after bounded orphan termination | 3 | 5 | Scheduling/coalescing changes the number of actual shared transports |

At the committed boundary, all owned descendants terminated, all five history
prefixes remained intact, logical rows were unchanged and recovery issued zero
new transport attempts. A separate verifier re-read the original raw/index and
transport evidence and reproduced both saved reports.

During incomplete bodies, the new real service opened while recorded workers
were still alive. It did not redispatch them or declare them terminal while
alive. Outcomes became `abandoned`, with no invented completed-worker receipt.
All five fresh original processes then returned code 2 with the exact unresolved
attempt error, issued zero new transports and preserved their logical rows.
**This is verified fail-closed classification, not automatic resumed collection
after arbitrary service loss.**

The predecessor `75d6bf9976e9308280f13527ecfc74d44141ecd0` passed its initial
two owner-loss cases and eighteen adjacent checks, but both formal sandboxed
source/archive suites later failed the in-flight observer: **19 passed, 1
failed** each. macOS denied an orphan command-line query. The error was in the
experimental liveness helper and its failure cleanup, not a proven production
coordinator failure. Every recorded descendant was subsequently confirmed absent.

Three focused regression assertions failed before the correction. The successor
uses the existing coordinator PID/birth/status liveness helper. Missing, zombie
and dead identities are terminal; permission denial on required birth/status
evidence still propagates. Full command identity remains required before cleanup
signals. Ten observation/cleanup tests and six existing coordinator guard tests
passed. The complete 36-test suites include the actual owner-loss reproduction.

Earlier exploratory failures also remain preserved: one verifier invocation
omitted retained accounting; another observer hooked the definition instead of
the runner's imported binding. Their corrected probes are exploratory evidence;
the formal harness fixes their inherited ordinary-stop declaration before
namespace creation. None of these failures was overwritten or counted as a pass.

All **11,642** checks match the corrected 5,821-file source manifest, with no
changed or missing files. The standalone archive SHA-256 is
`773015d78177358b986974961e3e87c1ce827c0464a947d9d51530c7dafea972`.
Materialized archive source files are independent filesystem clones whose bytes
were verified against every tar member; the compressed archive remains standalone.

Research import had deferred below its 8 GiB free-space reserve. Agent-created
duplicate sources were replaced with verified independent clones only after
matching their retained archives and checking inactive targets for open handles.
The three historical targets retained all 17,408 manifest files unchanged;
17,391 byte-identical files were cloned. Measured free space moved from
8,577,540,096 to 9,083,088,896 bytes during that operation, with concurrent work
also affecting disk usage. Imports subsequently succeeded without lowering the
reserve or restarting the live backend. This provides headroom, not a long-term
storage-capacity guarantee. The original parser failure on named evidence groups
was preserved; it occurred before any target mutation.

A separate journal-output bookkeeping mistake pinned an empty stdout file before
the journaling command printed its summary. The complete output was backed up
and retained, and the exact empty pinned snapshot was restored. The repair record
documents both hashes. All **28,598** references across the two graceful-recovery
revisions then matched again, with zero missing or changed references.

**High confidence within the stated fault boundaries.** Early terminal claims,
extra transport dispatch, changed source/rows, lost history, permission errors
treated as death or cleanup of a changed identity would falsify these claims.
Host power loss, production network behavior, operational migration/rollback,
full-study overhead and safe continuation of unresolved attempts remain open.
No improved profitability is inferred from this infrastructure qualification.

Retain the corrected isolated harness. The highest-value next investigation is
an evidence-preserving recovery protocol for original attempts abandoned before
a complete response: any proposed continuation must reconcile original request
identity and local weight without inventing a success, deleting the unresolved
witness, or silently issuing the old request again. No live change is proposed
or approved by this review.
