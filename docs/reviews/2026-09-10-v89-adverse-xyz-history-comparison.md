# Original adverse-cost XYZ history comparison

The original full-prefix versus rolling-fourteen-day XYZ comparison preserves
all 177 ordered trades, entry prices, exit times, quantities, holding periods,
funding and capital exposure in both allocations. The outcomes are not exactly
identical: 26 modeled stop exits retain slightly different source anchors. The
resulting account difference is less than $0.000003 per allocation across the
48-day historical window. This supplies no economically material reason to
change the history window in these cases.

Confidence is high for these authenticated, bounded observations. They do not
establish profitability, live fill behavior or invariance in other histories.
Changed source identities, differing non-history settings, an unexplained cash
residual or different trade selection would update the corresponding conclusion.

## Fixed scope and measured results

Compare original cases 4/16 and 5/17: first core observations, adverse costs,
recorded-bar exit timing and each allocation fixed. Only XYZ provider history
changes from the full available prefix to a rolling fourteen-day window. The
window is July 21 through September 7 UTC, with a fixed August 18 split.
Cases 16/17 were already complete; their account analyses completed at 10:13:55
UTC on September 10 using unchanged qualified reporter `3400457`. Native replay
was not repeated. The two report jobs and comparison job exited successfully.

| Allocation | Full-prefix net | Rolling net | Rolling minus full | Maximum drawdown, full / rolling |
| --- | ---: | ---: | ---: | ---: |
| Control | $95.7185549453 | $95.7185536965 | -$0.0000012488 | $198.2769053644 / $198.2769059171 |
| Equal | $368.9171018911 | $368.9170992130 | -$0.0000026781 | $287.7198324834 / $287.7198341840 |

Each case has 177 accepted, closed entries, 72 wins, 105 losses and no open
terminal trades. Average gross exposure stays $872.6029273474 for control and
$1,765.7583473242 for equal. Reported proposal dispositions are byte-identical.
The other four economic sections differ because their cash and price values
retain the small differences rather than rounding them away. Both later
segments remain negative; this comparison does not resolve that weakness or
the separately documented higher-fee sensitivity.

## Source-to-cash explanation

Twenty other manifest fields match, including all seven route descriptions.
Execution settings, funding and execution-price sources are unchanged. Each
manifest has 2,277 references: 2,133 shared references keep identical identities,
while 144 daily provider files switch between the declared history variants.
Those bindings cover the exact three XYZ symbols and all 48 original dates.

Within each allocation, the 26 affected exits comprise six SPCX, eight SNDK and
twelve Brent stops. Only valuation price, gross PnL, exit fee and net PnL change
in their complete trade contributions. The largest exit-price difference is
$0.0000020703. No trade is added or removed, and the other contribution fields
match exactly.

An independent trace authenticates 44 retained provider files and resolves all
affected entries to their original publications. Their raw intents differ only
in the stop anchor. Each anchor reproduces the modeled exit price with the
unchanged 5.5-basis-point exit slippage. Fixed quantities, directions and exit
fee rates reproduce every changed gross, fee and net cashflow. The largest
arithmetic residual is 2.28e-13; summed changed-trade cash reconciles to the
portfolio difference within 1.34e-12 dollars. This traces model inputs and
arithmetic, not executable venue ticks or actual historical fills. The detailed
trace retains ATR values and source lengths but does not independently rederive
the indicators.

The earlier September 9 zero-difference provider checks compared each variant
against its own archived/native reference. They did not establish exact numeric
equality between full-prefix and rolling-history anchors. That earlier review
also recorded equal intent counts with differing complete payload hashes. This
account comparison extends that evidence rather than overturning it.

## Validation and retained decision

All 2,464 unique report references authenticate. Each case conserves seven
equity totals and its fresh independent accounting agrees with the retained
audit. A separate canonical-byte comparison confirms the exact scope of
economic equality and inequality. Ten focused tests verify that the comparison
accepts the history-only contrast and rejects changed settings or endpoints.

The first two test commands failed imports because repository pytest settings
selected the installed source. Those failures are retained and supply no axis
validation. The isolated test configuration exercises the frozen reporting
source: the prior core-axis helper fails the new contract, and the adapted
history-axis helper passes all ten tests. Ruff and the recorded source-structure
checks pass. Twelve archived source/provenance files match their original bytes.

Retain this result without changing the history setting. The alternative of
choosing a window by these sub-cent differences adds selection risk without
measured benefit here. Finish the original 48-case report before drawing a
matrix-wide conclusion. Existing initialization gaps, hybrid historical
provenance, conditional missing-minute execution prices and modeled fill
assumptions remain limitations; neither extra history nor this partial result
removes them.

No live strategy, allocation, risk, execution, deployment or TUI change was made.
Both prospective outcome seals remain intact. The complete matrix remains
required; this is four predeclared historical cases, not a new holdout.

Evidence root: `data/logs/research/bidirectional_cohort/`
`v89_adverse_xyz_history_comparison_20260910_v1/`.
