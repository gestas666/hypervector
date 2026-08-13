# HYPE authoritative 5-minute entry attribution

**Observed:** 2026-08-04 EDT  
**Mode:** report-only post-hoc development measurement  
**Execution authority:** none

## Problem restatement

The current live HYPE breakout entered from an authoritative completed 5-minute
`BREAKOUT`, yet the existing historical attribution sidecar measured mostly
1-minute tactical features. The live entry's 5-minute breakout-volume ratio was
`5.2392x`, creating a falsifiable hypothesis: stronger authoritative breakout
intensity might distinguish the favorable live sample from the negative
deployed-shape history.

The success criterion was deliberately narrow. A feature needed chronological
fold stability and an absolute median high-minus-low gross tail spread of at
least `26 bps`, twice the modeled `13 bps` round-trip cost. This measurement did
not define, select, or apply an execution threshold.

## Point-in-time implementation

The historical and future live telemetry contracts now share four causal values
from the completed authoritative 5-minute classifier:

- strength percentile;
- BBWP percentile;
- EMA-gap bps, directionalized to the intended side;
- breakout-volume ratio.

They are emitted under the
`causal_completed_multitimeframe_historical_parity_v2` provenance. The sealed,
previously opened 60-day block was not reopened. The analysis retained the
existing 1,011 development lifecycles, five chronological folds, next-open
execution, `4.5 bps` fee and `2 bps` slippage per side, funding, and the active
protective-stop/maximum-hold contract.

## Results

| Authoritative 5m feature | Median fold Spearman IC | Sign-consistent folds | Median high-low gross spread | Clears 26 bps? |
|---|---:|---:|---:|---:|
| Strength percentile | -0.0658 | 4/5 | +12.15 bps | No |
| BBWP percentile | -0.0497 | 4/5 | +2.68 bps | No |
| Directional EMA gap | +0.0111 | 4/5 | -1.76 bps | No |
| Breakout-volume ratio | -0.0011 | 3/5 | +9.96 bps | No |

None cleared the predeclared gross-spread hurdle. Breakout-volume association
also changed sign across folds. The live entry's `5.2392x` volume is near, but
generally below, the historical top-tail cuts (`5.82x`, `5.95x`, `7.46x`,
`6.17x`, `6.35x`). Its 5-minute strength percentile was only `8.75`, so it is
not an example of the historically measured high-strength tail.

The four already-declared entry policies remain unsupported. The least-bad
development policy remained `precompression15_min40_pullback` at PF `0.99945`,
`-14.63 bps`, and only 2/5 positive folds. No forward candidate was produced.

## Assessment

**Confidence: high for the development-set measurement; low for future return
prediction.** The output is reproducible from 525,600 venue-matched HYPE bars,
8,760 funding rows, and immutable feature/trade sidecars. It directly falsifies
the narrow hypothesis that these four authoritative intensity measurements, by
themselves, explain the favorable live sample strongly enough to clear modeled
costs.

This does not prove every combination is useless, nor does it prove the current
live HYPE trade will lose. Searching combinations or thresholds now would add
post-hoc trials and increase overfitting risk. The appropriate action is to
retain the measurements in forward telemetry and let new venue lifecycles test
them without changing execution.

## Risks and falsifiers

- One-minute OHLC cannot reproduce exact intrabar ordering or private IOC
  slippage.
- The feature analysis is post-hoc and development-only.
- Overlapping onsets reduce the effective sample below the nominal 1,011
  lifecycles.
- A future code-parity replay producing different 5-minute values for the same
  completed bars would falsify point-in-time parity.
- Fresh, independently observed lifecycles showing a stable cost-clearing
  relationship across multiple non-overlapping market episodes would update
  the current negative assessment.

## Evidence

- Summary: `data/logs/research/hype_breakout_entry_attribution_development_v2_20260804.json`
  (`SHA-256 49b69f22c65ea039e7eb71b4842d8ba3e4ea9a13f25c75b4d71204047d616cc6`)
- Feature rows: `data/logs/research/hype_breakout_entry_attribution_development_v2_20260804.features.parquet`
  (`SHA-256 0088305b8348ca8e624433c7699a28521583923c2e80b24f5bdc1dbbb2afaf89`)
- Lifecycle rows: `data/logs/research/hype_breakout_entry_attribution_development_v2_20260804.trades.parquet`
  (`SHA-256 3f61ff4d00de357d9bb22139d508289803047ba37bd8bd80c5b08ffe4829a47c`)
- Deployed exit parity:
  `data/logs/research/hype_breakout_live_extension_parity_20260804.json`
