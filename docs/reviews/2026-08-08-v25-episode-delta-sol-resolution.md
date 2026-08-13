# V25 episode delta and SOL lifecycle resolution review

**Reviewed:** 2026-08-08 15:13 EDT  
**Runtime:** `multi_asset_bidirectional_complete_portfolio_canary_v25`  
**Run:** `bidirectional-live-1786182011216`  
**Decision:** retain the running v25 configuration unchanged

## 1. Problem restatement

The live portfolio needs an immutable, point-in-time comparison that answers
three independently verifiable questions:

1. Did a real compatible lifecycle resolve, including fees and funding?
2. Did newly matured provider/blocker episodes produce repeatable after-cost
   paths rather than repeated annotations of the same move?
3. Can those claims be made without mixing asset evidence observed after the
   cohort prefix or mutating the armed runtime?

Success requires exact run/profile identity, causal cutoff enforcement across
every ledger, immutable report files, and zero execution authority.

## 2. Known facts and evidence

The source and destination prefix reports are:

- `data/logs/research/bidirectional_cohort/v25_live_prefix_episode_onsets_bidirectional-live-1786182011216_20260808T183622Z.json`
  - SHA-256
    `d1d340ae3eec51bd86ebb43050cd1ebc72456ad43b705c2c950af793d8221c6f`
  - 9,017,600 bytes
- `data/logs/research/bidirectional_cohort/v25_live_prefix_episode_delta_20260808T190357Z.json`
  - SHA-256
    `8a5c05acb5a9a2f4bb95d6b3544a47f2caf25940726a0722d4357c4deb28d15d`
  - 9,304,061 bytes

Their corrected immutable delta is:

- `data/logs/research/bidirectional_cohort/v25_live_prefix_delta_episode_onsets_corrected_20260808T183622Z_20260808T190619Z.json`
  - SHA-256
    `7dacb342748ce5245c3d6ef484da324e8cd745888a5c7e3248b3a35c89e5f608`
  - 182,620 bytes
  - report-only, `execution_authority=none`, no automatic promotion, and no
    runtime strategy change

The comparison covers 206 added cohort rows, from 18:36:23 to 19:03:54 UTC.
The destination prefix contains 4,345 cohort rows.

## 3. Causal snapshot defect and correction

The first destination audit exposed a real non-atomic snapshot race. The
cohort ledger was copied while SOL was still open; SOL closed before its asset
ledger was copied. The history selector previously bypassed the cohort cutoff
for the latest asset run, so the report combined an earlier cohort state with
a later SOL close.

`select_asset_evidence` now applies the cohort `as_of` timestamp to current,
compatible-history, and all-time asset rows without a latest-run bypass. A
post-cutoff asset event is excluded even when it belongs to the active run.
The audit therefore represents one causal point in time rather than the order
in which files happened to be copied.

Regression tests cover:

- exclusion of post-cutoff current, compatible-history, and all-time rows;
- immutable resolved episode-path retention and identity;
- honest `newly_available` output when a prior prefix lacks attribution;
- exclusion of attribution rows whose evidence did not change.

The earlier noisy delta remains immutable evidence, but it is superseded for
decision use by the corrected delta above.

## 4. Resolved execution result

One exact compatible lifecycle newly closed:

| Field | Result |
|---|---:|
| Lifecycle | `SOL:512630721342` |
| Provider | `hype_breakout_onset_bidirectional_v1` |
| Side | long |
| Entry / exit | 74.457 / 76.12 |
| Gross price return | +2.2335% |
| Net PnL | +$1.582877 |
| Return on margin | +10.6561% at 5x |
| Fees | $0.065048 |
| Funding | -$0.015075 |
| Holding time | 55,510,094 ms (about 15h 25m) |
| MFE / MAE | +309.57 / -19.61 bps |
| Gross MFE captured | 72.15% |
| Exit | `maximum_hold_seconds` via `cohort_maximum_hold` |

Entry context was aligned: 1m `TREND_UP`, 5m `BREAKOUT`, and 15m
`TREND_UP`. Exit context was mixed: 1m `TREND_DOWN`, 5m `RANGE`, and 15m
`TREND_UP`, with structure-support score 0.0833. No provider exit was ignored.

