# Hypervelocity Recipe C Direction-Selector Plan

**Goal:** Determine whether point-in-time evidence can choose between long fade
and short trend-follow actions at the identical pinned Recipe C `TREND_DOWN`
onsets.

**Scope:** Research and annotation only. No runtime, TUI, faithful-config,
position-sizing, target, liquidation, or model-authority change is authorized.

## Upstream source and simulator audit

Git history locates the exact selective recipe at Hypertrader commit
`7c26fef054bbf216f9d6a270c06f8c9bc1eef679`, which is contained in the
pinned `master` revision. The source confirms that Recipe C is a long fade of
a `TREND_DOWN` onset during 07:00-16:00 UTC, with a 24-hour maximum hold, no
stop, and a 20-bps/130-point target.

The advertised 26/26 historical result is not execution-equivalent to the
Hypervector archive replay. Its runner loads Binance closes, enters at a
nearest five-minute close, and evaluates future nearest closes for the target.
It does not reconstruct maker fills, use intrabar high/low for target or
liquidation, model queue position, or maintain a 70%-margin leveraged
portfolio with isolated liquidation. The upstream recipe itself labels the
result in-sample and calls for forward validation.

The pinned source boundary now includes both the recipe implementation and
its historical runner. This closes a prior provenance gap where the primary
classifier was hash-pinned but the B/C recipe and its evaluation contract were
not.

A native-candle parity check then addressed the remaining feed-construction
risk. Across the available five-day overlap, 1,261/1,441 rows had exact OHLC
parity between native Hyperliquid 5m candles and 5m bars resampled from
Hyperliquid 1m. The pinned classifier produced equal primary labels on
1,439/1,441 rows and equal secondary labels on 1,423/1,441. Most importantly,
all nine selective B/C event rows had identical recipe IDs and timestamps.
This supports the resampled 90-day labels for the selective event study, but
the short native overlap limits confidence to medium. Artifact SHA-256 is
`b67bce9f8736017553f5772dd4d9cdd54989dbb86e1b96c5eb5dc72bd243671c`.

The source event population itself is also not reproducible from committed
files. The upstream runner reads the newest 8,000 rows from an external
`regime_ta.sqlite` database; it does not regenerate those labels, and that
database is not in the repository. The source claims 15 B and 11 C entries.
Applying the pinned recipe to the reconstructed 90-day labels instead yields
2 B and 77 C events; its trailing 8,000 rows yield 1 B and 25 C. At the eight
visible source-history timestamps, all three C rows still map to `TREND_DOWN`,
but none of the five B rows maps to current `BREAKOUT/BK_UPWARD`.

Therefore the experiments below reproduce the pinned formula on current
reconstructed labels, not the source's exact persisted July event population.
The missing source SQLite rows and their generating classifier revision are
required to close that gap. Population-audit artifact SHA-256 is
`0307031aaa9f77595c4e4680191c570428175d65644e14f6549ce771cf50f48e`.

## Frozen experiment contract

- 76 development Recipe C event times from the pinned formula applied to the
  reconstructed Hypertrader labels.
- Decision occurs only after the source 5m bar is complete.
- Same $10,000 initial equity, 70% isolated allocation, BTC 40x, 8% gross-margin
  target, no stop, one position, fees, funding, mark/oracle liquidation, and
  60-second maker eligibility.
- Compare long fade and short follow without a signal-range ceiling.
- Retain touch, book-through, and public-trade-through results separately.
- Treat path-dependent `not_submitted` rows and equal outcomes as unresolved,
  not as favorable labels.

## Verified unconditional baselines

| Fill assumption | Long fade | Short follow | Long DD | Short DD |
|---|---:|---:|---:|---:|
| Touch | $11,163.56 | $13,920.39 | -66.14% | -66.09% |
| Book-through | $10,173.02 | $21,255.12 | -67.68% | -56.69% |
| Public trade-through | $10,229.80 | $19,370.46 | -54.26% | -47.67% |

All three pairs contain the same 76 decision timestamps, share the exact labels
hash, and match every execution-contract field except direction. Short follow
is the unconditional development leader. This does not prove that a selector
is learnable: per-event outcomes contain many ties, cancellations, and
path-dependent admissions.

Short-follow artifact SHA-256 values:

- touch: `d225e826e21847857a8f199746cc78c0a0c981dd99b1178ee9ba54ae9a206897`
- through: `410d5377689347cce6beddeef03667eba2cb700881e1614d8c22185651fcd2f1`
- trade-through: `77623a57875d47f95b38ea2c249ee77c66155943984362b5436d341efd7466de`

## Validation sequence

1. Build paired event outcomes and explicitly classify ties, cancellations,
   and path-dependent admissions.
2. Measure label overlap and effective sample size from actual event lifetimes.
3. Add only point-in-time source, completed-bar, and verified L2 features.
4. Compare always-fade, always-follow, a frozen transparent rule, and strongly
   regularized logistic regression with purged expanding walk-forward folds.
5. Keep fill models separate; require sign/direction consistency rather than
   averaging them.
