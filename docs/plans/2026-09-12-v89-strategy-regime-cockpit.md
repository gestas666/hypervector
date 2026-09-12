# Strategy and regime monitoring repair

The user explicitly requests an updated TUI for tracking, monitoring and planning strategy indicators and their corresponding regimes. The prior hold-visibility candidate is committed as `4e8d7a8`; its separate 51-frame native acceptance and archived-source tests remain evidence for that version.

Observed defects in the native stopped snapshot: the hourly SNDK provider publishes `signal_timeframe=1h` and `source_timeframe=15m`, but the chart uses the configured 15m source as its decision timeframe. Setup AGE reports arrival-minus-decision latency rather than current evidence age. Strategy inspectors lack a separate causal canonical context when the provider's own regime fields are absent.

Implement display-only repairs:

1. Use the matching evaluation's backend signal-timeframe metric for chart aggregation and title; retain the configured source timeframe separately. Missing legacy metrics use the configured timeframe; malformed explicit metrics remain unavailable.
2. Label arrival lag and elapsed evidence age separately. Label stored indicator values as recorded. Preserve all existing screens, controls and scrollable evidence.
3. Add configured entry/exit/risk plan and canonical context to the existing strategy evidence inspector. Join only the same coin and canonical provider, with both decision and observation clocks no later than the strategy evidence. Report missing retained history explicitly. Show latest recorded canonical context separately with its own timestamp and age. Do not substitute canonical context for a provider's own entry rules.
4. Test hourly aggregation, exact provider identity, missing/malformed metrics, stale/future clocks, causal joins, and reachability at 100x28, 120x36 and 190x52. Reuse the current source snapshot for native inspection of all seven strategies and all three regime pages.
5. Validate the final source, archive and release binary; preserve and document rollback. Install the read-only monitor update under the user's explicit instruction. Do not change live configuration, strategies, risk, orders or start trading.

High confidence in the reproduced display defects. A signal/source mismatch, borrowed provider evidence, a future regime joined to an earlier decision, clipped required data, or failed installed-source parity would falsify completion. This work does not establish predictive validity or live profitability. Current execution remains stopped; recorded market data remains dated until an authorized source updates it.
