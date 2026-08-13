# HYPE breakout strategy contract

**Audited:** 2026-08-05 10:50 EDT  
**Strategy:** `hype_breakout_onset_bidirectional_v1`  
**Execution authority:** documentation and inactive-candidate validation only

## Scope and identity

The running legacy profile is `multi_asset_bidirectional_canary_v2`, profile
fingerprint
`c992cb2f958ed607d25d6be76a52a37070278061c0e8c186723dc574e6938f6b`.
Its HYPE contract uses `$25` maximum notional and an eight-hour soft hold that
may extend to a hard 24-hour boundary.

The separately preserved inactive candidate is
`configs/multi_asset_bidirectional_evidence_routed_hype75_fixed8_candidate.toml`.
Its profile fingerprint is
`697f30b2bb4eb430c5f514c8b82cdbe994a5decf100459da243c53660b5177b6`
and its file SHA-256 is
`936ec127645c4e07f1fde77f8571f60b8daae720746471fc966d2a97008048fd`.
It raises HYPE's maximum notional to `$75`, changes HYPE to a fixed eight-hour
hold, and limits executable provider-symbol mappings to HYPE breakout/HYPE and
Hulk Smash/BTC. It has not been staged, started, or granted signing authority.

## Market data and decision clock

- The backend polls every 15 seconds and requests Hyperliquid one-minute OHLCV.
- Only completed candles enter the decision builder. Initial startup uses a
  14-day lookback; subsequent polls merge a five-minute incremental window.
- The HYPE provider evaluates on the one-minute clock, but its trigger is a
  completed five-minute regime transition.
- Startup seeds readiness without replaying historical entry intents.
- A fresh intent older than 60 seconds is withheld rather than submitted.

## Exact entry contract

An entry intent requires all three conditions:

1. The current completed five-minute state is `BREAKOUT`.
2. The preceding completed five-minute state was available and was not
   `BREAKOUT`; this makes the signal an onset rather than every bar within an
   existing breakout.
3. The completed one-hour SMA10/SMA30 relation is directional:
   - `SMA10 > SMA30` produces a long intent.
   - `SMA10 < SMA30` produces a short intent.
   - equality or insufficient hourly warmup produces no intent.

The five-minute `BREAKOUT` classification requires a completed five-minute
close beyond the preceding 60 five-minute highs/lows by at least 8 bps and
current five-minute volume at least 2.5 times the mean of the preceding 20
five-minute volumes. Those windows represent approximately five hours of
structure and 100 minutes of volume, respectively.

The trade side deliberately comes from the completed hourly SMA relation, not
from the five-minute breakout direction. A downward five-minute breakout may
therefore open a long while hourly SMA10 remains above SMA30. The present
contract can behave as a structural pullback/fade as well as continuation; it
does not require an hourly crossover on the entry bar or a minimum hourly SMA
gap.

## Regime and feature authority

The following values are measured but do not independently veto a standalone
HYPE intent: one-minute state, 15-minute context, regime confidence, RSI/RSI
EMA, BBWP, EMA-gap strength, order-book pressure, OPI, and the observe-only ML
metalabel. BBWP still contributes to general regime classification, but a
prior `BBWP < 25%` compression is not an HYPE entry requirement. The breakout
classification overrides the ordinary trend/range state on the triggering
five-minute bar.

Canonical 1m/5m/15m regime alignment is attached to every intent. It ranks two
simultaneous providers competing for HYPE, using weights 1/3/2, but does not
reject a standalone HYPE intent. Provider priority breaks a remaining tie.

## Routing and position behavior

- At most one position may be open per coin, and the shared profile permits at
  most four simultaneous coin positions.
- A same-direction intent while HYPE is already open is withheld.
- A selected opposite-direction HYPE intent closes the existing position. It
  does not reverse into a new position in the same cycle.
- A later entry requires a genuinely new eligible onset while venue and local
  lifecycle state are flat.
- In the running legacy profile, another executable HYPE provider can also win
  a same-symbol conflict and cause an opposite-intent close. In the inactive
  evidence-routed candidate, only the canonical HYPE breakout provider has
  HYPE order authority; the other HYPE providers remain visible observers.

## Sizing and order mechanics

- Margin mode: isolated.
- Leverage: 5x, below the configured HYPE venue ceiling of 10x.
- Planned notional is
  `min(account equity * 3% * 5, maximum notional)`.