6. Log the searched set and retain future Recipe C events as untouched forward
   evidence.

## Risks and falsifiers

- If effective sample size is too small for stable folds, stop at descriptive
  annotation and collect forward events.
- If fold direction flips, logistic fails to beat the unconditional leader, or
  trade-through disagrees with optimistic fills, reject the selector.
- If features require data available after decision time, reject the dataset.
- Fresh venue-matched Recipe C outcomes that materially underperform the
  development baselines update or falsify the current short-follow lead.

Confidence is medium that short-follow is the stronger development baseline
and low that a reliable event-level selector is learnable from this window.
Confidence is high that the upstream 26/26 and the L2 replay answer different
execution questions. A raw creator ledger with venue fills, margin, and
liquidation records would update that assessment.

## Measured label and pressure-screen result

Pairing the identical event rows produced 39 trainable preferences under touch,
39 under book-through, and 41 under public trade-through. Requiring every fill
model to agree reduced this to 25 consensus labels: 14 fade, 11 follow, and 51
unresolved. Their measured duration-weighted uniqueness is 1.0, so
`N_eff = 25`; the reduction comes from fill ambiguity and path dependence, not
overlapping label lifetimes.

The strongest causal univariate association was five-second top-of-book OFI.
The natural zero-sign rule chose short follow for nonnegative OFI and long fade
for negative OFI. It classified 20/25 consensus labels, including 8/9 early and
12/16 later. Because the feature was selected after screening and the 51 messy
events were not represented in that score, it remained an exploratory
annotation and was replayed statefully before any promotion decision.

The stateful result was mixed and failed the frozen robustness criterion:

| Fill assumption | OFI selector | Always short | OFI DD | Short DD |
|---|---:|---:|---:|---:|
| Touch | $17,811.14 | $13,920.39 | -76.45% | -66.09% |
| Book-through | $16,223.90 | $21,255.12 | -76.45% | -56.69% |
| Public trade-through | $21,388.88 | $19,370.46 | -48.36% | -47.67% |

The selector increased fills to 61/59/31 and worsened drawdown under all three
fill assumptions. It is rejected as a strategy rule. The OFI relationship may
describe maker-side fill selection rather than a stable directional forecast;
fresh evidence can update that hypothesis. No pressure threshold grid or ML fit
is authorized from these 25 labels.

OFI-selector artifact SHA-256 values:

- touch: `338c1d6ef53679e918e0abe11e724318535a71b08fdf12835201fd1245890a03`
- through: `f2eb55dc7f7fa6bb50b8ca893b0f885ebf838143d12616c140742ad6b361733c`
- trade-through: `8d336551529c9c419e64c88c3f2ec4d06a1c64414a869dfe550bc5651766307f`

One Jul 27 Recipe C event is outside the development partition. Its fade-long
maker order canceled under every fill assumption. The same-event short-follow
filled and reached its target under touch, book-through, and public
trade-through, producing +$476.87 net from the isolated $10,000 portfolio.
This is one directionally supportive forward observation, not a stable edge
estimate; a later short-follow failure would immediately update confidence.

## Recipe B reconstruction closure

The exact Recipe B formula was replayed separately with 60-second maker
eligibility and no transferred range ceiling. Only two events exist in the
reconstructed 90-day population. The first canceled under all fill models; the
second filled, missed its target, and exited at the four-hour source timeout.

| Fill assumption | Final equity | Maximum drawdown | Targets / liquidations / time exits |
|---|---:|---:|---:|
| Touch | $6,878.74 | -35.17% | 0 / 0 / 1 |
| Book-through | $6,853.18 | -35.17% | 0 / 0 / 1 |
| Public trade-through | $6,853.18 | -35.17% | 0 / 0 / 1 |

This rejects Recipe B on the reconstructed event population. It does not
falsify the source's displayed B history because none of its five visible B
rows is a B event under the reconstructed labels and the missing 15-event
source population cannot be recovered from the repository. No fresh B event
exists in the Jul 27 partition.

Recipe B artifact SHA-256 values:

- touch: `0e46c6397a2081c4e2c4615b17c96a37f8204b2a46dce03da2246df1e0578047`
- through: `f4677525fb36d8902d3a11b386b22d35b9f80de0b63ec2ce9ddbc0ed865da391`
- trade-through: `7b1da475f723ddc05c679656409b68675508cc37bce22e9df1bc3346e90524c9`

The ML4T preflight stops here. Twenty-five cross-fill Recipe C consensus labels
plus two nonrepresentative Recipe B events cannot support defensible purged
walk-forward model comparison. Even perfect recovery of currently
`not_submitted` local outcomes would raise the resolved population only to
about 30. Fitting LightGBM, a time-series model, or a direction selector now
would primarily fit path and label-version noise. Model authority remains
observe-only while new venue-matched events are collected.

Final verification passed 1,105 non-network Python tests with four deselected
and 31 warnings, all 33 Rust TUI tests, 36 focused source/replay tests,
task-scoped Ruff and formatting, artifact accounting and hashes, file/function
size limits, diff hygiene, and fail-closed CLI status.
