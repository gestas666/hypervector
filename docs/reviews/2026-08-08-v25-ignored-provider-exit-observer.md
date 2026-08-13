# v25 ignored provider-exit observer acceptance

## Problem restatement

v25 intentionally ignores provider recipe-exit signals for the currently bound
HIP-3 contracts. Before this change, the checkpoint exposed the policy but did
not bind the first ignored signal to the exact open lifecycle or measure the
completed-bar path that followed it. That made later exit-policy analysis
dependent on manual ledger rescans and increased attribution risk.

The acceptance requirement was to retain causal evidence without changing any
live entry, exit, sizing, stop, timer, or arbitration rule. Evidence is stored
at
`data/logs/research/bidirectional_cohort/v25_ignored_provider_exit_observer_acceptance_20260808T1306Z.json`.
Its SHA-256 is
`be8e5449947c8a683c8441913b00da802ccb6d9fc89ea1c4a60720f3ece5cc9e`.

## Implemented contract

For every open lifecycle, the report-only checkpoint now publishes one of
three explicit states:

- `observed`: first post-fill, same-side provider exit plus its causal path;
- `no_ignored_exit_observed`: policy is `ignore`, but no eligible signal has
  occurred;
- `not_applicable_policy_honors`: the provider policy executes recipe exits,
  so an ignored-exit observer is not applicable.

Pre-entry, opposite-side, and future signals are excluded. An observed record
requires both the first signal and its path. The Rust projection rejects
partial records, non-finite economics, inconsistent policy/status shapes, or
any contract that claims execution authority. Legacy checkpoints that omit the
entire observer remain readable.

The regime cockpit shows the provider entry relation and ignored-exit outcome
on compact layouts. Wide layouts additionally show the full signal reason,
reference price, entry-relative return, subsequent directional return, and
signal count.

## Actual v25 evidence

The open `xyz:GOLD` long lifecycle produced the first useful observation:

- strategy: `hip3_swing_ha_sndk_gold_brent_bidirectional_v1`;
- entry: `4354.3`, size `0.0172`;
- first ignored signal: `hip3_swing_ha_flip` at `4344.7`;
- signal position relative to entry: `-22.05 bps`;
- ignored signal count at acceptance: `7`;
- completed bars since the first signal: `140`;
- current directional path from the signal: `+2.53 bps`;
- MFE/MAE from the signal: `+7.60 / 3.45 bps`;
- checkpoint mark: `4345.8`;
- active lifecycle marked net PnL: `-$0.214942`.

The signal would have exited below entry, but the sampled market later traded
slightly above the signal reference. This is one unresolved path, not proof
that ignoring the HA flip is profitable. Final comparison still requires the
actual venue close, exit fee, funding, and slippage.

ETH, SOL, and SPCX correctly reported `no_ignored_exit_observed` at the same
checkpoint. No success-shaped synthetic path was generated for them.

## Validation

- 53 focused Python lifecycle, audit, and checkpoint tests passed.
- The complete Rust TUI library and integration target set exited with code 0.
- Strict negative tests reject partial observed records and execution-bearing
  observer contracts.
- Ruff, Python format, and Cargo format checks passed.
- The actual refreshed checkpoint parsed in the real monitor; the monitor
  exited cleanly.
- Only `com.hypervector.v25.checkpoint` restarted. The live owner remained PID
  `37897`, launch count one, and never exited.
- The four open positions retained exact stops `512630700867`, `512630736897`,
  `512544517709`, and `512769547957`; the checkpoint reported zero faults.

## Uncertainty and decision boundary

Confidence is high that signal attribution, strict projection, execution
isolation, and cockpit rendering work for the observed payload. Economic
confidence is low because GOLD is unresolved and one path cannot identify an
exit edge.

The mechanical assessment would be falsified by lifecycle leakage, TUI
rejection of a valid payload, acceptance of a partial payload, execution-owner
restart, or missing stop. The policy assessment should change only if resolved
after-cost forward lifecycles consistently show that honoring a defined signal
outperforms the frozen timer/stop/opposite-intent path. Until then, this observer
is evidence collection, not an automatic strategy mutation.

