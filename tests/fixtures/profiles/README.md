# Test fixture profiles

Test data only. Every cohort profile here routes synthetic, test-only signal
providers (`test_*` ids) that `tests/synthetic_live_providers.py` registers from
`tests/conftest.py`; nothing in `src/` knows them. HIP-3 symbols are neutral
placeholders (`xyz:AAA` ... `xyz:FFF`). The profiles exist to exercise the
generic loader, validation bounds, execution plans, sizing, stops, exits,
ledgers, restart, checkpoint and audit paths. They carry no strategy and no
evidence; do not use them as a template for a live profile.

The `hypervelocity_*.toml` files are test inputs for the paper/strategy tests
owned outside the live cohort.