- Running legacy maximum HYPE notional: `$25`, requiring about `$5` margin
  when the cap binds.
- Inactive candidate maximum HYPE notional: `$75`, requiring about `$15`
  margin when the cap binds.
- Entry uses the SDK market-open path with a 1% maximum slippage tolerance.
  That tolerance is a rejection/price boundary, not a forecast of realized
  slippage.
- Actual fill price, venue fee schedule, fill fees, funding payments, order
  acknowledgements, and venue position state are journaled.

After the entry fill reconciles, the backend calculates a stop from the actual
venue entry price and places a venue-native reduce-only market trigger 80 bps
adverse to entry. The lifecycle is not reported `OPEN` until that stop is
visible and reconciled. A rejected or unverifiable stop invokes the fail-closed
emergency-flatten path.

## Exact exit contract

The strategy has no take-profit order. A HYPE position exits through one of
these paths:

1. **Protective stop:** the venue reduce-only market trigger activates 80 bps
   adverse to actual entry. Gaps and venue execution can make the realized loss
   larger than 80 bps.
2. **Opposite selected intent:** the backend cancels the owned stop, submits a
   reduce-only market close, verifies venue flat, and does not reverse in the
   same cycle. A failed close is reprotected or faulted.
3. **Maximum hold:**
   - Running legacy profile: at eight hours, extend only while normalized
     directional structure support is at least 0.5; otherwise close. The
     extension uses provider primary regime plus canonical primary/1m/5m/15m
     evidence and closes unconditionally by 24 hours.
   - Inactive candidate: close at the first completed polling cycle at or after
     eight hours, with no regime extension.
4. **Manual operator close:** an explicit operator command follows the same
   reduce-only, verify-flat lifecycle.
5. **Technical emergency:** entry-direction mismatch, missing entry price,
   protection failure, or unreconciled state invokes a fail-closed close/fault
   path rather than leaving knowingly unprotected exposure.

Fees and funding are included in reconciled lifecycle performance, but neither
is currently an entry gate or adaptive exit input. Liquidation price is venue
telemetry, not an intended exit; the protective stop is the primary adverse
price control and cannot guarantee against a gap or exchange failure.

## Evidence and uncertainty

Six reconciled live HYPE closes were `5W/1L`, `+$2.099489`, PF `10.3762` at the
audit point. Four entries whose five-minute breakout direction opposed the
hourly SMA side were `4W/0L`, `+$2.093364`; the two aligned entries were
`1W/1L`, `+$0.006125`. This is encouraging but post-hoc and sparse.

The one-year venue-bar control is contradictory: the generic eight-hour
contract completed 1,011 development trades at PF `0.8911` and `-7,625.83`
bps, then 214 final-60-day holdout trades at PF `0.8750` and `-1,795.12` bps.
A supplemental direction split found the final-60-day fade subset positive
(119 trades, PF `1.1801`, `+1,371.15` bps) while continuation was negative,
but the fade subset was negative in development. That split is diagnostic and
not promotion-grade evidence.

**Confidence: high** that this document matches the present source/config
contract, supported by direct code tracing and focused tests. **Confidence:
low-to-medium** that the observed live HYPE profitability is durable because
the broader historical control is negative and the live sample is six closes.

Twenty to thirty profile-matched live closes with PF at or below one or
negative after-cost PnL would falsify HYPE's current core status. Repeated live
continuation beyond eight hours that beats the fixed exit would falsify the
fixed-eight-hour candidate. A ledger entry whose side differs from the
completed hourly SMA relation, an entry without a fresh five-minute breakout
onset, or an `OPEN` state without a reconciled venue stop would falsify this
contract implementation.

## Backup and promotion contract

Current and candidate profiles are separate files, so this candidate did not
overwrite the running strategy. Every future cohort live start must create an
immutable prestart bundle before authenticated exchange clients are created.
The bundle includes target and prior strategy configs when changed, provider
source profiles, existing ledgers/runtime state, the bounded implementation
source set, `pyproject.toml`, and `uv.lock`. The launcher decompresses and
SHA-256 verifies every archived source and the composite implementation
identity; a mismatch refuses startup.

The currently running legacy process predates the complete implementation-bound
backup gate and has no production `prestart_*` manifest. Therefore the next
activation must produce and independently verify the first complete bundle;
the current run must not be represented as having one retroactively.
