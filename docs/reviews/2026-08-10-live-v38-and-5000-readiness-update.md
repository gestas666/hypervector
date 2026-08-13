# Live v35, staged v38, and $5,000 readiness update

## Outcome

The live v35 backend is healthy and advancing. The immediate successor is v38,
which removes GOLD, removes HIP3 Swing, and limits Range Onset to SOL. It cannot
replace v35 while the adopted GOLD position and its owned stop remain open. The
separate $5,000 candidate is v37: eight assets, ten position slots, 3% isolated
margin per occupied asset, 5x leverage, and a $750 notional ceiling.

Confidence is high for runtime identity and venue protection over the checked
interval, medium for deterministic $5,000 loss sensitivity, and low for future
strategy expectancy. A stopped heartbeat, missing GOLD stop, identity mismatch,
or exact-policy forward outcomes would update those assessments.

## Bound evidence

| Artifact | SHA-256 |
|---|---|
| v35 config | `4b5b35b2045e5c600a6acd4c7365e9acc771ee6074b18b5e7d30268ba17432cc` |
| v38 current-bankroll successor | `8d378bd57433bc338f24ab913e64a5fc5ee75ee7f5bb33f7c9dce12e2d375423` |
| v37 $5,000 candidate | `325d45f982ae48ce17c661b2c486fd19f02340d71887dcdeced8b47ff37df987` |
| final prior v35 audit | `08b69d85d3a7976afed73d58ba0fcda9c2dc1b2514c040c52a9a829ea103492c` |
| current v35 restart-prefix audit | `5df7f7d29eac4235bec98f0234a9564c9fda41024fc6457b6b5f50ee3b91ca97` |
| corrected 3% stress | `4c388b9be352bb2bb9899268641a795b2ef5add1c798cb9dd47c109269a26ad5` |
| corrected 5% stress | `9e81e55c183b848ab516f519c8b45beb75e69f212bb653aee9ecd25e36ce990f` |
| corrected 7% stress | `70047b68136f1676c0ad235bf6fed9861c28c4f90188406f416d7378f8d316f9` |

The first three newly generated stress files without the `_v2` suffix are not
authoritative because their JSON retained the false hard-coded key
`actual_nine_asset_roster`. Schema v3 uses `configured_asset_roster` and is the
only current sizing evidence.

## Current runtime and transition

At the 2026-08-10 19:14 EDT checkpoint:

- live run: `bidirectional-live-1786402452315`;
- runtime profile: v35, fingerprint `8acc70105f8254dc...`;
- lifecycle: `running_consistent`, no faulted assets;
- GOLD: long 0.0171 at 4362, 5x isolated;
- GOLD stop: order 513912102834, reduce-only, full size, trigger 4327.1;
- GOLD liquidation price: 3564.8707482993;
- all other assets: flat;
- staged v38 fingerprint: `0432f49abfa2c71c...`;
- transition state: wait for flat and no orders, blocker `xyz:GOLD`.

The cohort sequence advanced from 124002 to 124023 during the stale-backend check.
The checkpoint was regenerated from the active run and reported a heartbeat age of
19.6 seconds. Process existence was not used as the sole health proof.

High confidence for this bounded observation. It is falsified if the sequence stops
advancing beyond the configured cycle, an asset faults, or the venue stop disappears.

## Strategy review

The 47 archived lifecycles are mixed-policy descriptive evidence: 42 are incompatible
with exact v35 and five are unverifiable. They cannot establish v38 or v37 expectancy.

| Strategy | Trades | W/L | Net USD | PF | Current action |
|---|---:|---:|---:|---:|---|
| Hulk Expansion | 5 | 4/1 | +1.4678 | 14.34 | retain four crypto assets |
| HT-Breakout | 27 | 13/14 | -0.4513 | 0.920 | retain and measure exact policy |
| ETH Pullback | 2 | 1/1 | +0.0047 | 1.77 | retain ETH |
| Source Follow | 5 | 3/2 | -0.1046 | 0.695 | retain BTC |
| HIP3 Swing CMD | 4 | 1/3 | -0.0500 | 0.976 | removed in v38/v37 |
| HIP3 Swing IDX | 3 | 1/2 | +0.3052 | 1.24 | removed in v38/v37 |
| Range Onset | 1 | 0/1 | -0.1744 | 0 | SOL only in v38/v37 |

HIP3 Swing was addressed by retiring the mechanism, not by tuning the same sparse,
largest-winner-dependent sample. GOLD is also removed as an asset. BRENTOIL and SNDK
remain only under HIP3 Breakout; SP500 and SPCX remain only under their HIP3 Breakout
provider.

Range Onset had no provider faults in the bounded v35 review, but almost all states
were ineligible and its only archived trade lost. Broad threshold relaxation is not
supported: non-overlapping missed-opportunity results were negative at 5m and 15m,
and 30m was largest-winner dependent. SOL-only retention is an explicit experiment,
not a claim that its edge is proven.

