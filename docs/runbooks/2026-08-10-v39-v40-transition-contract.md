# v35 to v39 to v41 transition contract

## Identities

| Role | Profile | Capital scenario | Authority |
|---|---|---:|---|
| Active backend | `multi_asset_bidirectional_all_live_canary_v35` | current account | live, already armed |
| Next current-account revision | `multi_asset_bidirectional_hype_compression_range_retired_current_canary_v39` | $500 | staged only |
| Equal-weight growth baseline | `multi_asset_bidirectional_hype_compression_growth_5000_candidate_v40` | $5,000 | report-only baseline |
| Preferred growth revision | `multi_asset_bidirectional_hype_compression_growth_5000_risk_normalized_candidate_v41` | $5,000 | report-only candidate |

The active backend and staged profile are intentionally different. The TUI
renders this as `STAGED UPDATE PENDING`; it is not evidence of a stale backend.

## v39 strategy and asset changes

- Retire `range_onset_bidirectional_v1`.
- Retire both HIP3 Swing routes.
- Remove `xyz:GOLD` from the asset roster.
- Preserve bidirectional Hulk Expansion for BTC, ETH, SOL, and HYPE.
- Preserve bidirectional Hypervelocity Source Follow for BTC.
- Preserve generic HT-Breakout for BTC, ETH, and SOL.
- Replace generic HYPE HT-Breakout with
  `hype_breakout_compression_pullback_bidirectional_v1`.
- Preserve ETH Breakout Pullback.
- Preserve HIP3 Breakout for `xyz:SP500`/`xyz:SPCX` and
  `xyz:SNDK`/`xyz:BRENTOIL`.
- Every declared provider-symbol route is executable; none is observe-only.
- Preserve isolated 5x leverage, 3% margin fractions, ten position slots, and
  one position per asset.

The 3% fractions are ceilings, not the realized v39 allocation for every
asset. At the refreshed $504.70 account snapshot, BTC and ETH are capped at
$25 notional ($5 margin) while the other six assets are capped at $75 notional
($15 margin). An all-eight wave therefore plans $100 margin and $500 notional,
or 19.81% of observed equity. The uncapped eight-by-3% ceiling is 24%; v39 does
not reach it because of the two core-asset caps.

The HYPE compression route requires the canonical completed 5m breakout onset,
authoritative structural direction, 5m BBWP at or below 50, the prior 15-minute
minimum 1m BBWP at or below 40, and a non-chasing directional signal body. Its
exit contract is an 80 bps venue stop, eight-hour soft hold, extension while
regime-supported, and 24-hour hard ceiling.

## v40 sizing change

v40 keeps the v39 asset and provider roster byte-for-byte equivalent at the
parsed contract level. It changes every asset cap to $750 notional:

- $5,000 reference equity × 3% margin = $150 margin per occupied asset.
- $150 × 5 leverage = $750 notional per occupied asset.
- Eight assets imply a 24% simultaneous-margin ceiling.
- Ten configured slots imply a 30% ceiling if two future assets are separately
  qualified and added later.

No performance, trade-count, model-score, or drawdown gate is embedded in the
profile. Transition aborts only for technical inconsistency, an open retired
asset, or outstanding owned orders.

## v41 sizing change

v41 preserves the parsed v40 asset/provider roster, all long/short scopes, 5x
leverage, ten position slots, and the same 24% maximum margin across the eight
configured assets. It replaces equal 3% slot sizing with exact-repriced
inverse-p99 weights. Planned notionals range from $604.76 for SNDK to $860.02
for SP500. The immutable exact-notional audit reports an eight-position p99
stop wave of $58.02 versus $58.82 for v40, and a 1.013x per-asset p99 loss
concentration ratio versus 1.422x. This is risk balance, not an expectancy or
profitability claim.

## Current evidence

- v39 preflight:
  `data/runtime/bidirectional_cohort/latest_current_500_v39_preflight.json`
- immutable v39 preflight at the current drain boundary:
  `data/logs/research/bidirectional_cohort/v39_current_500_preflight_20260811T0355Z.json`
- latest immutable four-position boundary:
  `data/logs/research/bidirectional_cohort/v39_current_500_preflight_20260811T0525Z.json`
