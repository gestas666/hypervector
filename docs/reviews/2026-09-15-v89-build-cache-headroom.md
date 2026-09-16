# V89 build-cache headroom and bounded research-journal verification

The data volume reported **25 GiB available and 98% capacity** during the
September 15 storage check. Two inactive Rust incremental caches offered a
bounded cleanup that preserved trading evidence and installed executables.
The user's earlier drive-cleanup request authorizes this operational work.

## Applied scope and verification

Only these generated cache directories were cleared:

- `/Users/gestas/Prototypes/hypervector/target/debug/incremental`
- `/Users/gestas/Prototypes/hypervector-v89-native-account-replay-20260912/target/debug/incremental`

The snapshot retained hashes, sizes, permissions, inode and modification-time
evidence for **21,897 files**, representing **5,430,030,785 logical bytes**.
No Cargo or Rust compiler process was observed during the required preflight
checks. The cache directories were backed up before any move or removal.

The retained archive is
`data/backups/build_cache_cleanup/20260915T233304Z/incremental-caches.tar.zst`,
**1,689,844,989 bytes**, SHA256
`5ce661aec58f4dcde0e757500d1246fb366c3f7eaf86442e52eeb27aef34a2e3`.

A complete native restore authenticated every file's bytes, size and permissions
against the manifest. The original cache trees were then independently checked
again for exact file membership, bytes and unchanged inode/mtime identities.
Only after those checks passed were the two cache directories moved to bounded
quarantine names and removed. The temporary verification restore was also
removed; the compressed backup, manifest and verification receipts remain.

The first streaming archive check rejected an additional `._incremental` entry
created by the native archive tool. The initial verifier and failure log were
preserved. A full native restore replaced that check and passed all **21,897**
file comparisons; no failed verification was treated as permission to delete.

Three installed TUI hashes and the active V89 profile hash match their retained
identities before and after cleanup. Financial-session PIDs **29190, 29191,
30603, 62016 and 62017** retain their recorded birth times. The native backend
published a `running` heartbeat at **23:42:56.249301 UTC** after cleanup.
Source, compiled executables, dependency artifacts, prior versions, journals,
native ledgers and historical market evidence were preserved.

## Observed space and limits

Available bytes increased from **26,907,688,960** before backup creation to
**28,564,631,552** immediately after cleanup: **1,656,942,592 bytes**, about
**1.54 GiB net**, with the compressed backup retained. The later verification
reported **26.60 GiB available** and a **1.539 GiB** increase from the original
baseline. These are observed filesystem measurements. Concurrent writes and
shared filesystem blocks were not isolated; logical cache sizes are not an
exact prediction of physical space recovered.

Headroom remains limited. This is a scoped improvement, not a claim that the
drive's storage pressure is fully resolved. No further dataset, source archive,
global cache or unrelated project was removed.

## Research-journal memory repair

Preparing the backup's journal entry exposed an implementation defect:
`portfolio_research_journal.py` loaded each evidence artifact entirely into
memory for both append and report. That would allocate the entire retained
**1,689,844,989-byte** archive. Six failing regressions reproduced the unbounded
read through the public journal APIs before the implementation changed.

Both artifact checks now reuse `oxa_storage.file_evidence`, which hashes in
**1 MiB chunks**. SHA-256 and byte-count validation, immutable revision identity,
missing/changed reporting and explicit I/O failures retain their existing
contracts. The small JSON record and canonical revision hashing are unchanged.
This changes one research module; it does not change trading logic or control
any financial process.

The candidate and installed checkouts each pass **19 focused tests**. Coverage
records **205/225 statements (91.11%)** for the journal module, with every
statement in the two changed functions executed. Checks include empty and
multi-chunk files, final-chunk corruption, incorrect byte counts, missing
evidence, permission errors, idempotence, chain integrity and CLI behavior.
The initial module-selected coverage invocation failed during NumPy import;
file-pattern selection completed successfully. That failure log remains evidence.

The actual retained archive passed append and report in separate private probe
databases from both checkouts. Installed peak traced Python allocations were
**2,108,587 bytes** for append and **2,241,076 bytes** for report, both below the
predeclared 16 MiB limit. These measurements start after imports and exclude
native DuckDB allocations; they are not whole-process RSS claims. The checked
source SHA256 is
`41b12cbdb7ca5efd9c5654549157b1d115474bec9f7022fe75c606aeac3662aa`.

The pre-change source, tests, final source, patch, logs, coverage and real-archive
probes are retained under the evidence directory's `journal_memory/`. The
reverse patch passed `git apply --reverse --check`; it restores the prior
research module and removes only the new test. Inspect subsequent changes
before applying it. No running backend restart is required for new research
CLI processes to use this correction.

## Historical evidence references

Two prior SNDK research revisions referenced the mutable journal source file.
Their new revisions resolve it to identical authenticated pre-change bytes.
Verification of the stateful entry also found four previously drifted source
references. Their original bytes were recovered from Git and matched against
the original hashes; the current live source was not reverted.

The full-execution revision now has **3,372 matching references**; the stateful
revision has **3,620 matching references**, with none changed or missing in
either current revision. Prior revisions remain intact and truthfully retain
their old mutable references: historical reports show one changed reference
for the full-execution original and five for the stateful original. The failed
stateful append that exposed the older drift is retained. Underlying strategy
results, confidence and recommendations are unchanged; these experiments were
not rerun or reopened.

The replacement revisions are `c8c83fd11889fd6f8befeb935319826cf660e083084ffe979a208cf374cc8092`
and `a12b3ff9324ecdfe7efd29b8c3ac2661a3412cb43bbbd71b2170119975e71052`.

**Recommendation / why now:** retain this reversible cleanup because it adds
measured writing headroom without changing trading behavior. It applies
independently of market regime. Keeping the caches would preserve incremental
build speed; clearing them means a later Rust build may take longer and recreate
the cache. Retain bounded journal verification to avoid artifact-sized Python
allocations. Keeping whole-file reads is simpler but scales memory with archive
size. No trading-performance or profitability improvement is claimed.

**Approval / proposed live change:** existing corrective technical and cleanup
authorization covers this work. No live strategy, asset, route, sizing, leverage,
risk, execution or deployment setting was changed. No further approval is
requested for these completed research and storage corrections.

**Rollback:** the archive's complete restore has been tested. With Rust builds
idle, extract into a new empty directory using the recorded native restore
command with a new destination. Inspect any regenerated caches before moving
restored content into a workspace; do not overwrite subsequent user work.
Normal builds can also regenerate these caches from source.

**Confidence / success / falsifiers:** high confidence in the retained backup,
file-byte comparisons, protected identities and measured space increase.
Changed archive hashes, missing source members, altered protected executables,
unexpected process identity changes or loss of the observed space gain would
require reinspection. The historical source paths in the manifest are expected
to be absent after this documented cleanup. A missed tail corruption, changed
revision identity, swallowed I/O error or artifact-sized allocation would reopen
the journal repair. Immutable artifacts remain an assumption; this correction
does not add filesystem snapshot isolation during concurrent file mutation.

**Next investigation:** continue the same lifecycle observer (PID 17371,
session 27304) and diagnostic observer (PID 67653, session 82480). Inspect their
first real event or actual deadline receipt. No financial process control or
live policy change occurred. Prospective seals remain unopened.

Operational receipts are in the backup directory; the later native/process/
space verification is under
`data/logs/research/bidirectional_cohort/v89_build_cache_headroom_20260915_v1/`.
