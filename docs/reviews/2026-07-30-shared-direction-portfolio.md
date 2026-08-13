# Shared BTC direction portfolio review — 2026-07-30

## Correction: short and combined lanes are superseded

The short selector in this report consumed one-minute candles even though its
12-100 bps range gate is a completed-five-minute runtime rule. The standalone
hourly long lane is unaffected, but the short and shared-portfolio results are
not valid promotion evidence. A regression test now requires five-minute
resampling, and the core selector rejects one-minute inputs. Retain this file
only as an audit record; do not use its short or combined statistics for a
configuration decision.

Follow-up: the corrected completed-five-minute replay has now been run with
the active `[06:00,15:00)` short session. Short-only ended at $28,511.41; the
shared short-plus-long account ended at $28,521.80 but worsened maximum
drawdown from -12.22% to -18.23%. The $10.38 equity improvement does not justify
the additional long tail. The authoritative follow-up is
`docs/reviews/2026-07-30-source-session-gate-and-shared-direction.md`; the
historical figures below remain an audit record rather than decision evidence.

## 1. Problem restatement

This review tests whether the frozen source-follow short and the
annotation-only liquidity-sweep long can share one $15,000 BTC portfolio
without inventing parallel capital or overlapping positions. The comparison is
report-only and does not change the running shadow strategy, ML authority, or
TUI execution authority.

The measurable contract is one pending entry or open BTC position, 35% isolated
allocation, 30x leverage, an 8% gross margin target, a 60-second post-only entry,
a 60-second post-exit cooldown, and a 24-hour maximum hold. The long uses its
frozen 18% margin stop (60 price bps); the short retains no stop. A signal seen
while occupied is ignored and cannot become a stale entry after the portfolio
returns flat.

## 2. Known facts and assumptions

- Source-follow shorts remain available at their exact causal five-minute
  decision time.
- A completed hourly long signal is available only at the following hour.
- An exact simultaneous collision gives the source-follow short priority.
- Public trade-through is required for maker entry fills. It cannot reveal the
  private queue position or cancellations ahead of the simulated order.
- Fees, authentic funding, mark/oracle context, isolated liquidation, target,
  stop, and maximum-hold exits are evaluated on one chronological tape.
- The interval informed candidate selection and is not a holdout.

## 3. Exact 91-day results

The replay processed 12,202,083 canonical L2 snapshots and 36,931,672
deduplicated public trades from 2026-04-28 through 2026-07-28. It observed 33
short signals, six long signals, and no exact simultaneous signal collisions.

| Lane | Filled trades | Targets | Stops | Liquidations | Time exits | Net PnL | PF | Max DD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Short control | 26 | 23 | 0 | 2 | 1 | -$5,413.90 | 0.56 | -60.74% |
| Long control | 5 | 4 | 1 | 0 | 0 | +$376.31 | 1.32 | -7.39% |
| Shared portfolio | 29 | 26 | 0 | 2 | 1 | -$4,684.19 | 0.63 | -59.77% |

The shared lane admitted four long trades and all four reached target. The
standalone long stop at 2026-07-13 01:00 UTC was correctly ignored because a
short position opened ten minutes earlier and remained active. The long arm
improved final equity by $729.71 relative to the short-only control and reduced
maximum drawdown by 0.97 percentage points, but it did not repair the short
tail.

One short filled in the control but expired in the shared lane. Both lanes
submitted the same $75,215 limit at 2026-05-27 13:35 UTC. Earlier long profits
made the shared order larger: it required 1.93809013 BTC versus 1.84549089 BTC
in the short control. Only 1.92501 BTC of qualifying public aggressor-buy volume
traded through the limit during the order lifetime. This is an equity-dependent
queue-volume outcome, not arbitration displacement.

## 4. Failure modes and uncertainty

- Two short liquidations and one 24-hour short loss dominate 26 targets. The
  current shared candidate therefore has negative execution economics.
- Confidence and completed range do not separate those short losses from the
  targets; adding either threshold would be retrospective over-gating.
- Five long fills are too sparse to estimate stable expectancy or tail risk.
- Twenty-one declared empty-book hours make the full-window report
  conservatively non-conclusive, although no order or position overlapped an
  empty-book interval (`active_book_gap_windows=0`).
- Shared compounding changes future order quantity, which can change whether
  public trade-through volume is sufficient. Independent-lane PnL cannot be
  added mechanically to predict a shared result.

The long hypothesis would be falsified by a frozen forward PF at or below one,
a liquidation, repeat stop losses, or causal decision mismatch. The shared
candidate is already rejected by this interval unless a replay-accounting error
is found or a predeclared independent window reverses the short-tail result.

## 5. Validation and recommendation

1. Keep the long signal annotation-only and collect decision-time forward
   outcomes from the live venue feed.
2. Replay the frozen long on the older gap-free archive blocks to expand exact
   execution evidence without changing its parameters.
3. Diagnose the two recent short liquidations using path evidence. Do not add a
   confidence, range, time-of-day, or regime gate unless it separates losses on
   independent data.
4. If a causal short-tail rule is identified, test the unchanged control, short
   challenger, long control, and shared portfolio on identical tape.
5. Keep the current runtime unchanged until an evidence-supported candidate is
   frozen for a clean $15,000 forward shadow run.

Recommendation: retain the long challenger, reject promotion of this combined
configuration, and focus the next bounded experiment on short-tail containment.
The simpler alternative is long-only shadow annotation; it has materially lower
historical drawdown but nowhere near the requested income and remains sparse.

Confidence is high in the one-position arbitration and relative replay result,
subject to public-queue uncertainty. Confidence is low-to-medium that the long
signal has a durable edge and high that the tested shared configuration is not
currently promotable.

## 6. Evidence identity

- Corrected immutable replay:
  `data/logs/research/hypervelocity_shared_direction_20260428_20260728_trade_through_hv35x30_v2.json`
- Corrected replay SHA-256:
  `d41ea4da5147495f5df3cda2d03c44b9810640b3f0a95b8b03d3a97add4c3c56`
- Long freeze:
  `data/logs/research/hypervelocity_liquidity_sweep_long_forward_freeze_20260730T1200_v2.json`