- resolved SNDK close audit and latest three-position boundary:
  `data/logs/research/bidirectional_cohort/v35_live_audit_after_sndk_stop_20260811T0542Z.json`
  and
  `data/logs/research/bidirectional_cohort/v39_current_500_preflight_after_sndk_stop_20260811T0544Z.json`
- v40 preflight:
  `data/runtime/bidirectional_cohort/latest_growth_5000_v40_preflight.json`
- v40 empirical growth stress:
  `data/logs/research/bidirectional_cohort/v40_growth_sizing_stress_20260811T0200Z.json`
- v41 preflight:
  `data/runtime/bidirectional_cohort/latest_growth_5000_v41_preflight.json`
- v41 allocation and exact repricing evidence:
  `data/logs/research/bidirectional_cohort/v40_p99_risk_normalized_allocation_20260811T0216Z_v1.json`
  and
  `data/logs/research/bidirectional_cohort/v40_p99_risk_normalized_exact_reprice_20260811T0226Z_v1.json`
- HYPE compression research:
  `data/logs/research/hype_compression_breakout_challenger_20260810_v1/`
- Retest rejection review:
  `docs/reviews/2026-08-10-hype-breakout-retest-economic-diagnostic.md`

The cited 05:44 UTC v39 preflight is the preserved transition record. Its
v35 blockers were subsequently closed and v39 was activated under run
`bidirectional-live-1786453934555`. The v40 and v41 sizing preflights remain
report-only scenario captures and must be regenerated against the funded
account and current books before either profile can replace v39.

## Current TUI command

v39 is now the active live profile. Attach the TUI without a staged profile;
monitor mode must not restart or replace the backend:

```bash
uv run python scripts/multi_asset_bidirectional_canary_tui.py \
  --mode monitor \
  --config configs/multi_asset_bidirectional_hype_compression_range_retired_current_canary_v39.toml
```

The monitor recovers its own report-only checkpoint writer when the checkpoint
is stale. Quitting with `q` leaves the backend running.

## Current v39 accounting and exit contract

At the 2026-08-11 16:21 UTC checkpoint, v39 is healthy and identity-consistent
with four protected shorts: BTC, ETH, SOL, and `xyz:SP500`. The durable venue
archive contains 53 closes, 25 wins, and 28 losses. Only 50 of those closes
have compatible reflection context; the three archive-only rows are historical
GOLD losses. TUI all-time W/L must therefore use archive `25/28` and disclose
reflection coverage as `50/53`, rather than silently treating either population
as complete for both purposes.

The operator-closed SPCX lifecycle was a +$0.693854 net win. The operator-closed
SOL short moved favorably and earned +$0.050960 gross, but $0.064204 fees and
+$0.009934 funding produced -$0.003310 net. Net-of-friction accounting therefore
classifies SOL as a loss. The next SNDK protective-stop close was -$0.726696;
those are the two latest chronological losses.

Exit control is route-specific:

- every route has an owned reduce-only protective stop;
- an authoritative opposite executable intent can close or reverse a position;
- Hulk has a structural-clamped stop plus a 3R target;
- Source-Follow has an 80 bps safety stop plus a 26.67 bps target;
- HT-Onset and HYPE-Compression use an 8-hour soft timer that can extend while
  the canonical regime remains supportive, with a 24-hour hard ceiling;
- ETH-Pullback has a 12-hour fixed ceiling; and
- HIP-3 breakout routes use a 24-hour fixed ceiling.

Provider-native recipe exits are currently ignored. For routes without a target,
the timer is therefore a terminal strategy mechanism alongside the protective
stop and opposite intent, not merely an emergency fallback. A future exit change
must use a new profile identity and route-specific prospective evidence; the
existing generic early-lock challengers reduced mixed-history returns.

## Exact v39 post-start audit

After v39 starts and all eight asset ledgers have advanced, publish the generic
exact-run audit rather than adapting an older candidate-specific verifier:

```bash
uv run python scripts/multi_asset_bidirectional_live_audit.py \
  --ledger-root data/live/bidirectional_cohort \
  --out-dir data/logs/research/bidirectional_cohort
```

The audit is execution-incapable. Technical acceptance requires:

- current run/profile identity equals v39 fingerprint
  `8785a2618d4e06d7b23886ee39a4c05caed6326641efe101ff52ab47bbdae6e5`;
