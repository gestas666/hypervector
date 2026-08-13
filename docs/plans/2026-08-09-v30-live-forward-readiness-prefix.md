# V30 Live Forward-Readiness Prefix

## Purpose

Freeze a report-only, source-bound view of the exact three v30 routes using the
currently running v25 ledger and checkpoint. This test cannot drain v25,
activate v30, place or close an order, resize a position, or change a route.

## Inputs

- Authoritative current cohort checkpoint loaded once as immutable bytes.
- Append-only `decisions.jsonl` prefix length and SHA-256.
- Exact inactive v30 TOML and profile fingerprint.
- Exact route scorecards already derived by the backend:
  - `range_onset_bidirectional_v1|SOL`;
  - `range_onset_bidirectional_v1|ETH`; and
  - `hip3_swing_ha_sp500_spcx_bidirectional_v2|xyz:SPCX`.

## Measurements

For each selected route report:

- forward evaluations and eligible-signal count;
- independent 5/15/30/60-minute directional paths;
- exact live closed trades, fees, funding, net PnL, PF, and side composition;
- net PnL excluding the largest winner; and
- whether the route has any prospective eligible or execution evidence.

Also report current v25 closed economics, every open position, stop protection,
source faults, current profile and run identity, and transition-drain state.

## Decision rule

The fixed v30 profile remains inactive if any selected route has zero eligible
forward signals, if exact live execution evidence is missing for a route, if
the only positive route becomes negative after removing its largest winner, or
while v25 owns a position or order. These are research-readiness findings, not
implicit runtime performance gates.

No route, side, size, or leverage is changed from this opened prefix. A later
transition still requires explicit operator authority and a verified
flat-and-order-free boundary.

## Falsifiers

- The checkpoint route key does not match the v30 executable mapping.
- The checkpoint, configuration, or decisions-prefix identity cannot be
  reproduced.
- A selected route metric is silently defaulted or inferred from another route.
- Open positions or stop protection are omitted.
- The report claims counterfactual fills from eligible signals.
- The report mutates live state or grants execution authority.
