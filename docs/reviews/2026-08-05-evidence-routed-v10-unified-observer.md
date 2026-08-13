# Evidence-routed v10 unified observer decision

**Decision time:** 2026-08-05 15:38 EDT  
**Runtime change:** none; inactive next-flat candidate  
**Execution authority:** none from this review

## Problem and success criteria

The separately running four-asset HYPE-breakout observer collects useful
prospective transfer evidence, but its ledger and checkpoint are not part of the
live portfolio cockpit. Continuing that arrangement after the next restart
would duplicate public candle requests and fragment operator visibility.

The next candidate must expose BTC, ETH, SOL, and HYPE HYPE-breakout evaluations
through the shared backend ledger and existing Setup, Chart, and Journal screens
without expanding automatic execution beyond the already-selected mappings.

## Candidate delta

Candidate:
`configs/multi_asset_bidirectional_evidence_routed_hype75_all_asset_observe_candidate.toml`

- profile ID:
  `multi_asset_bidirectional_evidence_routed_hype75_all_asset_observe_v10`
- profile fingerprint:
  `a7dde9ae84c18620476a7c8dc491ac12915a9f111515584bcd98e19e2265cf08`
- executable mappings remain exactly:
  - `hulk_expansion_bidirectional_tuned_v2|BTC`
  - `hype_breakout_onset_bidirectional_v1|HYPE`
- HYPE-breakout observation expands from HYPE to BTC, ETH, SOL, and HYPE.
- HYPE-breakout `execution_symbols` remains exactly `HYPE`.
- both long and short remain enabled for every observed mapping.
- HYPE remains capped at $75 notional and 5x isolated leverage.
- the HYPE 8-hour soft / regime-supported 24-hour hard exit is unchanged.
- all asset, provider, stop, target, priority, polling, and portfolio-capacity
  settings are byte-equivalent to v9 after normalizing only the profile ID and
  HYPE provider observation symbols.

The poller fetches one one-minute candle snapshot per configured asset and then
shares those frames across providers. BTC, ETH, SOL, and HYPE were already
configured assets for Hulk and range-onset, so the expanded HYPE provider does
not add another per-provider venue candle request.

## Why v10 supersedes v9 as the preferred next-flat candidate

| Option | Execution scope | Transfer visibility | Venue request shape | Decision |
|---|---|---|---|---|
| Preserve v9 | Hulk/BTC + HYPE/HYPE | Separate observer only | Separate process duplicates BTC/HYPE polling | Retain as rollback |
| v10 unified observer | Same two mappings | Native four-asset backend/TUI telemetry | Reuses four already-fetched asset frames | Preferred candidate |
| Execute transferred mappings | Wider | Native | Same public reads but new order authority | Rejected |

This is an observability improvement, not an economic promotion. The historical
transfer study remains adverse or contradictory: ETH and SOL are rejected
unchanged transfers, while BTC's positive recent result is short-only and
reverses negative development evidence. Those mappings remain observe-only.

## Validation

The candidate was created through a failing-then-passing contract test. The
focused configuration, loader, poller, v9, and standalone observer suite passed
34 tests. The v10-specific tests prove:

1. only the HYPE provider's observation symbols change relative to v9;
2. the executable provider-symbol set remains exactly two mappings;
3. explicit live flags do not expand the observed transfer mappings;
4. production collectors build for all four HYPE mappings; and
5. all four mappings carry explicit report-only research provenance.

## Risks, confidence, and falsifiers

**Configuration confidence: high.** Exact loader identities and executable sets
are tested. A different fingerprint, any BTC/ETH/SOL HYPE-breakout routed
action, or any other config delta falsifies this assessment.

**Operational confidence: medium.** The standalone observer proves the four
collectors operate together, but v10 has not run as the account-owning backend.
Missing coverage, increased cycle latency, rate-limit faults, TUI parse errors,
or a checkpoint mismatch after activation would lower confidence and require
rollback to preserved v9.

**Economic confidence: low.** No new prospective eligible signal has resolved.
The extra mappings are measurements, not profit forecasts, filters, or sizing
inputs. Repeatable direction-specific positive paths across market states would
justify a separately frozen execution-friction experiment; negative paths
would reinforce rejection.

The current armed backend and open HYPE lifecycle remain unchanged. Activation
requires a verified venue-flat and order-free boundary, exact fingerprint
verification, a fresh pre-start implementation backup, and explicit live
authority.

