# SPCX pivot challenger first prospective resolution

Date: 2026-08-08

## Problem restatement

Evaluate the first post-cutoff result from the frozen report-only SPCX
pivot-state relaxation without confusing counterfactual entry quality with an
actual shared-portfolio trade. The candidate removes only
`pivot_break_state_missing`, requires aligned side-adjusted visible-book
pressure, and uses a fixed 60-minute adverse-BBO replay with an 80-bps stop
proxy.

## Result

The first non-overlapping post-2026-08-08T16:00:00Z candidate was long:

- reference decision: 2026-08-08T19:45:00Z;
- directional OPI: +0.19344;
- estimated entry: 138.14;
- stop-proxy exit: 136.99;
- gross return: -83.2489 bps;
- fees: 8.6040 bps;
- funding: -1.3655 bps;
- net return: -93.2184 bps;
- MFE: -1.4478 bps;
- MAE: -83.2489 bps;
- result: 0W/1L, PF 0, one stop-proxy cross.

The path never became favorable at the recorded BBO. This is stronger adverse
entry-quality evidence than a late reversal after substantial MFE.

## Portfolio interaction

The candidate was not deployable in the shared portfolio because SPCX already
had an open live position. The portfolio journal reports one attempt, zero
deployable candidates, and one `existing_symbol_position` conflict. Therefore:

- the -93.2184 bps is valid counterfactual entry evidence;
- it is not a missed or realized portfolio loss; and
- it does not alter the current open SPCX lifecycle or its venue protection.

## Updated assessment

The formation window had three all-long paths at 2W/1L, +15.9274 bps total,
and PF 2.8302. The first prospective path is materially worse than all of that
formation-window aggregate and crosses the frozen stop proxy. This weakens the
candidate and blocks any promotion claim.

One all-long result is not sufficient to establish that every future pivot
relaxation is negative. The candidate remains report-only while more outcomes
are collected, but the burden of evidence has increased: subsequent paths must
offset the stop loss after costs, remain positive excluding the largest winner,
and include short-side observations before shared-portfolio interaction replay
is coherent.

## Failure modes and falsifiers

The result depends on recorded BBO rather than a submitted IOC and cannot prove
hidden depth or identical private latency. It uses a fixed horizon and stop
proxy rather than the deployed 24-hour Swing/HA lifecycle. The absent 5m/15m
context fields prevent regime attribution for this path.

The negative observation is invalidated by source/profile/cutoff drift,
incomplete funding, stale book context, or changed artifact bytes. The broader
weakening would be updated by independent both-side post-cutoff executions that
produce positive after-cost net return excluding the largest winner without
capacity failures or one-episode concentration.

## Recommendation

Keep the observer running and v25 unchanged. Do not promote, resize, route, or
remove the candidate based on the discovery-window gain. Do not treat this
single counterfactual as an automatic performance gate on the active ungated
trial. Reassess after additional resolved, non-overlapping post-cutoff paths.

Confidence is high for the frozen path arithmetic and occupancy attribution,
and low-to-medium for the inference that the candidate lacks repeatable edge
because only one prospective side/outcome exists.
