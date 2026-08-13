# Observer Forward-Path Telemetry Plan

**Goal:** Add causal 5/15/30/60-minute signal-path evidence to the disarmed
cohort observer and expose a compact, truthful summary in the TUI without
assuming orders, fills, costs, or PnL.

**Architecture:** Reuse the existing point-in-time provider diagnostics on the
selected observer run. Startup evaluations remain excluded. The rolling
checkpoint carries the report unchanged; Rust strictly projects only aggregate
forward evaluation and five-minute path counts. Execution authority and router
behavior remain untouched.

## Evidence contract

- Forward candles may label a recorded provider state only after its decision.
- Readiness annotations remain separate from eligible signals.
- Overlapping paths expose both resolved and non-overlapping counts.
- No path return is represented as a fill, trade, PnL, or expected edge.
- Sparse results are displayed rather than used as implicit strategy gates.
- Any missing candle or metric coverage remains visible.

## Task 1: Extend the observer audit test-first

- Add failing tests requiring `signal_outcomes` in the observer audit.
- Require startup exclusion, counterfactual-only authority, and a learning state
  that distinguishes signal paths from execution outcomes.
- Reuse `build_provider_forward_diagnostics` on the selected run.

## Task 2: Extend the strict TUI projection test-first

- Add failing parser tests for forward evaluations, eligible signals, resolved
  five-minute paths, independent five-minute paths, and path-data coverage.
- Render a compact observer line with `FWD EVAL`, `FIRE`, and `5M PATH` counts.
- Keep live execution checkpoint parsing unchanged.

## Task 3: Runtime and regression validation

- Restart only the read-only checkpoint sidecar; preserve the observer run.
- Inspect an actual 120x36 render against the live ledger.
- Run focused tests, full non-network Python tests, full TUI tests, Clippy,
  scoped Ruff, formatting, and diff checks.

## Falsifiers

- A startup seed appears in forward evidence.
- A readiness annotation is pooled with an eligible signal.
- The TUI labels paths as fills, trades, PnL, win probability, or edge.
- Adding diagnostics changes a provider decision, routed action, or execution
  authority.
- A missing future candle is reported as a resolved path.
