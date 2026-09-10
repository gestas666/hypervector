# Initial complete historical account comparisons

At September 10 04:12:35 UTC, three original cases are complete and independently
reconciled. These are descriptive progress results from July 21 through September
7 UTC, not a completed 48-case assessment or evidence of future profitability.
The earlier/later segments were previously available history, not new holdouts.

| Nominal-cost case | Net equity change | Maximum marked drawdown | Earlier 28 days | Later 20 days |
| --- | ---: | ---: | ---: | ---: |
| Control, recorded clock | +$196.85 / +4.05% | $140.67 / 2.74% | +$214.58 | -$17.73 |
| Equal allocation, recorded clock | +$491.17 / +10.11% | $264.87 / 5.05% | +$482.30 | +$8.87 |
| Control, late exit clock | +$196.85 / +4.05% | $140.67 / 2.74% | +$214.58 | -$17.73 |

All three cases contain the same 177 completed trade identities, with 74 winners,
103 losers, no remaining open trades, 41.81% wins and 3.6875 entries per calendar
day. The recorded allocation pair has identical entry prices and exit timestamps.
One exit price differs by approximately 2.27e-13, consistent with floating-point
rounding at the larger quantity; this numerical difference is retained rather
than described as exact price equality.

Equal allocation increases average gross notional from $874.23 to $1,766.75,
a 2.0209 ratio, while marked drawdown rises by $124.20. Its three largest winners
contribute $490.90; removing them leaves $0.27. The corresponding control result
without its three largest winners is -$31.83. High confidence applies to these
bounded calculations. They do not establish improved signal selection, a larger
win probability or a dependable live advantage.

| Asset | Completed trades | Control net | Equal-allocation net |
| --- | ---: | ---: | ---: |
| BTC | 3 | +$6.36 | +$2.73 |
| ETH | 3 | -$8.39 | -$17.98 |
| SOL | 5 | +$3.80 | +$8.16 |
| HYPE | 6 | -$46.22 | -$19.80 |
| xyz:SPCX | 52 | +$58.41 | +$125.27 |
| xyz:SNDK | 47 | +$131.71 | +$283.21 |
| xyz:BRENTOIL | 61 | +$51.17 | +$109.59 |

The non-crypto assets contribute approximately +$241.30 of the control result;
the four crypto assets contribute approximately -$44.44. Small individual crypto
samples and concentration in a few non-crypto winners limit interpretation.
This is not a recommendation to remove crypto or change allocations.

The nominal control clock comparison retains the same entry and exit prices.
It shifts 56 exit timestamps by 899,999 ms and 12 by 59,999 ms; 109 remain
unchanged. Its average gross exposure rises by 0.727%, while total return and
maximum marked drawdown remain equal in this case. This only tests the explicitly
modeled clock convention, not arbitrary live latency or venue fill behavior.

Verification authenticated 2,303 unique report/provenance references across the
three cases, matched fresh and retained independent audits, and reconciled seven
equity totals per case. The ledger audit does not independently validate historical
source-price selection or native routing. Changed source identities, audit
disagreement or nonconserved contributions would invalidate these calculations.
Adverse costs, other registered source variants and the remaining clocks may
change their practical interpretation.

The highest-value next step is the original adverse-cost comparison, already in
the active full matrix. Preserve all 48 cases; do not change the matrix after
observing these three results. Both prospective outcome seals remain intact.
No live strategy, sizing, risk, execution or deployment changes are made.

Evidence: `data/logs/research/bidirectional_cohort/`
`v89_initial_historical_account_comparison_20260910_v1/verified.json` and its
retained `verify.py`; complete underlying reports are explicitly pinned there.
