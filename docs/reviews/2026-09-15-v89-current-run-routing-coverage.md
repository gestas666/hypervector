# Current-run publication and routing coverage

High confidence in the recorded coverage and routing dispositions within this
frozen interval. All 713 provider evaluations follow their configured source
publication grids. Two eligible publications have two corresponding durable
intents and two explained outcomes: one SPCX entry and one SNDK same-side
position hold. No eligible publication is unaccounted for by the recorded
router in this sample. This does not establish that every upstream signal was
calculated correctly or that the strategies have profitable expectancy.

## Source and interval

Run `bidirectional-live-1789497016143`, configuration recorded September 15
18:41:51.993041 UTC through the selected cohort snapshot at 22:20:09.776771 UTC.
The authenticated native interval spans sequences 605439 through 609357.
All 3,919 native rows in that interval were scanned. All 1,741 selected
configuration/routing/intent/snapshot rows exactly match the research index and
their original native byte ranges. Empty routing publications are included.

The selection contains 869 routing events, of which 220 contain evaluations,
869 cohort snapshots, one configuration and two durable strategy intents.
Initial warm-start source boundaries precede configuration time: BTC starts at
18:00 UTC, the XYZ providers at 18:30 and minute providers at 18:41. These are
explicit startup observations, not claims of pre-start trading activity.

## What the providers reported

| Asset | Source publication cadence | Evaluations | Eligible | Reported unmet conditions |
| --- | --- | ---: | ---: | --- |
| BTC | 1 hour | 5 | 0 | Close below EMA55 in all five; other sweep/volume blockers overlap |
| ETH | 1 minute | 220 | 0 | Hourly SMA cross absent in all 220; 5m regime not admitted in 215 |
| SOL | 1 minute | 220 | 0 | Hourly SMA cross absent in all 220; 5m regime not admitted in 211 |
| HYPE | 1 minute | 220 | 0 | Canonical breakout onset absent in 219; remaining evaluation reports absent authoritative 5m compression |
| SPCX | 15 minutes | 16 | 1 | One hourly entry, three hourly exit publications, twelve other no-entry evaluations |
| SNDK | 15 minutes | 16 | 1 | One hourly entry publication; fifteen without an entry condition |
| BRENTOIL | 15 minutes | 16 | 0 | Sixteen evaluations without an hourly setup |

Source publication cadence is not entry cadence. The XYZ recipes use completed
hour signals while publishing on their 15-minute input grid. Minute evaluations
can repeatedly report the same unmet hourly/5m condition. Blocker counts overlap
and are not separate rejected trades or independent statistical trials.

For each provider, the exact ordered decision-time grid matches its configured
timeframe from the startup boundary through the frozen observation cutoff.
There are no duplicated or missing source-clock publications in that interval.
Independent SQL agrees with all seven per-provider count/eligibility/time-range
summaries and independently counts the same distinct clocks.

## Eligible publications and existing-position evidence

At 19:00 UTC, SPCX published an eligible long and generated the recorded entry
action. SDK-dispatch age is 19,432 ms against its configured 30,000 ms limit.
Its canonical alignment is directionally opposed, yet the standalone intent is
dispatched under the recorded ungated policy. This observation supports absence
of a canonical-alignment veto for that entry; it does not qualify every possible
strategy or execution path. The separate SPCX entry audit already reconciles
its native fill and protective stop and is not repeated here.

The simultaneous SNDK short is recorded as `same_direction_position_open`.
The immediately preceding snapshot, sequence 605764, shows the inherited short
of 0.326 units, state `OPEN`, entry order 545845583477. The configuration permits
one position per symbol. Thus the withheld reason is supported by recorded
position evidence; it is not a missing router disposition or a new implicit
performance gate. Snapshot evidence is not a claim about every instant between
venue observations.

## Validation and limitations

Seven corrupted copies are rejected: missing entry disposition, missing withheld
disposition, wrong held side, missing ETH publication, wrong action clock,
wrong alignment attribution and late SDK dispatch. The first analysis harness
incorrectly constructed `Counter` from a mapping, treating intent payloads as
counts. It was corrected to count mapping keys; the initial source and failure
are preserved. This was an audit-code error, with no installed production change.

All 1,741 selected records were independently reauthenticated against original
native byte offsets after the analysis. The complete projection and manifest,
validator, failed initial attempt, seven controls and independent SQL results
are retained under
`data/logs/research/bidirectional_cohort/v89_current_routing_audit_20260915_v1/`.

No new strategy, sizing, leverage, risk, source, runtime or order action is
warranted by this routing sample. Observing few eligible signals does not show
that their future win rate or payoff will be high. The upstream initial candle
cache remains unretained, so this audit cannot independently reconstruct every
indicator or detect all upstream false negatives. The band-history correction
is installed on disk but remains inactive in the existing process.

A native/index disagreement, missing publication, unmatched eligible intent,
unjustified withholding, changed evidence hash or contrary execution receipt
would reopen this conclusion. The highest-value next evidence remains a new
native lifecycle/protection/fault event, followed by exact startup-input and
source verification after the next user-controlled backend start. The existing
watcher remains bounded through approximately 22:39 UTC. Prospective outcome
seals remain unopened; no financial process control was performed.
