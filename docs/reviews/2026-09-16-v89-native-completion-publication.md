# Native research completion publication

High confidence in a reproduced reporting defect: the two research drivers open
their final completion path before serializing its JSON. During that interval,
the existing account handoff sees a file and stops waiting even though its
contents are empty. Subsequent authentication rejects the incomplete JSON; this
is a potential false failure, not evidence of an incorrectly accepted account.
No occurrence has been observed in the running full-length experiments.

The lowest-risk repair is prepared in
`data/logs/research/bidirectional_cohort/v89_captured_provider_assembly_20260916_v1/native_completion_publication_v1/candidate.patch`.
It changes only the two research receipt writers. They first encode through the
existing strict account serializer, then use the existing
`write_immutable_json` helper to write a private file and publish it with an
exclusive hard link. There is no new storage helper or trading rule.

## Evidence and validation

- The unmodified writers failed six behavioral checks: two demonstrations that
  the real handoff reader finishes during serialization, and four demonstrations
  that unsupported/nonfinite input leaves an empty completion file. Two further
  red checks target staging-failure handling in the repair. Six preservation and
  encoding checks already passed. The full red receipt is **8 failed, 6 passed**.
- The repair passed **15 tests**: 14 targeted checks across the two writers and
  the existing storage regression. It preserves previous files and dangling
  symlinks, propagates encoding/staging failures, removes private staging files,
  and retains canonical dataclass, timestamp, byte, path and frozen-set values.
- The same **15 tests passed** using the seven-member frozen candidate archive
  and the existing immutable native-account source archive, with network access
  and credential-file reads denied. The first sandbox attempt stopped before
  tests because pytest could not open `/dev/null`; that failed receipt is
  preserved, and the corrected profile permits that device only in addition to
  the private evidence/temporary write directories.
- Ruff passed for the new test module. Both pinned running driver files retain
  their original hashes. The final verification receipt records these checks,
  archive identities and exact evidence paths.

JSON formatting changes from compact to indented output. Canonical decoded
values remain equal, but future receipts necessarily receive new byte hashes.
This is not a general crash-durability or filesystem-power-loss qualification.
It also does not establish native account correctness, a trading edge or live
profitability; the full source and account comparisons remain separate work.

## Recommendation and boundaries

Use the qualified atomic writers in the next separately versioned research
driver. Preserve the currently running experiments and their pinned source,
requests, manifests and output directories. No job is restarted to adopt this
change. If an actual publication race terminates a research handoff, inspect its
terminal result and authenticate the completed source before preparing a new
handoff; retained native decisions must not be discarded or recomputed merely
because the reporting consumer failed.

| Alternative | Benefit | Cost or limitation |
| --- | --- | --- |
| Keep the current frozen runs | Preserves evidence identity and ongoing computation | Their completion writers retain the reproduced race |
| Atomic publication in a future version | Readers see a complete receipt; previous evidence stays exclusive | New driver and receipt hashes must be registered |
| Reader retries alone | May tolerate an in-progress file | Must distinguish incomplete publication from permanently corrupt evidence; does not prevent the empty marker |

The expected upside is fewer avoidable research handoff failures. There is no
proposed live strategy, asset, sizing, leverage, execution or deployment change,
and no additional live approval is requested. Existing unrelated approval
questions remain pending.

Success means the final path stays absent until its complete JSON is available,
all prior evidence remains intact, and the existing reader accepts the final
document. An early-visible final path, changed canonical values, overwritten
evidence, suppressed error or failed future integration would reopen this
repair. Previous source copies and the exact patch are retained for rollback
of a future research installation; the running source was not changed.

During this review, both passive watchers reached an actual new Brent entry at
12:00 UTC. Native fill, leverage, stop coverage and signal reconstruction are
the next investigation; these observations do not alter the frozen prospective
study dates or qualify an open trade's eventual outcome.
