# Portable reproduction addendum

Correction to the rerun instructions in the
[collection health review](2026-09-10-v89-prospective-collection-health.md):
the first `reproduce.py` compares an archive's absolute retained path as well
as its contents. It reproduces the original in-place evidence, but rejects an
otherwise identical relocated copy. The original audit and numerical results
remain valid. The failed relocated run is retained as `portability_red.log`.

Use `reproduce_v2.py` for a separate evidence copy. Its archive comparison
normalizes only the expected local archive path; membership, byte counts,
SHA256, raw/index first timestamps and all coverage fields must still match.
Collector source/protocol copies are resolved inside the relocated capture
directory rather than read from the original absolute location.

At September 10 09:07 UTC, all 40 copied collector evidence files match their
original bytes. The corrected helper reproduces exactly the original result
for both captures: 11,017 raw requests, 21,776 first timing identities and no
missing or late mature prospective rows. No timing logic, health snapshot,
collector source or economic result changed. High confidence is scoped to
this measured relocation; changed content hashes or different output would
falsify it. The first helper, its archive, review and journal remain unchanged.

To repeat, copy `audit.py`, `timing.py`, `reproduce_v2.py`, `acceptance.json`
and the complete `pair/` and `seven/` directories into a fresh directory.
Do not copy the top-level `reproduction.json`. From that fresh directory run:

```bash
/Users/gestas/Prototypes/hypervector/.venv/bin/python reproduce_v2.py
```

The script creates a new `reproduction.json` and refuses to overwrite it.
This command reads retained artifacts only. It does not start a collector,
contact a venue, inspect market-price values or evaluate a trading outcome.

Evidence remains in
`data/logs/research/bidirectional_cohort/v89_prospective_collection_health_20260910_v1/`:
`portability_acceptance.json`, `portability_red.log`, `portability_green.log`,
`reproduction_copy/reproduction.json` and `reproduce_v2_source.tar.gz`.
The new helper passes Ruff, annotation/docstring and size checks. The unchanged
timestamp module retains its 26-test, 97-statement/44-branch qualification.
