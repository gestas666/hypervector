# Profile-change fixture chain

Test data only. `profile_a.toml`, `profile_b.toml` and `rollback_b_to_a.toml`
are synthetic cohort profiles routing test-only providers (`test_*` ids,
registered from `tests/conftest.py`). The approvals bind their fingerprints and
sha256 values so the tests can exercise profile-change approval, rollback
authoring, preflight and runtime validation. `rollback_b_to_a.toml` and
`approvals/rollback_b_to_a.json` are exactly what `hypervector.operations.
cohort_rollback_profile` writes for B -> A; regenerate them with that tool
(and refresh `approvals/a-to-b.json`) whenever profile A or B changes.
