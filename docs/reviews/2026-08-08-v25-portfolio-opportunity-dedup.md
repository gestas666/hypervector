# V25 portfolio opportunity deduplication acceptance

**Observed:** 2026-08-08 14:08 EDT  
**Run:** `bidirectional-live-1786182011216`  
**Profile:** `multi_asset_bidirectional_complete_portfolio_canary_v25`

## 1. Problem restatement

Provider-level forward diagnostics could count one symbol, direction, decision
minute, and completed-candle path once for every strategy that observed it.
This overstated the apparent number of missed opportunities and could make one
market move look like independent confirmation from several strategies.

Success required a report-only portfolio measurement that preserved each
provider and blocker attribution while counting the shared causal market path
once. It could not place, close, resize, route, gate, promote, or restart live
execution.

## 2. Known facts and assumptions

- The source ledger retains source run, symbol, decision minute, side,
  reference price, strategy, and exact blocker for every provider evaluation.
- In the sampled HYPE window, breakout and range-onset repeatedly used the same
  source run, symbol, minute, side, and reference price. This directly proves
  cross-provider double counting was possible in the prior aggregate view.
- A unique directional path is identified by source run, symbol, decision
  minute, and side. Opposing sides are distinct hypotheses and are surfaced as
  competition rather than merged.
- Providers with different reference prices for the same causal identity are
  excluded from resolved path statistics. The report never chooses one price
  silently.
- Paths remain completed-candle counterfactuals. They do not model an order,
  queue, fill, capital contention, fees, funding, liquidation, or realized PnL.

## 3. Implemented measurement

`signal_outcomes.portfolio_opportunity_dedup` now reports:

- raw one-blocker directional provider observations;
- unique directional causal paths;
- duplicate provider observations removed;
- cross-provider overlap composition by exact strategy and blocker;
- same-minute opposing-direction competition;
- reference-price conflicts; and
- raw and non-overlapping 5/15/30/60-minute opportunity evidence.

The prefix-delta workflow compares cumulative portfolio evidence only when both
prefixes contain it. The first prefix that introduces the field is labeled
newly available and non-comparable, preventing a fabricated historical delta.

## 4. Measured result

| Measure | Result | Interpretation |
|---|---:|---|
| Provider observations | `3,199` | Raw one-blocker directional annotations |
| Unique directional paths | `2,091` | Causal paths after provider deduplication |
| Duplicate observations removed | `1,108` (`34.64%`) | Prior provider-level inflation |
| Cross-provider path groups | `966` | Unique paths observed by multiple strategies |
| Direction competitions | `1` | Same symbol/minute had opposing hypotheses |
| Reference-price conflicts | `0` | No inconsistent causal price in this prefix |

The largest overlap was 708 paths shared by HT-Breakout's
`5m_not_breakout` blocker and range-onset's `awaiting_hourly_sma_cross`
blocker. Those are now one market path with two provider attributions, not two
independent opportunities.

| Horizon | Independent paths | Cost-clearing close | Robust MFE | Mean close after 13 bps hurdle |
|---|---:|---:|---:|---:|
| 5m | `472` | `23` (`4.87%`) | `13` (`2.75%`) | `-12.65 bps` |
| 15m | `201` | `14` (`6.97%`) | `15` (`7.46%`) | `-11.06 bps` |
| 30m | `101` | `15` (`14.85%`) | `14` (`13.86%`) | `-8.80 bps` |
| 60m | `55` | `13` (`23.64%`) | `14` (`25.45%`) | `-9.45 bps` |

This cumulative portfolio result does not support broadly loosening the
one-blocker gates. Even at 60 minutes, the mean close after the fixed hurdle is
negative. The higher long-horizon MFE rates may justify narrower provider- and
context-specific exit research, but not a route or live-policy change.

## 5. Validation

- Red-green tests proved that identical paths collapse, opposing sides remain
  distinct, conflicting prices are excluded, portfolio maturity is measured,
  and first-introduction prefixes remain non-comparable.
- Focused signal, opportunity, delta, candidate, and order-book suite:
  `37 passed`.
- Full non-network Python suite: `4,115 passed, 4 deselected`; 27 existing
  dependency/deprecation warnings were reported.
- Ruff check and formatting pass for the changed Python sources and tests.
- Production modules remain below 500 lines: 218, 422, and 260 lines; no
  changed function exceeds 50 lines.
- Immutable cumulative audit:
  `data/logs/research/bidirectional_cohort/v25_live_prefix_portfolio_dedup_bidirectional-live-1786182011216_20260808T180817Z.json`,
  SHA-256 `68bb0db6fc216fc761ed118edc2eb66760d9b952280c96cf068c04a4bf9b62b4`.
- Immutable first-introduction delta:
  `data/logs/research/bidirectional_cohort/v25_live_prefix_delta_portfolio_dedup_v4_20260808T173226Z_20260808T175859Z.json`,
  SHA-256 `7cfc08f51c84785ece9ac92757b089a068388ccf1fc945cbf5946697846716a8`.
- Immutable comparable deduplication delta:
  `data/logs/research/bidirectional_cohort/v25_live_prefix_delta_portfolio_dedup_comparable_v4_20260808T175859Z_20260808T180817Z.json`,
  SHA-256 `e026c1c06f15cc6b6910c596dab088dcfb9a0e50c061ccfd49ddea34583cc776`.
  It added 56 provider observations but only 38 unique paths; all seven newly
  independent five-minute paths failed to clear the fixed cost hurdle.
- At 18:12:40 UTC, launchd still reported PID `37897`, one run, and no exit.
  The checkpoint was `running_consistent`, fault-free, runtime/profile matched,
  and drain-inactive. BTC, SOL, GOLD, and SPCX retained stop OIDs
  `512826131342`, `512630736897`, `512544517709`, and `512769547957`; BTC also
  retained target OID `512826144316`.

## 6. Risks, falsifiers, and recommendation

Confidence is high that exact same-side provider paths are no longer counted
as separate portfolio opportunities. Economic confidence remains low because
these are counterfactual paths rather than executable lifecycle outcomes and
because capital contention across symbols is not modeled.

The technical claim is falsified by merging different sides, accepting
reference-price conflicts, counting the same causal identity twice, allowing
cumulative counts to move backward, or producing any execution side effect.
The economic conclusion changes with provider-specific independent evidence
that remains positive after executable friction and subsequently agrees with
resolved live lifecycles.

| Option | Benefit | Failure mode | Decision |
|---|---|---|---|
| Retain v25 and continue unique-path monitoring | Preserves live truth and honest sample size | Requires more elapsed evidence | Selected |
| Loosen all one-blocker gates | More entries | Current independent after-hurdle means are negative | Rejected |
| Tune one provider/context challenger offline | Tests the long-horizon MFE lead | May not survive fills or capital contention | Research only |
| Restart while four positions remain open | Loads staged code | Mutates active management and protection assumptions | Deferred |

No live process, order, position, stop, target, size, route, or policy was
changed by this work.