- all eight asset identities and ledgers match the cohort run;
- seven providers, 14 provider-symbol routes, and 28 long/short scopes are
  represented without an observe-only route;
- each provider-symbol route emits evaluation/readiness telemetry or an
  explicit technical non-action reason;
- every HIP-3 breakout decision freezes the latest causally received book at
  or before its completed 15-minute close and reports `pressure_status`, age,
  and imbalance consistently from that boundary;
- current-run health has no unresolved runtime fault;
- every open position is isolated 5x, reconciled, and fully covered by its
  owned reduce-only stop;
- fees, funding, fill slippage, acknowledgement, markout, regime context, exit
  reason, and provider attribution remain explicit when applicable; and
- current-profile performance contains only exact-v39 lifecycles while mixed
  history remains separately labeled.

Run the identity- and status-aware verifier against that fresh checkpoint:

```bash
uv run python scripts/v39_poststart_acceptance.py
```

After technical acceptance passes, publish the first exact-profile economic
snapshot. This command pins the exact v39 profile fingerprint, rejects v35 or
any changed v39-shaped profile, and materializes all 14 routes plus the 28
configured long/short scopes, including explicit zero-trade rows:

```bash
uv run python scripts/v39_forward_evidence_monitor.py --once
```

For the forward window, the same command may run without `--once`; it updates
only `data/runtime/bidirectional_cohort/latest_v39_forward_evidence.json` and
has no execution, resizing, pause, retuning, or promotion authority. A
profile-identity or route-coverage failure preserves the last valid snapshot.
It also rejects checkpoints older than 90 seconds, noncausal timestamps,
contradictory route/side accounting, duplicate open lifecycles, and an output
path that aliases either evidence input. Configured directional authority and
the number of sides with actual evaluations are reported separately.

Its immutable negative control is
`data/logs/research/bidirectional_cohort/v39_poststart_negative_control_v35_20260811T0400Z.json`:
the verifier rejected the active v35 checkpoint for its old profile, roster,
configuration generation, missing `pressure_status`, and extra GOLD route. A
v39 acceptance is valid only when those exact reasons clear; zero fills can
prove technical shape but cannot prove realized execution economics.

Trade count, win rate, profit factor, drawdown, and model/regime scores are
reported evidence, not implicit acceptance gates. Any missing technical field
is a data-quality defect to fix before using that lifecycle as scale evidence.

## Forward v39 measurement contract

The compatible v39 window must preserve the frozen provider and execution
identities while collecting the following measurements before a $5,000
decision:

- intent-accounting completeness: every executable intent equals one routed
  action or one explicit withheld/non-action reason;
- realized friction: entry/exit slippage and acknowledgement latency;
  fees and funding as a share of positive gross market PnL, separated by
  route, asset, and side;
- repeatability: median net return, profit factor, drawdown, side composition,
  largest-winner share, and net PnL excluding the largest winner;
- portfolio interaction: maximum concurrent positions;
  cross-symbol entries inside 1, 5, and 15 minutes; same-side clustering; and
  realized/modeled simultaneous stop waves;
- missed capture: eligible but withheld decisions, blocker identities, and
  causal 5/15/30/60-minute markouts after venue-specific friction; and
- regime attribution: point-in-time entry/exit state, movement strength,
  direction conflict, and opposition persistence without turning descriptive
  regime direction into an implicit veto.

Technical incompleteness can invalidate a lifecycle for scale evidence;
performance outcomes remain report-only and do not stop an otherwise valid
trial. The first v39 window is not retuned in place. Any later parameter change
requires a new profile identity and preserves the prior window as evidence.

The Trade Oracle notebook independently supported friction, outlier, median,
and co-trigger measurements. It also contradicted the supplied v39 roster by
claiming Range Onset was retained, and proposed unvalidated numeric thresholds.
Those claims were rejected. Its range-reclaim concept remains a separately
identified research hypothesis and cannot alter v39 or its validation window.

The exact v41 topology diagnostic
`data/logs/research/bidirectional_cohort/v41_provider_family_concentration_20260811T0535Z_v1.json`
maps the eight assets into three connected provider clusters. The four-core
cluster contains 50.0853% of the modeled all-asset p99 stop wave; the two HIP-3
clusters contain 24.8707% and 25.0440%. This is structural exposure capacity,
not an estimated co-trigger probability. It proves that per-slot p99
normalization does not remove shared-provider or cross-asset concentration.

