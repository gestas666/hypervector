# Rejected snapshot reader: memory attribution

The previous turn was progress: it exposed candidate-specific retained resident
memory under repeated checkpoint publication. Candidate `00237bb` remains
rejected for deployment. No live reporting or execution process changed.

## What the new experiments establish

All experiments use the same eight immutable ledger prefixes, 149,966,790 bytes
total. The rejected candidate and existing reader are preserved in the source
archives from the previous experiment. Requests to sockets and DNS were denied.

Python allocation tracing over three complete snapshot-only cycles measured
40,447 live Python bytes after the final cycle while native RSS was 952,369,152
bytes. Explicit garbage collection reduced live traced allocations to 25,104
bytes, but RSS remained 949,223,424 bytes. A separate process-local Darwin
`malloc_zone_pressure_relief(NULL, 0)` experiment reported zero released bytes
and did not reduce RSS. The installed SDK documents that this call asks every
malloc zone for maximal pressure relief. It was a diagnostic intervention, not
a proposed production workaround.

Four-cycle stage controls then isolated the growth:

| Stages included | Initial RSS | Final RSS |
| --- | ---: | ---: |
| Spool copy only | 259,063,808 | 863,911,936 |
| Copy and hash | 258,883,584 | 863,748,096 |
| Copy, hash, text iteration | 258,588,672 | 863,158,272 |
| Copy, hash, JSON parsing | 259,244,032 | 890,257,408 |
| Existing file JSON parsing | 258,818,048 | 298,926,080 |
| Anonymous mapped copy and hash | 258,129,920 | 263,012,352 |

The mapped-copy control verified all 32 per-file checksums. It copied the same
1 MiB chunks into a bounded anonymous mapping and unmapped each resource after
hashing. Its final three observations were 263,012,352 bytes; no disk writes
were reported for its own process.

High confidence: the growth reproduces in the spool-copy stage without hashing,
decoding, JSON objects, checkpoint construction, or retained report dictionaries.
The tested anonymous mapping avoids this growth at the copy primitive. Low
confidence: the exact underlying allocator/runtime mechanism remains unverified;
the failed pressure-relief experiment does not establish ordinary malloc-cache
retention as its cause. The control is not evidence that a complete mapped
checkpoint reader is correct or ready to deploy.

## Next correction and verification

Implement a private bounded snapshot stream backed by anonymous pages, with an
explicit disk spill above the existing 128 MiB cap. Keep the frozen byte copy,
complete-line handling, raw hash, stream parser, sequence scope, causal cutoff,
and legacy path-projector API intact. Unmap raw pages before yielding rows.
Do not add allocator pressure calls or explicit garbage collection to the
production reporting loop.

Write failing resource/stream tests first. Verify read, append, seek, truncation,
close, rollover, unavailable scratch space, short writes, and corrupt/torn input.
Then run the existing checkpoint regressions and compare complete output on the
same frozen inputs. Repeat both independent-process and same-process measurements;
reject another version if growth remains materially above the baseline control.

Trade-offs: keeping the existing reporter retains its measured copy traffic;
slower reporting would make the TUI staler. A mapped buffer may avoid heap
retention but adds stream and spill code that needs explicit validation. The
larger unrelated filesystem capacity swings remain unattributed.

No deployment approval is requested for `00237bb`. A corrected candidate must
first pass the full tests and repeated-report measurements, then receive the
human approval required by the continuous-agent instructions. Changes to byte
hashes, inconclusive memory controls, or a new retained mapping would update this
assessment. No trading-performance conclusion follows from these experiments.

Evidence root: `data/logs/research/bidirectional_cohort/` in the live checkout.
Groups: `v89_snapshot_memory_diagnostic_{candidate,baseline}_20260908_v1/`,
`v89_snapshot_allocator_relief_20260908_v1/`,
`v89_snapshot_stage_{copy,hash,text,json,file_json}_20260908_v1/`, and
`v89_snapshot_mmap_control_20260908_v1/`.
