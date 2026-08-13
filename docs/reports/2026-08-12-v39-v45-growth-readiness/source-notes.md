# Hypervector v39 → v45 $5,000 Growth Readiness — source notes

## Evidence boundary

- The report is frozen from the v39 checkpoint generated at `2026-08-12T11:35:41.719683+00:00` and its 62/62 complete portfolio archive.
- Current-run economics are exact v39 lifecycle accounting. All-time route economics are explicitly mixed-contract descriptive history.
- v45 sizing and friction are bound to base profile fingerprint `e1b46ba749a46cc2966f0b4629bfd487c3d6dfe1a29de745d9f9eb7c8e22c6f5`.
- The isolated v45 observer has a different fingerprint because every ledger path is rebound; a regression proves provider, asset, sizing, and exit contracts are unchanged.
- Adaptive 0.75×/1.00×/1.25× notional tiers are counterfactual only. No tier has execution authority.

## Chart map

1. `all-time-pnl`: signed route-level all-time net PnL. This exposes revision-mixed concentration and leave-largest fragility better than an aggregate equity headline.
2. `regime-accuracy`: pooled and episode-onset primary-regime directional accuracy at 5/15/30/60 minutes with a 50% reference line.
3. `v45-slot-risk`: deterministic $5,000 p99 stop-wave contribution for the mutually exclusive BTC slot, HYPE, and SP500.

## Deliberately omitted views

- No monthly income projection: compatible v45 trade frequency and expectancy do not exist yet.
- No covariance heatmap: the prior eight-asset exact return panel had zero common timestamps.
- No ten-slot allocation chart: v45 has three actual assets; ten is account capacity, not an allocation plan.
- No variable-leverage performance curve: at fixed notional leverage changes collateral and liquidation headroom, not trade PnL. At fixed margin it merely scales notional and confounds signal quality with exposure.

## Interpretation and validation rules

- Hyperliquid documents initial margin as notional divided by leverage and isolated liquidation as dependent on isolated margin. This supports fixed 5x leverage with adaptive notional as the cleaner experimental control: <https://hyperliquid.gitbook.io/hyperliquid-docs/trading/margining> and <https://hyperliquid.gitbook.io/hyperliquid-docs/trading/liquidations>.
- Readiness is prerequisite completion, not win probability and not a sizing score.
- The p99 stop wave stacks marginal estimates. It is neither a joint-probability forecast nor a maximum-loss guarantee.
- A future 1.25× tier requires a predeclared compatible route window that is positive after realized fees, funding, and slippage and remains positive without its largest winner. Technical gaps or adverse evidence map to 0.75×. These criteria are proposed experiment rules, not current execution gates.
- Any strategy/profile transition remains blocked until v39 and venue state are flat and owned-order-free, followed by a fresh mainnet preflight and explicit live-risk authorization.