Until exact compatible closes exist, v41 remains venue-risk-only.
expectancy-weighted sizing would estimate weights from sparse incompatible
history. The compatible window must instead measure provider-family and
cross-symbol co-triggers, realized simultaneous losses, median outcomes, and
largest-winner sensitivity. Any later cluster budget is a separately named
profile, not an in-place v41 adjustment or an implicit execution gate.

The ML4T/Jansen notebook supports constrained risk-parity and hierarchical
allocation when expected returns and covariance estimates are unstable. It
does not prove that provider-graph connectivity equals return correlation.
The current asset liquidity windows are asynchronous, so HRP or covariance
weights remain a separately preregistered point-in-time challenger until a
synchronized causal return panel and walk-forward stability test exist.

The immutable exact-roster audit
`data/logs/research/bidirectional_cohort/v41_return_panel_coverage_20260811T0558Z_v1.json`
confirms that limitation against the 37.61 GB market DuckDB. SP500, SPCX,
SNDK, and BRENTOIL have no canonical five-minute trade bars; ETH and HYPE
have only about 26 hours. The eight-asset roster has zero exact shared timestamps;
covariance weighting remains withheld. This is a research-evidence limitation,
not an execution or performance gate. A future challenger requires synchronized
point-in-time bars for all eight assets, explicit session/no-trade treatment,
and walk-forward stability under a new profile identity.

Historical mixed-profile context is descriptive only: 47 closed lifecycles
reached seven simultaneous positions, with five cross-symbol same-direction
entry pairs inside five minutes. A different compatible v39 result would
update the concurrency assumption; it cannot be inferred from that mixed
history.

## MU and SK Hynix candidate-slot disposition

`xyz:MU` and `xyz:SKHX` were evaluated as potential ninth and tenth assets,
but neither is included in v39, v40, or v41. Both studies preserve the selected
15-minute breakout identity, keep validation and final holdout unopened, and
have no execution authority.

- MU development: 56 trades; nominal +$14.81/PF 1.71 and stress
  +$13.14/PF 1.60 on $500. Stress remains positive without the largest winner,
  but the short slice does not. Forty-three of 56 selected lifecycles overlap
  unresolved mark-path evidence.
- SKHX development: 34 trades; nominal +$14.76/PF 2.43 and stress
  +$12.91/PF 2.09 on $500. All three development folds are positive and pooled
  stress remains positive without the largest winner. The long slice is
  largest-winner dependent, the short slice is only marginally positive after
  removing its largest winner, and 24 of 34 selected lifecycles overlap
  unresolved mark-path evidence.
- MU, SKHX, and SNDK are one provisional semiconductor exposure cluster, not
  three independent position slots. The limited common return window reports
  correlations of roughly 0.76 to 0.86. A future roster may qualify one
  cluster member or use a separately implemented shared cluster budget; it
  must not silently consume three independent risk slots.

The original technical contract required mark observations no more than five
seconds apart. Hyperliquid documents approximately three-second HIP-3 oracle
updates and a ten-second stale-mark fallback, so five seconds is a conservative
research threshold rather than a documented venue maximum. That observation
does not resolve missing historical stop paths and does not authorize a
post-hoc threshold change. The next experiment must use a separately named,
predeclared technical-evidence contract or exact prospective/on-chain mark
capture, replay only the already-frozen candidate identity, and abort before
validation if selected development lifecycles remain unresolved.

SKHX is the first candidate for that experiment because its pooled development
economics and fold stability are stronger. MU remains second. If SKHX becomes
technically resolved, it should first challenge SNDK for one semiconductor
cluster slot rather than automatically occupying an unused independent slot.

The frozen SKHX 15-minute breakout was also replayed on the common
development-only `candleSnapshot` window, 2026-06-21 02:00Z through
2026-07-16 21:00Z. Across 2,476 contiguous bars, public-trade OHLC and official
venue-candle OHLC produced the same 24 entry signals and 22 completed
lifecycles. One bar, 2026-06-30 13:45Z, disagreed on both EMA exit flags; the
venue-candle replay changed net PnL by only -$0.00253 nominal and -$0.00252
under stress. This weakens signal-source sensitivity as an explanation for the
development result, but does not open validation: stress net excluding the
largest winner is negative on this common tail, the long slice loses, and the
historical risk-path evidence remains unresolved.

