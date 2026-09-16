# Captured-only later warmup implementation plan

**Goal:** assemble the later study's exact September 9–23 warmup from authenticated
receipts, preserving first/latest knowledge and excluding older seed records.

**Architecture:** extend the existing warmup bundle with its reader identity and
optional authenticated seed evidence. The original eighteen-stream historical
path remains intact. The later path validates its fixed manifest and seed and
has no historical prefix. The source view binds the exact contract and records
how many predecessor receipts are excluded before the later bootstrap.

**Tech stack:** existing Python/SQLite reader, native normalizer fixtures, pytest,
immutable snapshot and source archives. Implement locally in the isolated
`hypervector-v89-prospective-account-20260916` worktree using executing-plans and
test-driven-development. Baseline `5798735`; no running collector/runtime edits.

## Task 1: reproduce actual warmup/source-view rejection

Create `tests/test_allocation_captured_warmup.py` using the real raw ingestion,
snapshot identity and tape builder. Cover missing grids, both first/latest views,
late warmup values, revisions that arrive after study start, no older candles,
funding or metadata, unchanged receipt clocks and payloads. Assert that a full
fourteen-day query preserves missing event identities instead of claiming full
coverage. Add manifest/seed drift, changed dates, booleans-as-integers, missing
seed proof and forged bundle/tape identity cases. Run before implementation;
retain the loader's seam rejection as the expected behavioral failure.

## Task 2: implement exact reader-only warmup

Modify `src/hypervector/research/allocation_warmup_sources.py`: retain
`CaptureSourceIdentity`, validate the exact later warmup declaration, authenticate
the referenced seed and its source snapshot, and return an empty historical
prefix only for the explicitly registered later study. Keep original source
registration/grid validation. Individual warmup gaps remain visible in queries;
manifest acceptance does not claim complete future warmup.

Modify `src/hypervector/research/allocation_source_view.py`: bind exact study and
numeric contract, retain monotone knowledge and completed-market cutoffs, and
exclude pre-bootstrap seed receipts only for the later study. Expose an exclusion
count. Original historical overlap remains an error. No synthetic metadata,
candle or funding fallback. Run new and existing source/assembly/clock tests,
retain failures, verify complete changed-path coverage and code limits.

## Task 3: validate actual retained prefix and freeze

Use the immutable source/tape from the preceding qualified conversion. Inspect
only pre-start data. Query the exact available warmup prefix for all seven
assets and both variants; independently compare native values and clocks from
the authenticated index. A full warmup query must explicitly retain future
missing identities. No provider signals or hypothetical outcomes are computed.
Authenticate the seed/source evidence again and preserve financial/collector
process births. Freeze source, reproduce from its archive, journal and commit.

## Remaining full objective and falsifiers

The complete 24-cell prospective replay still needs its separate clock/account
caller and output provenance. Reuse completed native routing and historical
account components; do not rerun the completed 48-case historical matrix.
Changed fixed dates, evidence hashes, causal selections, missing-data semantics
or original-study behavior reopen this qualification. High confidence is limited
to tested source assembly. No change to economics, seals, live deployment or
automatic promotion is authorized by this plan.
