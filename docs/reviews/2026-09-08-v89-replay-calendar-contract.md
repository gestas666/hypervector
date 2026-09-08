# Allocation replay calendar adapter qualification

Source `57bd710e05280422b0507308df226ffa0b86b384` adds an isolated research
adapter in `src/hypervector/research/allocation_replay_contract.py`. It composes
the existing `ReplayWindow` without changing that shared component or the
running collectors. This is one qualified component; the full prospective
replay remains unqualified.

High confidence in the observed contract behavior: **22 tests passed**, comprising
20 new adapter cases and two existing window regressions. The new module has
**57/57 statements and 22/22 branches covered**. Ruff and the 500-line/file,
50-line/function, four-level indentation and explicit annotation checks passed.
No strategy outcomes or source prices were evaluated.

The prospective factory keeps September 9–23 UTC, the September 16 split,
August 26 warmup start and $4,857.58724349 model capital. It rejects evaluation
through this contract before the exact September 23 end. The historical factory
keeps July 21–September 7, the August 18 split and July 7 warmup start. A shifted
synthetic calendar crosses a year boundary without inheriting those dates.
Source timestamps are bounded by the declared interval; a terminal mark may
include the end while an end candle/funding event may not. Ambiguous timezones,
non-midnight calendar bounds, empty partitions, malformed capital and wrong
warmup/seal boundaries fail explicitly.

Validation artifacts are in
`data/logs/research/bidirectional_cohort/v89_equal_cap_replay_qualification_20260908_v1/`:
`contract_red.log`, `contract_acceptance.log`, `contract_coverage.json`,
`contract_qualification.json` and frozen implementation/test copies.

The future entry point must authenticate the frozen study/config/cost/source
artifacts and invoke the seal before source-price or strategy processing. This
adapter alone cannot enforce that behavior throughout unfinished replay code.
Provider parity, receipt/entry-clock mapping, dynamic shared equity, rounded
quantities, cash reservations, native funding timestamps and terminal open
positions still require implementation and independent qualification. Exact
historical path/accounting reproduction has not been claimed from these date
checks. Failing any of those broader checks would prevent replay qualification.

Next: bind authenticated inactive profiles and cost/source identities, then
qualify incremental account arithmetic against hand-calculated fixtures and
registered historical controls. Keep the source-collector files unchanged and
both prospective outcome seals intact. The parent continuous goal stays active.