Evidence:

- `data/logs/research/xyz_mu_15m_breakout_development_path_thresholds_20260608_20260716_v1.json`
- `data/logs/research/xyz_skhx_development_only_diagnostic_20260811_v2.json`
- `data/logs/research/xyz_skhx_exact_mark_paired_archive_audit_20260811_v1.json`
- `data/logs/research/xyz_skhx_liquidity_profile_current_fees_20260811_v1.json`
- `data/logs/research/xyz_skhx_signal_source_sensitivity_20260812_v2.json`

Falsifiers include any source/hash/window mismatch; unresolved selected
development paths after the new evidence contract; non-positive stress net or
profit factor after removing the largest winner; untouched validation failure;
or a synchronized portfolio replay showing that semiconductor co-triggers
breach the separately declared cluster risk budget. Performance failures are
reported candidate results; technical evidence failures remain fail-closed.

## $5,000 activation sequence

v41 is not authorized merely because the scenario preflight is technically
sizeable. After the account is funded, rerun the public-wallet preflight against
the actual balance and current books. Then activate only at a
flat, order-free boundary and only after separate explicit live-risk
authorization for v41.

The latest source-bound preparation evidence is:

- fresh public-wallet and executable-depth scenario preflight:
  `data/runtime/bidirectional_cohort/growth_5000_v41_preflight_20260811T1718Z.json`;
- immutable combined readiness report:
  `data/logs/research/bidirectional_cohort/v41_successor_readiness_20260811T1730Z_v1.json`;
- readiness generator: `scripts/v41_successor_readiness.py`; and
- exact future post-start verifier: `scripts/v41_poststart_acceptance.py`.

The combined report reconciles eight assets, not ten: the account position cap
is ten, one-position-per-asset limits the current roster to eight simultaneous
positions, and two slots remain unused. At a $5,000 sizing reference it binds
24% maximum initial margin ($1,200), $6,000 gross notional, and exact repriced
p99 stop-wave sensitivity of $58.0238627910263. That sensitivity is a
deterministic venue-risk scenario, not a loss guarantee or profit forecast.

No hot reload is permitted. While v39 is open, continue collecting exact route,
side, friction, regime, exit, and missed-opportunity evidence. A route or sizing
change becomes a new profile identity; v39 is not retuned in place. At the
eventual boundary:

1. require every venue and ledger position flat and every owned order absent;
2. stop v39 normally and preserve its implementation/ledger backup;
3. rerun the v41 public-wallet preflight against the funded account and current
   books;
4. regenerate `scripts/v41_successor_readiness.py` from that transition-ready
   preflight and preserve the immutable report digest;
5. start the exact successor only with both explicit live-risk flags;
6. attach the TUI with the same active profile identity and verify eight assets,
   14 provider-symbol routes, 28 directional scopes, sizes, stops, fees,
   funding, regime telemetry, and current/all-time accounting; and
7. run `scripts/v41_poststart_acceptance.py --readiness <flat-boundary-report>`.

The post-start command refuses the current mid-run readiness report because its
transition state is false. It also rejects an active v39 checkpoint, a stale or
unhealthy backend, an identity/route mismatch, missing HIP-3 pressure
provenance, an unprotected position, or friction-contract drift. Passing is
technical acceptance only; performance and trade-count results remain
reported outcomes rather than implicit execution gates. Rollback is permitted
only after v41 is flat and order-free.

## Confidence and falsifiers

Confidence is high that the configuration identities, sizing arithmetic, and
TUI projections match the current files and point-in-time venue preflights.
This does not establish strategy profitability.

Reopen the transition if any of the following occurs:

- the backend heartbeat stops or its run/profile identity changes unexpectedly;
- v39, v40, or v41 parses to a different provider roster than documented here;
- an observe-only route appears;
- a retired GOLD position or owned order is omitted from transition blockers;
- the v41 preflight does not reproduce its eight exact percentages, 5x
  leverage, 24% aggregate margin, or planned notionals;
- live fills, fees, funding, stop coverage, or slippage materially diverge from
  the modeled contracts; or
- fresh prospective HYPE evidence reverses the compression policy's result.
