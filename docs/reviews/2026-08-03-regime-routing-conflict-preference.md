# Regime routing conflict preference — 2026-08-03

## Problem and operational boundary

The canonical regime engine already participates inside Range Onset, BTC Source
Follow, and HYPE Breakout signal generation. Hulk remains an independent signal
provider. The weighted context on Screen 9 was report-only and therefore did
not resolve simultaneous same-coin provider disagreements.

The staged change gives causal 1m/5m/15m structure one narrow execution role:
ranking conflicting intents for the same coin. It does not reject a standalone
intent and does not create a regime-only exit.

## Exact policy

Each routable intent receives a score in `[-1, +1]` relative to its side from
the latest completed canonical evaluation:

| Canonical input | Weight |
|---|---:|
| 1m execution state | 1 |
| 5m primary state | 3 |
| 15m context state | 2 |

`TREND_UP` and `TREND_DOWN` contribute direction, `RANGE` and `TRANSITION`
contribute zero, and `BREAKOUT` uses the backend structural direction. A score
at or above `+0.5` is supportive; at or below `-0.5` is opposed; the middle is
mixed/transition.

For two or more same-coin intents, score ranks first, configured provider
priority second, and decision time third. Therefore the policy can choose an
entry or choose an opposite-side intent that closes an open position. A lone
intent remains routable even with a negative score. Forced regime exits remain
off.

## Persistence and visibility

The intent, action, decision journal, and TUI projection retain the score,
stance, canonical decision time, and basis
`canonical_1m_5m_15m_1_3_2_v1`. Screen 2 shows `REGIME BIAS` for selected and
withheld outcomes and states `CONFLICT REGIME PREF // LONE UNGATED // FORCED
EXIT OFF`. Incomplete routing preference records fail Rust projection rather
than rendering a success-shaped value.

## Deployment state and validation

The implementation is staged, not active in the backend process started before
this code existed. At the final check, BTC/ETH/SOL were flat, HYPE remained
open and venue protected, the heartbeat was current, and there were no faulted
assets. The order backend was deliberately not restarted mid-lifecycle.

- Python no-network suite: 3,096 passed, 4 deselected.
- Rust TUI suite: passed in full.
- Strict Rust Clippy: passed.
- Touched Python files: Ruff and format checks passed.
- Repository-wide Ruff retains 33 unrelated legacy findings.

Confidence is high in causal attachment, deterministic ranking, persistence,
and display because exact unit/integration tests cover them. Confidence is low
in economic improvement because no conflict-outcome sample exists yet. A
decision timestamp after route time, a lone intent withheld for regime, a
regime-only forced close, or forward conflicts where the regime-preferred arm
underperforms static priority would falsify or downgrade the policy.
