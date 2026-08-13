# Hypertrader 1m Impulse ML v1 review — 2026-08-02

## 1. Problem restatement

Determine whether Hypertrader's `1m impulse ML v1` can serve as a lower-risk
Hypervelocity entry model or as another portfolio sleeve. This review is
read-only and grants no execution authority.

## 2. Observable implementation facts

- The BTC long gate fades downside extension below EMA21 with negative DI delta
  and five-bar ROC. The short gate fades upside extension. This is
  mean-reversion, not trend continuation or breakout.
- Hypertrader documents the TA-gated variants as RANGE-only.
- The v1 runtime constants use fixed price TP/SL rules and up to 40x ML-sized
  leverage, while the saved model evaluation uses ATR barriers, 45-minute
  maximum hold, and approximately 20x average leverage. This contract mismatch
  prevents treating the saved report as exact evidence for the current runtime.
- Hypervector's existing simplified port assigns the lanes `uptrend` and
  `downtrend` roles and uses a different default short gate. It is therefore not
  an exact port of the reviewed Hypertrader v1 runtime.

## 3. Saved Hypertrader evaluation evidence

The saved holdout starts at `2026-05-04T17:52:00Z`.

| Side | Production trades | Win rate | Profit factor | Total margin PnL | 2x-cost PnL | AUC |
|---|---:|---:|---:|---:|---:|---:|
| Long fade | 288 | 47.6% | 0.306 | -415.479% | -897.269% | 0.7395 |
| Short fade | 148 | 47.3% | 0.370 | -207.143% | -463.122% | 0.7948 |

Both saved gate reports fail net-return monotonicity, walk-forward OOS
comparison, deflated Sharpe, cost survival, and composite risk checks. AUC
therefore reflects label-classification ability without demonstrated economic
edge under the evaluated execution contract.

## 4. Risks and falsifiers

- Promoting the saved models would combine negative net expectancy with high
  leverage.
- Merging a range fade into Hypervelocity would make regime and attribution
  ambiguous.
- The saved evaluation could be stale or based on a contract that differs from
  current code.

The negative assessment would be updated by an exact, causal Hyperliquid replay
of the current source contract that includes fees, funding, queue/fill logic,
and produces positive net expectancy on a frozen forward window.

## 5. Recommendation

Do not use the saved v1 models for sizing or execution. Preserve the raw gate as
a separately named RANGE fade challenger at 3–5x leverage and observation-only
authority. Before replay, align the Hypervector port with one explicit source
revision, freeze TP/SL/hold semantics, and make the regime role `range` rather
than `uptrend` or `downtrend`.

Confidence is high that the saved v1 artifacts are not promotable as-is because
their own economic metrics are negative. Confidence is medium that a rebuilt
low-leverage range sleeve is worth testing; current evidence does not establish
positive expectancy.
