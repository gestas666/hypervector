# v25 causal signal context and TUI integrity review

**Observed:** 2026-08-08 20:27 EDT  
**Runtime:** `bidirectional-live-1786182011216`  
**Profile:** `multi_asset_bidirectional_complete_portfolio_canary_v25`

## Problem and success criteria

Screen 6 rejected the otherwise valid v25 checkpoint after two supplemental,
report-only challengers were added. The repair is accepted only if the current
checkpoint parses without a success-shaped fallback, the new signal context is
visible before the long path sections, and neither annotation nor checkpoint
generation can route, size, fill, close, or mutate a live position.

## Root cause and repair

The Python checkpoint emitted two exact research identities that the Rust TUI's
strict forward and candidate-journal allowlists did not yet recognize:

- `hip3_swing_ha_sp500_spcx_bidirectional_v2|xyz:SPCX|pivot_break_state_missing|spcx_swing_pivot_relaxed_fixed60_bidirectional_v1|aligned`
- `hype_breakout_onset_bidirectional_v1|SOL|awaiting_new_5m_breakout_onset|sol_breakout_continuation_aligned_fixed60_bidirectional_v1|aligned`

The allowlists now accept only those exact tuples. The checkpoint projection
also carries a typed `eligible_signal_context` contract, and Screen 6 renders a
compact report-only summary before the longer path diagnostics.

## Evidence

- Immutable source artifact:
  `data/logs/research/bidirectional_cohort/v25_live_prefix_eligible_signal_context_20260808T233605Z.json`
- SHA-256:
  `d436b375ceacfedb925d63743e92be850dfa72d8dc5d8edf540c86e77a1cb216`
- Size: `10,394,256` bytes.
- Coverage: 22 eligible provider signals, 22 causal order-book matches, zero
  missing and zero stale matches, across six provider/symbol identities.
- Contract: `execution_authority=none`, `report_only=true`,
  `routing_or_fill_claimed=false`, `signal_eligibility_changed=false`, and
  `thresholds_selected=false`.
- Direct 160x50 current-checkpoint inspection loaded Screen 6 and showed, for
  GOLD, `SIGNALS 1`, `PRESSURE A1 N0 O0 U0`, unavailable 5m/15m context, and
  `SIGNALS != ROUTES OR FILLS`.
- Full `cargo test -p hypervector-tui` passed with zero failures.
- Focused Python checkpoint validation passed 56 tests.
- `cargo build --release -p hypervector-tui --bin tui-regime-detector` passed.

Only the read-only checkpoint sidecar was restarted. The armed live backend
remained PID 37897 with run count one; its routes, positions, orders, stops,
sizes, and transition state were not changed.

## Limits, failure modes, and falsifiers

Confidence is high for the schema repair and current TUI projection because the
original failure was reproduced, exact identities were tested, and the current
checkpoint was inspected through the rendered TUI. This does not establish an
economic edge. Twenty-two annotations are descriptive, HIP-3 signals do not
have causal 5m/15m regime context in this artifact, and latest-book pressure
does not prove queue position or fill quality.

The assessment is falsified by any repeat of the Screen 6 contract rejection,
a checkpoint/TUI run or profile mismatch, a signal count that does not
reconcile to its provider rows, a signal annotation affecting execution, or a
fresh current checkpoint with nonzero technical faults.
