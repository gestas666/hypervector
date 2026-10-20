# Profile-change fixture chain

Test data only. `profile_a.toml`, `profile_b.toml` and `rollback_b_to_a.toml`
copy the values of retired live profiles so the tests can exercise approvals,
rollback authoring and runtime validation. Those strategies failed. Never use
these files as a template or starting point for a new profile.
