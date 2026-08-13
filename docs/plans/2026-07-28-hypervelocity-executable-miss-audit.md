# Hypervelocity Executable-Miss Audit

## Problem restatement

The canonical 5m structural direction matches 20 of 23 outcome-backed creator
entries, but the actual executable `entry_direction` matches only 17. This
audit asks whether the six misses have a causal, sufficiently selective
signature that justifies another stateful replay without weakening the
source-faithful runtime or adding a broad entry gate.

Runtime, TUI, fixed 8% target, 70% allocation, BTC 40x leverage, one-position
policy, and ML observe-only authority are unchanged.

## Evidence and assumptions

- Bars: `data/cache/BTC_1m_90d.parquet`, SHA-256
  `7ecfcf42cafe4143c6bfe525a47209a40f23fd3e53d31f8be572dbb5d4e29e43`.
- Faithful config: `configs/hypervelocity_faithful.toml`, SHA-256
  `801d2c7af3c1211c13fea49dda673fdb8ed40ff0909692e9cebad070c0e3246f`.
- Base creator positions: SHA-256
  `68b40a3b9afc9ec584fc30b4887e2f9092d025b312e599bbaf5f175bd4a7c430`.
- Supplemental screenshots: SHA-256
  `ca315315af09406d8c7c987d422285e59970c991739d2105ff7eedec8c99412e`.
- Every bar/regime value is shifted to its completed-bar availability time.
- L2 uses the latest verified Hyperliquid snapshot at or before the creator
  timestamp with a two-second maximum age. Displayed liquidity is not private
  queue or hidden-liquidity evidence.

## Six executable misses

Three entries are genuine early reversals against canonical 5m structure:

| Time UTC | Side | 1m | 5m | 15m | Canonical age |
|---|---|---|---|---|---:|
| Jul 20 00:52 | short | TREND_DOWN | TREND_UP | TREND_UP | 32 bars |
| Jul 22 01:17 | short | TREND_DOWN | TREND_UP | TREND_UP | 77 bars |
| Jul 23 13:33 | long | TREND_DOWN | TREND_DOWN | TREND_DOWN | 48 bars |

Three entries have the correct 5m breakout side but canonical execution still
awaits its narrow 1m confirmation:

| Time UTC | Side | 1m | 5m | 15m | Breakout age |
|---|---|---|---|---|---:|
| Jul 20 18:19 | long | TREND_UP | BREAKOUT | TREND_UP | 4 bars |
| Jul 23 12:35 | short | TREND_DOWN | BREAKOUT | TREND_DOWN | 0 bars |
| Jul 23 12:43 | short | TREND_DOWN | BREAKOUT | TREND_DOWN | 8 bars |

The existing report-only 1m-trend breakout challenger recovers the latter
three trade-backed directions. It is not promoted because its exact source
window worsened from $114.37 to $99.48 and from -77.78% to -80.79% drawdown.

## Reversal and microstructure audit

The price-only Pine Trend State points in the creator direction at all three
early reversals. Their source-direction RSI gaps are +3.54 to +10.64 and their
source-direction Pine dominance is +0.436 to +0.872. This is association, not
a selective trigger:

- requiring opposite Pine/canonical direction;
- a Pine state age below ten bars;
- source-direction RSI alignment;
- Pine dominance of at least 0.40; and
- a canonical episode age of at least 15 bars

still marks 18,179 bars, 6,357 rising edges, and 636 canonical structural
episodes over 90 days. The already completed Pine integrations similarly
created about 935-955 bar trades and 139-141 liquidations.

Orderbook pressure does not repair the ambiguity. Source-direction OBI5 spans
-0.701 to +0.843 across the three reversals, while source-direction OBI20 is
opposed on all three (-0.534 to -0.107). The three breakout waits also have
opposed source-direction OBI5. This is compatible with pullback timing but
contradicts a simple direction-confirming OBI gate.

## Strength and repeated-entry screens

Canonical resolved targets and liquidations overlap heavily in causal regime
strength: median percentiles are 47.36 and 45.00. A strength-60 fixed-lifecycle
screen has 16/0 and 17/1 target/liquidation counts in the first two 30-day
slices, but fails the latest slice at 12/3 with -$129.40 additive PnL. It is not
a stable canonical gate.

The hard-BBWP/recovery interaction has a superficially favorable
fixed-lifecycle strength-50 screen in all three slices. The charter requires
performance screens to remain reported results rather than implicit trial
aborts, so the exact stateful follow-up was completed despite its known source
penalty. Applying the mask removes 19,401 directional bars and reduces exact
creator eligibility from 17/35 to 14/35, versus 24/35 for canonical.

The stateful result reverses the fixed-lifecycle association. Control retained
$2,466.13 with -97.83% maximum drawdown; strength 50 retained only $244.62 with
-99.37% drawdown. Full liquidations fell from 39 to 35, but partial
liquidations rose from 15 to 25. The candidate's first two 30-day slices grew,
then its latest slice collapsed to 0.0144x with 17 full liquidations. It is an
unstable path substitution and not a loss-control repair.

Strength also fails as the harder barrier for mature same-side continuation.
Thirteen of 14 observed creator continuations are at strength 40 or higher,
but applying that requirement to the mature cap-2 replay's candidate-only
lifecycles removes 24 eventual targets and only two liquidations. Every
30-day fixed-lifecycle slice remains negative. This closes regime strength as
the missing selective continuation trigger.

## Risks and failure modes

- The 23 outcome-backed rows are selected, clustered, and mostly winners.
- Exact creator venue/queue state remains unavailable.
- Fixed-lifecycle screens do not model later stateful path substitution; they
  may reject weak candidates cheaply but cannot establish profitability.
- The creator's aggregate loss counts do not expose losing entry/exit rows or
  exit reasons, so the dominant 40x loss mechanism remains unidentified.

## Decision and falsifiers

No reversal override, OBI rule, strength gate, or strength-conditioned
same-side re-entry advances to runtime. Confidence is high that the tested
signatures are too broad or unstable on this archive and medium for future
generalization. The strength replay artifact is
`data/logs/research/hypervelocity_hard_recovery_strength50_20260728.json`,
SHA-256
`1b6ad570f187efe1d5c02b9038956dbc5babdc9385e55ab179ad23cc5e19602a`.

This decision would be updated by either:

1. new creator entries repeatedly showing the same causal miss signature
   without selection ambiguity; or
2. a creator losing-trade row with entry/exit timestamps, prices, side, size,
   and exit reason that identifies the missing loss-control lifecycle.

The current `data/paper` ledger stopped on 2026-07-27 at 05:50 EDT with zero
fills and no Hypervelocity backend process was running at audit time. The older
visual ledger contains the already-reviewed successful long and immediate
same-side re-entry, not a fresh validation window.
