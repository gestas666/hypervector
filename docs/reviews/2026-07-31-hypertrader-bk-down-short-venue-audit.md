# Hypertrader BK_DOWN short venue audit

Date: 2026-07-31

## 1. Problem restatement

Hypertrader added a paper-only BTC cell at commit
`5010d6b0ca9384decd0d74026160a1f2d5ed4dd9`: enter short on a completed-5m
`BREAKOUT/BK_DOWNWARD` onset with source confidence at least 0.70, any UTC
hour, no stop, and a 24-hour maximum hold. The published close-only search
reported 27/27 targets using a 20-bps or 130-point first-hit target.

The validation question is whether that exact signal family has positive
expectancy under causal Hyperliquid execution, mark liquidation, funding,
fees, one-position state, and public maker trade-through. This experiment is
report-only and cannot alter the running backend, TUI, strategy config, or ML
authority.

## 2. Known facts and assumptions

- The classifier core files are byte-identical between Hypertrader revisions
  `ad15f2bd` and `8a784ea1`; the new commit changes the paper recipe, not the
  regime formula.
- The deterministic Hyperliquid reconstruction produces 57 qualified onsets
  over 2025-07-28 through 2026-07-28 and only four on its trailing 8,000 bars.
  Hypertrader's absent SQLite label store prevents reproduction of its 27-event
  population.
- Fifty-three events lie inside executable archive windows. Four events fall
  inside declared multi-day provider gaps and are excluded rather than
  imputed.
- Each replay starts with $15,000, risks 10% of current equity as isolated
  margin, uses a 60-second post-only maker TTL, and requires public
  trade-through beyond the limit price.
- Target execution is the first of an 8%-margin relative target or 130 BTC
  points, matching the source's logical OR. Entry and target use the configured
  maker fee; liquidation uses taker friction. Authentic funding and causal
  Hyperliquid mark context are applied.
- The leverage surface was frozen before replay at 20x, 25x, 30x, 35x, and
  40x. No arm uses a stop or an implicit performance gate.

## 3. Venue results

| Leverage | Filled / resolved | Targets | Liquidations | 24h exits | PF | Compounded equity | Return | Positive blocks | Worst block DD |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 20x | 41 / 40 | 35 | 0 | 5 | 0.532 | $13,461.24 | -10.26% | 8/15 | -6.63% |
| 25x | 41 / 40 | 35 | 1 | 4 | 0.489 | $12,814.93 | -14.57% | 8/15 | -9.69% |
| 30x | 40 / 39 | 34 | 3 | 2 | 0.471 | $12,320.05 | -17.87% | 8/15 | -10.21% |
| 35x | 40 / 39 | 34 | 4 | 1 | 0.559 | $12,598.24 | -16.01% | 8/15 | -9.96% |
| 40x source control | 40 / 39 | 31 | 8 | 0 | 0.374 | $10,822.21 | -27.85% | 6/15 | -11.35% |

The 40x source control confirms that an adverse excursion near the published
worst MAE can cross Hyperliquid's isolated liquidation boundary before a later
target. Lower leverage prevents some or all liquidations but converts the same
paths into losing 24-hour exits. It therefore improves the loss magnitude
without creating positive expectancy.

The 20x and 25x arms filled one additional order because their lower notional
required less public trade-through volume. That stateful capacity difference
is retained in the result; signals were not deleted.

The later 2026-04-28 through 2026-07-28 tape contains 21 declared empty-book
hours. `active_book_gap_windows=0` for every arm, so no pending order or open
position crossed those hours. The general execution-economics flag remains
conservatively false because the archive is not globally complete.

## 4. Uncertainty, risks, and failure modes

- Public trade-through cannot reveal private queue priority, cancellations, or
  participant identity. Real maker fill conversion can differ.
- The source's 27/27 event population remains unavailable. A recovered,
  checksum-identical source label store could materially change event
  membership and would require a new audit.
- The 15 replay blocks reset at declared archive gaps. Compounded equity is the
  product of block return factors, not a fabricated continuous event tape.
- The target's 130-point branch yields less than 8% margin return when BTC is
  sufficiently above $65,000. This is source-faithful but makes the displayed
  “8%” description price-dependent.
- Selection bias remains substantial because the upstream recipe was chosen
  from a grid. The later tape is diagnostic, not a pristine holdout after the
  recipe became known.

Confidence is high that the reproducible source recipe is negative on this
venue tape and high that reducing leverage alone does not repair it. Confidence
about unrelated BK_DOWN models is low; this experiment falsifies one explicit
entry/exit contract, not the entire feature family.

This conclusion would be updated by an accounting defect, recovered source
labels that reproduce the claimed 27 events, or a preregistered forward sample
whose executable PF remains above one with controlled tail loss.

## 5. Validation performed

- Added unit contracts for onset uniqueness, causal five-minute availability,
  confidence threshold, 24-hour hold, 10% isolated allocation, 130-point target,
  and the frozen leverage surface.
- Added exact support for the source's relative-or-absolute first-hit target.
- Ran 137 focused maker/source regression tests and Ruff before the surface.
- Replayed every eligible event with authentic L2, public trades, mark context,
  funding, fees, liquidation, and one-position state.
- Generated immutable cross-block robustness reports with source artifact
  hashes and leave-one-block-out diagnostics.

## 6. Recommendation and trade-offs

| Option | Evidence | Decision |
|---|---|---|
| Promote creator 40x cell | PF 0.374, eight liquidations, -27.85% | Reject |
| Substitute 20x-35x | Every arm PF below 0.56 and loses compounded equity | Reject |
| Add a stop to this cell | Upstream grid already showed stops cut later winners; current no-stop path is negative | Shelf |
| Keep BK_DOWN as annotation | Preserves information without execution authority | Acceptable |
| Continue active TREND_DOWN source-follow shadow | Separate signal family and forward test | Continue unchanged |

No runtime, config, backend process, TUI behavior, or ML authority changed.

## 7. Evidence identity

- 20x robustness SHA-256:
  `4f655f77b4ff0a4a960fbe9663e01a0c793c1569efd7d39c9214c86662fc88f0`
- 25x robustness SHA-256:
  `83f533b825e4a205d878043573df1064f5ac7284bb62e64be4c78c87d443fc6e`
- 30x robustness SHA-256:
  `ee2bb715e5789d59a5b5a8b06f2ec0ddf297f38b04c88c16f1dc13812d1821d8`
- 35x robustness SHA-256:
  `20ef77058ea5bb3c8b70f093914c625601368f5e9213222bc285b60adb4dcdf2`
- 40x robustness SHA-256:
  `2892a37bac4832a78ff2fa25977002f6a02327c83aad9f9a6195d13ed67d3a6a`
