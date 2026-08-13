# V29 transition-candidate audit

## Outcome

Exact v29 is retired as the default future transition target. Its files remain
available as immutable research and forensic context. Armed v25 remains
unchanged.

Confidence is medium-high for the retirement decision because two independent
conditions hold: the frozen implementation identity has drifted, and the
existing economic evidence does not support the complete six-route mix. This
does not establish that every v29 component lacks edge.

## Verifiable contract

The v29 configuration is internally coherent:

- five assets and five one-position slots;
- six explicit provider-symbol mappings;
- long and short authority on every mapping;
- no observation-only filler;
- isolated 5x execution with per-asset notional ceilings and venue stops.

The configuration SHA-256 remains
`bb62f0cd492bfeb332fd6e53cdd2a45205f3e7b6580fc5f18768ddecee3b40e1`.

## Contradictory economic evidence

The fixed 22.36-day common-window replay reports 97 nominal trades, +$16.52,
PF 1.52, and 98 stressed trades, +$13.64, PF 1.40. Those aggregate values are
not broad route confirmation:

| Route side | Nominal trades | Nominal net |
|---|---:|---:|
| SPCX Swing/HA long | 13 | +$14.85 |
| SPCX Swing/HA short | 23 | -$2.15 |
| ETH pullback, both sides | 23 | -$1.31 |
| SP500 breakout, both sides | 19 | -$1.57 |
| SOL Range Onset long | 2 | +$3.84 |
| SOL Range Onset short | 0 | unavailable |

SPCX long supplied 65.48% of positive nominal route PnL. The common window was
selected after route coverage was inspected and is not an independent holdout.

## Fresh live boundary

The immutable v25 prefix through 2026-08-08T21:16Z contains five resolved
compatible-profile lifecycles. Each route has one trade and every trade is
long. The two routes selected by v29 net -$0.646057. Three profitable routes
excluded by v29 net +$2.816778, but each is a single historically contradictory
observation and cannot establish a replacement edge.

BTC, GOLD, and SPCX remain open in that prefix. Their marked values are
provisional and were not counted as outcomes.

## Implementation identity

Revision 6 froze the live runner at
`693a5e1948602a70e533a87357ff6ba91ff6d03005690830617ab284720084a7`
and its regression test at
`03a78e4c8c33f549f1c3aec74c9261177b357b9a6512c80828747e34a91c8960`.
The current files hash to
`31500a60f9c99fba036969ca5dba6de4a56539c92a82178dc50df82a139dad33`
and
`1b7dc58e2ab4ab5b3aabf88528350a0f8d49b06a193cc173da2b6f1f7452b91a`.
The revision-6 baseline therefore cannot identify a future launch of the
current source tree.

## Required successor evidence

A successor profile must be a new generation rather than an unlabeled v29
refresh. It must bind the current implementation, shared-capital routing,
one-position-per-asset ownership, both-side authority, venue-native protection,
and post-resolution v25 evidence. Route selection must explicitly address:

- SPCX long concentration and losing short behavior;
- negative ETH-pullback and SP500 components;
- absent SOL short evidence;
- the single-trade nature of every current live route result;
- actual IOC friction, funding, maximum-hold behavior, and open-path drawdown.

The retirement decision would be revised by fresh after-cost bidirectional
evidence that resolves those deficiencies. Source parity alone would not be
sufficient.
