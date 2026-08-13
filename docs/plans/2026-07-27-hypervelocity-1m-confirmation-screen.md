# Hypervelocity 1m Confirmation Screen

**Status:** Completed serial falsification; no runtime change.

The source-window failure audit found entries where authoritative 5m trend and
1m execution state disagreed. Across all 407 resolved hard/recovery event fills,
however, explicitly opposed 1m states resolved 98 targets/8 liquidations
(92.45%), aligned states 257/26 (90.81%), and non-directional states 13/5
(72.22%). Opposed 1m state was therefore not a general failure marker.

One bounded screen blocked new entries only while 1m was `RANGE`, `TRANSITION`,
or `UNKNOWN`, retaining the 5m classifier, hard BBWP25, recovery-6, 8% target,
and all risk/re-entry rules. It worsened the causal serial path:

| Candidate | Trades | Targets | Liquidations | Final equity | Max drawdown | Source exact |
|---|---:|---:|---:|---:|---:|---:|
| Control | 488 | 450 | 38 | $444,855.97 | -96.41% | 17/35 |
| Block 1m non-directional | 486 | 446 | 40 | $152,000.40 | -97.47% | 15/35 |

The challenger removed more targets, added two liquidations through path
substitution, and reduced source alignment. It did not advance to L2 replay.
This supports retaining 5m authority and treating 1m opposition as pullback
telemetry for ordinary trends; 1m direction confirmation remains required for
5m `BREAKOUT` only. A larger forward sample with repeated losses concentrated
in 1m non-directional entries would update the conclusion.
