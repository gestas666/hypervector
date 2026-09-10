# Original canonical archive layout repair

The canonical history export completed at September 10 01:17:49.745215 UTC:
eight streams, 384 complete daily chunks and 552,960 ordinary checks. Original
session 32156 returned zero. Preserve that completed export; it is not a financial
account result and must not be regenerated to work around a reader defect.

The queued first account attempt, session 87769, returned one before account
simulation. The stack ends in `archive_implementation`: the original canonical
archive contains `source/uv.lock` and `source/scripts/...`, while this reader
selected only root-level `uv.lock`, `scripts/...` and `src/hypervector/...`.
Earlier catalog tests used root-level archives and did not cover that original
export layout. Existing qualified source and failed-run evidence remain intact.

The regression reproduced the same error: one expected success failed and seven
malformed-archive controls passed. The correction recognizes one unambiguous root
or `source/` lock layout, then compares normalized implementation names and exact
bytes. It rejects duplicate locks/files, mixed roots, links, absolute paths,
traversal and unsupported wrapper layouts. It does not extract or execute the
archive being inspected. The original export archive bytes are unchanged.

The repair is frozen as `69dd84a990836c30cd56b1effa524b0e20f88acd` in the isolated
history-storage worktree. Exactly one of the predecessor's 1,924 Python/lock
implementation members changes: `historical_canonical_catalog_evidence.py`.
Account calculations, source data, strategies, costs, clocks and case scope are
unchanged. The archive is 33,585,291 bytes with SHA-256
`c450ed1508e00960a173ea351fb26379f664223e5010567dfd3245be1843119a`.

Validation: 29 layout/catalog tests pass in the worktree (3.69 seconds) and
frozen archive (3.85 seconds), covering 59/62 measured helper statements (95%).
Both real-file preflights authenticate the original complete eight-stream catalog
and all 552,960 checks. Its 1,902 original canonical implementation members match
the exact original export archive after prefix normalization. All 5,552 regular
repair-archive files, executable modes, commit metadata and 1,924 implementation
members were verified before and after archive tests. Ruff, whitespace and
file/function/return-annotation structure checks pass.

Evidence is under `data/logs/research/bidirectional_cohort/`:

- `v89_historical_archive_layout_repair_20260910_v1/`: `source.json`,
  `source.tar.gz`, `preflight.json`, `archive_preflight.json`, `archive_tests.log`
  and `verified.json`.
- `historical_source_archive_layout_red_20260910.log` and
  `historical_source_archive_layout_scope_20260910.log` retain worktree tests.
- `v89_first_complete_historical_account_20260909_v1/run.log` retains the failed
  first attempt and its original immutable operator and launch record.

The new timing attempt uses the same original first/full-prefix/nominal/recorded
clock/control case and full 48-day contract. Its operator is under
`v89_first_complete_historical_account_20260910_v2/`; the check returned zero,
and explicit research run session 91963, PID 62107, started around 01:27 UTC.
Source assembly completed at 01:30:35.349212 UTC in 199.6200859588571 seconds.
At 01:38 UTC the process was active at approximately one CPU core, with roughly
13.5 GiB RSS; the machine has 96 GiB RAM and no swap use was observed. The case
has no completed account result yet. Full-case runtime, output size and resource
use remain unqualified until this attempt and its independent audit finish.

Confidence is high for this bounded archive-layout correction, based on the
reproduced failure, exact original archive inspection, regression controls and
real-file validation from both source copies. Changed source hashes, mixed roots
or catalog disagreement invalidate it. This does not establish strategy
profitability, complete historical matrix outcomes or live readiness. No live
configuration or execution process was changed; both prospective outcome seals
remain intact.
