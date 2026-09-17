# Public sharing: owned clocks and client receipt qualification

High confidence in the qualified clock/receipt component. The earlier sharing
kernel accepted logical clocks for offline replay; that did not establish when
a real database operation acquired its lock or when a client received bytes.
Treating those clocks as physical delivery would risk reporting delayed data as
timely. This is an integration boundary, not evidence that current collectors
or the live execution system used incorrect receipt timestamps.

The new isolated branch `research/v89-public-transport-20260917` is committed
and pushed at **3252022c47cce8c400e9909a3cec4f9dcac8c16b**, in
`/Users/gestas/Prototypes/hypervector-v89-public-transport-20260917`.
It adds an owned-clock adapter and separate receipt records. The logical
kernel's transaction bodies were extracted for reuse; its existing public
behavior remains covered by the prior tests and replay comparison.

## What is now established

- Original client request time, deadline, declaration and earlier-sharing
  consent are retained separately from actual broker registration. The broker
  samples its wall clock **after** acquiring the SQLite transaction. A real
  held-lock test observes no clock sample until that lock is released.
- Response preparation does not claim client receipt. The owned protocol uses
  `broker_publication_started_ms` and `broker_prepared_ms`, with
  `client_received_ms` unset. These are operation-start observations, not
  commit-completion timestamps. The old logical `subscriber_received_ms` and
  `published_ms` names are absent from the owned receipt.
- A separate acknowledgement retains the trusted local client's reported
  arrival and `acknowledgement_started_ms`. Data read after the client deadline
  is explicitly unavailable. Equality at the declared deadline remains allowed.
  A late acknowledgement does not backdate or replace the client arrival time.
- Registration, preparation and acknowledgement updates commit atomically with
  their corresponding kernel state. Injected SQL failures roll back dispatch
  grants and preparation receipts; failed acknowledgements leave delivery
  unconfirmed. Existing immutable receipts survive retry and reopen.
- Changed identities, impossible clocks, regressing wall clocks, wrong parent
  hashes, mismatched prepared/delivered fields and unowned subscriptions or
  transports are rejected. Cancellation, transport expiry and HTTP 429 retain
  the kernel's explicit behavior. No automatic retry is introduced.

During development, failure controls caught an unowned-transport adoption path,
a rehashed delivery that was not compared against its prepared body, and a
prepared record that could silently revert to pending. Those prototype defects
were repaired before this qualification. Their red transcripts are preserved;
they were not deployed trading defects.

## Evidence

**159 candidate tests and 159 tests from the frozen archive pass**, with network
access denied. This includes the prior 119 controls and 40 owned-clock controls.
The modified kernel covers 139/139 statements and 42/42 branches; the new record
module covers 65/65 statements and 20/20 branches. Across those modules and the
owned adapter, 298/299 statements and 91/92 branches execute. One defensive
missing-preparation guard is unexercised after the earlier consistency checks;
complete combined coverage is not claimed. Ruff and size/annotation checks pass.

Three real spawned-client cases use one-way OS pipes and fabricated bodies:

| Case | Broker prepared (UTC epoch ms) | Client read (UTC epoch ms) | Result |
| --- | ---: | ---: | --- |
| Timely read | 1789648972540 | 1789648972651 | Response available |
| Read after deadline | 1789648972672 | 1789648974695 | Expired; body unavailable |
| Client exits before acknowledgement | 1789648974720 | Unconfirmed | No delivery receipt |

The crash test asserts child exit code 7. An independent SQLite/JSON check
verifies the stored receipt hashes, parent linkage, arrival ordering and deadline
outcomes. The client clock is sampled immediately after `recv_bytes`; no network
or HTTP request occurs in these tests. These cases establish the tested receipt
boundary, not a complete production coordinator.

The previous fresh-trace logical replay is authenticated against its existing
journal. Its complete JSON report and both SQLite databases remain byte-identical
after the kernel refactor, and again when executed from the new archive.
This establishes preservation of that offline behavior, not measured production
traffic reduction or latency improvement.

The archive has **3,684 verified files**, matching Git blobs, the worktree and
extraction. Its 29,050,880-byte SHA-256 is
`e570db020dd2b3d49efcba6e0cd0db3a04ede710907ea26b441056e3bc676dd3`.
Evidence is retained under
`data/logs/research/bidirectional_cohort/v89_public_transport_clock_20260917_v1`.
Source, archive, qualification transcripts, replay ledgers and selected process
test databases are frozen evidence; subsequent work needs a new revision.

## Remaining work and decision

Retain this component and proceed with the bounded public HTTP worker and
coordinator. No collector deployment proposal is ready. The plan remains
`docs/plans/2026-09-17-v89-public-transport-integration.md` in the isolated branch.
Required next evidence includes complete HTTP wall deadlines, bounded bodies,
partial-response/error provenance, worker crashes and lost acknowledgements,
dispatch ownership, aggregate admission/queue behavior, and full failure-aware
process replay. Existing collector/study continuity needs a separate reviewable
plan and approval before any deployment configuration change.

The adapter trusts a local client to report its receipt clock and assumes a
single host clock domain. It does not authenticate an untrusted remote client.
Wall-clock regression fails explicitly. Preparation timestamps precede transaction
completion; client receipt remains the relevant deadline observation. Prepared
responses cannot be cancelled afterward. Millisecond ties retain the original
conservative in-flight policy. Database integrity hashes are not signatures
against an attacker who can rewrite all records and hashes.

| Alternative | Benefit | Limitation |
| --- | --- | --- |
| Keep logical replay only | Existing model remains usable | Cannot establish physical client availability |
| Owned clocks and separate receipts | Makes lock, preparation and client delays explicit | Requires the pending worker/coordinator and continuity qualification |
| Install sharing in current collectors now | Could reduce duplicate requests | Integration and study-continuity evidence are incomplete |

Success for this component is preserved client intent, clocks observed at their
declared boundaries, unavailable late data and immutable linked receipts. A
backdated arrival, premature delivery claim, duplicate grant, altered provenance
or failed process/replay check would reopen qualification. Rollback is to retain
the previous isolated kernel and stop using this experimental adapter. Current
live code/configuration, collectors and research jobs were not changed by this
work; no profitability or full transport qualification is claimed.