Protective stops remain. Archived stop exits lost because they bound failed entries;
that does not establish that wider or absent stops improve net outcomes. Any stop
change requires venue replay that includes gaps, fees, funding, latency, and the
recovery path.

## Regime detector

The authoritative one-year point-in-time evaluation found:

- RANGE had lower absolute future movement in 48/48 cells;
- strength and structural magnitude associated with movement in 48/48 cells;
- canonical direction had 0/32 positive pseudo-holdout cells;
- the RANGE result survived the gap-quarantine sensitivity in 48/48 cells.

This supports range/movement telemetry and conflict context. It does not prove the
directional state has no information in every formulation, and it does not justify
an automatic RANGE veto, directional size multiplier, or exit switch without an
exact strategy-conditional outcome study. HIP3 trades still lack canonical regime
attribution; that is a telemetry gap, not permission to fabricate a fallback.

High confidence for the tested movement relationship; low confidence for directional
prediction. An untouched point-in-time window with stable after-cost directional
improvement would revise the conclusion.

## Research challengers

Trade Oracle and ML4T sources were used as hypothesis generators, not authorities.
Their useful common requirements are completed-bar inputs, chronological partitions,
purging by maximum label horizon, untouched final evaluation, exact path ordering,
trial-count disclosure, and results with and without the largest winner.

Their fixed thresholds, global 13 bps friction assumption, mandatory sample gates,
automatic correlation gates, and claims that 0/32 mathematically proves zero edge
are not accepted. They are either unverified in this project or conflict with
`SRS_HV1_NO_GATES`.

Next research order:

1. exact HYPE compression/breakout challenger built from the observed
   `5m_not_breakout` near-miss lead, with HYPE-specific fee/depth/latency;
2. symmetric 5m failed-breakout range reclaim as a separate mechanism, not a relaxed
   Range Onset recipe;
3. symmetric PMARP/BBWP mean-reversion challenger only if its point-in-time features
   are available without source mismatch;
4. continue MU report-only pressure capture; MU remains non-runnable and non-live
   until prospective candle/pressure parity and durable cursor integration exist.

Every trial outcome remains reportable. Only technical evidence failure aborts a
trial; profit factor, drawdown, trade count, or model score cannot silently gate it.

## Corrected $5,000 sizing sensitivity

All current reports use the eight v37 assets and exact active v35 evidence by symbol.
GOLD is excluded. The staged profile and active evidence profile are serialized
separately.

| Margin/slot | Margin/slot | Notional/slot | 8-asset margin | 10-slot margin | 8-asset p90 wave | 10-slot p90 wave | Five 10-slot p90 waves |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 3% | $150 | $750 | 24% | 30% | $55.78 | $71.30 | $356.52 |
| 5% | $250 | $1,250 | 40% | 50% | $93.16 | $119.06 | $595.28 |
| 7% | $350 | $1,750 | 56% | 70% | $130.61 | $166.90 | $834.48 |

At 3%, modeled per-position p99 stopped loss ranges from about $6.34 for SP500 to
$9.02 for SNDK. Crypto depth uses 47 current-run observations per asset; HIP3 uses
the exact-notional 0xarchive profiles. All sampled depth is complete except SNDK at
99.993%.

Recommendation: retain 3%/5x/$750 for the first $5,000 experiment. This is not a
capital-preservation veto; it is the highest sizing level currently encoded with a
24% eight-asset margin envelope and materially lower repeated-wave loss than 5% or
7%. Larger sizing can be run as an explicit trial when requested.

Confidence is medium for relative deterministic stress and low for realized joint
loss probability. The result is falsified by materially worse live IOC impact, fee
changes, stop gaps, funding persistence, correlation, or capacity decay.

## Operational sequence

1. Keep v35 running while GOLD is open and protected.
2. Use the read-only TUI; its monitor recovers the checkpoint if stale.
3. When GOLD is flat and its owned stop is gone, transition to v38 with explicit live
   authorization and verify all 8 assets, 15 routes, 10 slots, and venue ownership.
4. Collect exact v38 forward fills, non-actions, fees, funding, regimes, and missed
   opportunities.
5. Before $5,000 funding goes live, rerun public-wallet preflight and the schema-v3
   stress report against the actual funded account and current venue conditions.
6. Arm v37 only on explicit authorization; confirm planned versus realized notional
   and full reduce-only stop coverage on the first position of every venue family.

Read-only TUI command:

```bash
cd /Users/gestas/Prototypes/hypervector
uv run python scripts/multi_asset_bidirectional_canary_tui.py \
  --mode monitor \
  --config configs/multi_asset_bidirectional_all_live_canary_v35.toml \
  --staged-config configs/multi_asset_bidirectional_gold_retired_current_canary_v38.toml \
  --growth-preflight data/runtime/bidirectional_cohort/latest_current_500_preflight.json
```

The TUI cannot arm, restart, or change the backend in monitor mode.
