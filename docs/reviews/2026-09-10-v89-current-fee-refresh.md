# Current fee refresh: growth mode remains enabled

Unsigned venue information captured September 10, 2026, **14:46:13–14:46:15
UTC** confirms the September 7 fee inputs for SPCX, SNDK and Brent. Each has
growth mode enabled and deployer fee scale 1.0. The account base taker rate is
4.5 bps with a 4% active referral discount. The existing official-formula model
projects **0.864 bps per side** for those three markets and **4.32 bps** for
BTC, ETH, SOL and HYPE after referral discount.

High confidence applies to this captured metadata and conditional calculation.
It does not establish fees throughout the historical window, fees on future
fills, current positions, or financial improvement.

| Asset group | Base taker rate | Projected taker rate per side |
| --- | ---: | ---: |
| BTC, ETH, SOL, HYPE | 4.5 bps | 4.32 bps after referral discount |
| SPCX, SNDK, Brent | 4.5 bps | 0.864 bps with growth mode and referral discount |

For the non-crypto markets, the calculation remains
`4.5 × 2 × 0.1 × 0.96 = 0.864 bps`, excluding any aligned-quote discount.
The aligned-quote state remains explicitly unresolved; the projection does not
establish that this additional discount is unavailable. The retained
[official fee formula](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/fees)
matches the calculation for the observed inputs. The page's broad growth-scale
domain descriptions are not mutually consistent; this qualification applies to
the observed scale 1.0 and makes no wider domain-compatibility claim.

## What this changes in the review

The frozen nominal/adverse HIP-3 assumption of 0.9 bps remains slightly above
the observed current projection. The frozen 9 bps full-fee case is an adverse
fee-state stress. It must not be presented as the fee state observed today.
The core 4.5 bps assumption also exceeds the current after-referral projection.
These are point-in-time comparisons, not historical fee reconstructions.

Retain all original historical cases, including their negative results and
registered primary comparison. Add dated current-fee context to a new report
preparation revision, preserving its original predecessor. No replay, strategy,
allocation, leverage, risk setting, live deployment or process transition is
changed. Today's discounts are not substituted into previously explored data.

## Evidence and verification

The capture uses only `userFees`, `meta` for `xyz`, and `perpDexs` on mainnet's
unsigned information endpoint. It reuses the qualified wallet-only loader and
request helper without constructing a signer or execution client. Its account
identity is hashed and matches the previous observation. Only fee rates,
referral discount, exact selected-market growth/deployer modifiers and collateral
index are retained. Unrelated account activity fields are excluded from output;
complete native response bodies are not retained. No account, position or
prospective outcome analysis is performed.

All **30 focused tests pass**: 15 projection/capture tests and 15 existing
fee-parser, model and environment-loader tests. Unknown fields represented by
unserializable objects exercise the retention boundary. Exact identity,
duplicate metadata, missing modifiers and invalid rates are covered. The pure
projection covers **27/27 statements and 8/8 branches**; combined capture and
projection coverage is 88%. The command-line entrypoint is verified by the
successful actual capture, rather than claimed as fully unit-covered.

Five original fee-source identities match their September 7 pins. All 140
captured local source/documentation references match before and after the
observation. Four archived source/plan members match their retained files.
Independent Decimal arithmetic reproduces all seven taker projections within
1e-12 bps. Ruff and file/function-size checks pass. Initial test records retain
the absent-module failure and a corrected expectation of the existing parser's
exception class; no fee formula changed to make those tests pass.

Evidence is under
`data/logs/research/bidirectional_cohort/v89_current_fee_refresh_20260910_v1/`:
`snapshot/fee_inputs.json`, `snapshot/report.json`, `source_manifest.json`,
`qualification.json`, `source.tar.gz`, `fees_documentation.md`, and test logs.
The source archive is 4,751 bytes, SHA256
`7627308b3b3dfbbffbc65ae197cb9a14703788207426823749b4fa6466936a7d`.

Changed growth mode, deployer scale, referral eligibility, account rates,
source identity or unexplained actual fill fees would require a superseding
observation. Retaining the stale snapshot alone leaves present fees uncertain;
replacing historical fees with today's rates introduces an unsupported time
assumption. The next highest-value task is the original complete financial
report with the corrected fee context. Both prospective outcome seals remain
intact. Publication rollback preserves this observation and appends a revision.