The cumulative compatible history at the destination prefix is four closed
trades: three wins, one loss, +$1.617944 net, $0.142406 fees, -$0.020950
funding, and profit factor 3.4631. This is descriptive evidence, not a stable
edge estimate.

## 5. Opportunity and episode analysis

The destination prefix contains 3,563 provider observations and 2,327 unique
directional paths. Deduplication removes 1,236 repeated provider observations;
1,078 path groups contain multiple providers, one group contains directional
competition, and no reference-price conflict was accepted.

Independent cumulative outcomes remain negative after the fixed 13 bps
hurdle:

| Horizon | Resolved | Cost-clearing close | Mean after hurdle | Leave-largest mean |
|---|---:|---:|---:|---:|
| 5m | 529 | 24 | -12.88 bps | -12.99 bps |
| 15m | 230 | 15 | -11.70 bps | -12.91 bps |
| 30m | 116 | 17 | -10.18 bps | -12.68 bps |
| 60m | 64 | 15 | -7.74 bps | -11.55 bps |

The delta added 189 provider observations, 114 unique paths, and removed 75
duplicates. Episode attribution is comparable: 18 attributions changed, three
were added, and none disappeared. It produced 11/9/4/9 newly independent
episode paths at 5/15/30/60 minutes.

Only one of those 33 new exact episode paths cleared the 13 bps close hurdle:
an `xyz:SNDK` short from the Swing/HA provider with
`pivot_break_state_missing`, resolving at 30 minutes with +13.95 bps close,
+18.06 bps favorable excursion, and 3.28 bps adverse excursion. It did not
clear the robust-MFE criterion. The other new episode paths failed the close
hurdle.

## 6. Uncertainties and failure modes

- Four closed trades, including one resolved SOL HT-Breakout lifecycle, are
  insufficient to estimate repeatability or tail loss.
- Counterfactual episode paths do not prove IOC fill, realized slippage,
  simultaneous portfolio capacity, or live PnL.
- Coverage remains incomplete because
  `provider_metric_telemetry_missing` persists. The delta adds ten missing
  metric values and seven right-censored observations without changing the
  technical-gap identity.
- The SOL outcome came from a compatible prior run under the same profile
  fingerprint; exact run provenance remains explicit rather than pooled away.
- A report that accepts post-cutoff asset rows, loses or rewrites a resolved
  path, changes an immutable evidence hash, or causes a live side effect would
  falsify this implementation.

## 7. Validation

- Focused causal audit/delta/run-selection suite: 51 passed.
- Full non-network Python suite: 4,122 passed, four deselected, 27 known
  warnings.
- Ruff and formatting checks passed for every changed audit source/test file.
- Changed production modules are below 500 lines; no changed function exceeds
  50 lines.
- At 19:12:33 UTC, the v25 ledger heartbeat was advancing. Launchd reported
  PID 37897, one run, and no prior exit. BTC, HYPE, SPCX, and GOLD each retained
  a venue-native reduce-only stop. No process, route, order, position, stop,
  target, size, allocation, drain, protection, or strategy was changed by this
  review.

## 8. Recommendation and trade-offs

| Option | Evidence | Decision |
|---|---|---|
| Retain v25 and collect independent live closes | Preserves the only causal forward sample and avoids confounding | **Selected** |
| Loosen an entry blocker now | 32/33 new episode paths failed the fixed close hurdle | Rejected for this revision |
| Promote the SNDK annotation | One 30m path and no robust MFE are not repeatable evidence | Rejected |
| Stop the live trial | No runtime fault, protection loss, or technical abort condition observed | Rejected |

Confidence is high for evidence identity, cutoff causality, delta arithmetic,
and execution isolation because these are directly tested and hash-bound.
Confidence is low for economic generalization because the resolved live sample
is four trades and the newly independent path distribution is predominantly
negative after costs.

The decision should be updated by additional independent, venue-resolved
lifecycle closes with consistent after-fee/funding behavior. It should be
falsified immediately by identity drift, a missing venue stop, a runtime fault,
an unexplained lifecycle disappearance, changed immutable evidence, or a live
mutation caused by report-only tooling.
