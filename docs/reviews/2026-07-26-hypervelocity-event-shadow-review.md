# Hypervelocity Event-Shadow Review — 2026-07-26

## 1. Problem restatement

The backend must remain the only Hypervelocity strategy and execution authority.
Shadow execution must consume public Hyperliquid L2/trade evidence, preserve the
fixed strategy contract, model venue friction without fabricating fills, survive
restart, and expose enough provenance for the TUI to remain a read-only view.

Success means one event-authoritative shadow runtime, no candle-fill fallback,
durable partial order state, explicit uncertainty, venue costs and isolated
margin in the ledger, and no live order client in paper/shadow mode.

## 2. Known facts and evidence

Confidence is high for the tested implementation paths:

- `runtime.shadow_execution_model = "nautilus_event_v1"` is validated and
  activates the backend event port.
- Public mainnet WebSocket L2/trade frames are bounded, normalized, archived
  before consumption, and reconnect/overflow gaps remain explicit.
- Submit/cancel latency, displayed queue-ahead, ALO rejection, partial fills,
  proportional reduce-only targets, maker fees, hourly funding, and isolated
  maintenance liquidation are deterministic under recorded fixtures.
- A stale book or declared stream gap preserves orders and cannot become a
  success-shaped fill.
- Restart restores partial entry quantity, active targets, fees, funding,
  cooldown/episode state, and order identities. Unknown queue priority is
  conservatively re-established behind current displayed liquidity.
- Observe-only metalabel output is recorded but cannot filter or resize an
  order.
- Funding is applied before the boundary liquidation check, so a funding debit
  can trigger liquidation without a one-bar delay.
- Liquidation uses the configured taker fee and zero separate clearance fee.
  The ledger identifies it as a venue-enforced market close, not a post-only
  strategy order.

Verification evidence:

- `uv run pytest tests/ -q -m "not network"`: 579 passed, 4 deselected.
- `cargo test -p hypervector-tui`: 23 integration tests passed.
- `uv run python -m hypervector status`: healthy; shadow no-submit and live
  fail-closed flags reported.
- Targeted Ruff, Ruff formatting, `cargo fmt`, Python compile, TOML/profile
  parsing, and `git diff --check`: passed.
- A bounded real public mainnet feed smoke received subscription, L2, and trade
  messages without constructing an order client.

## 3. Review reasoning and traceability

| Requirement | Implementation evidence | Automated evidence |
|---|---|---|
| One position and target-only lifecycle | Pure coordinator and typed commands | Runtime/controller/session tests |
| Event-authoritative fills | Public L2/trade pump to shadow port | Pump, feed, friction tests |
| No uncertain fills | Freshness and gap state block matching | Gap/stale-book tests |
| Partial fill fidelity | Cumulative quantities and proportional targets | Friction/controller/restart tests |
| Fee/funding accounting | Exact event fee override and hourly transfer parity | Fill/session/liquidation tests |
| Isolated liquidation | Hyperliquid maintenance boundary and mark check | Margin/friction/session tests |
| Restart continuity | Durable orders, targets, costs, IDs, and episode state | Resume/event-runtime tests |
| TUI remains display-only | No Rust execution changes; backend rows only | 23 Rust integration tests |
| Paper/shadow never submit | Public-only feed and no execution client | CLI/status and daemon tests |

## 4. Uncertainties and failure modes

Confidence is medium for exact live-venue friction outside the tested contract:

1. The shadow liquidation model closes the full position at the supplied mark.
   Hyperliquid documents a 20% first market liquidation for positions above
   $100,000, followed by a 30-second cooldown in which later liquidations are
   full size. The normal $10,000 shadow portfolio at 70% margin and 40x is about
   $280,000 notional, so this path is material. The session explicitly stamps
   `partial_liquidation_supported=false` and
   `full_at_mark_shadow_approximation_v1`.
2. Liquidation execution price is the supplied mark, not a walk through the
   contemporaneous book. The configured taker fee is charged, but market impact
   remains unmeasured.
3. Mark and funding refresh currently enter through public REST/candle cadence,
   not the continuous `activeAssetCtx` WebSocket stream. A fast liquidation
   between completed bars can therefore be detected late in shadow mode.
4. Public L2 cannot reveal hidden queue position or cancellations ahead of the
   order. The current policy is conservative but not venue-exact.
5. Shadow uses configured tier-0 fees. Account-specific discounts/rebates can
   only be reconciled in the explicitly armed live path.
6. The host's coverage instrumentation conflicts with NumPy under Python 3.13,
   so no trustworthy numeric coverage percentage was produced. Functional
   suites are green, but the >85% numerical claim remains unverified.

Evidence that would update these conclusions includes captured user
liquidation fills, account fee/funding history, active asset-context frames,
and side-by-side predicted-versus-actual queue outcomes from the $120 canary.

## 5. Next validation batch

The lowest-risk next batch is still no-submit:

1. Add and archive `activeAssetCtx` mark/oracle/funding events.
2. Drive liquidation checks from those events instead of completed-bar cadence.
3. Implement the documented >$100,000 20% liquidation attempt, 30-second
   cooldown, full follow-up, L2 market walk, and explicit backstop outcome.
4. Replay deterministic fixtures twice and require identical fills, fees,
   remaining position, and ledger state.
5. Then implement the mocked Nautilus Hyperliquid live execution port and
   account-specific preflight. No live command is armed in this batch.

## 6. Recommendation and trade-offs

| Option | Benefit | Cost/risk | Recommendation |
|---|---|---|---|
| Keep current model | Ready event-level entries/targets now | Liquidation timing/size remains approximate | Accept only with current explicit telemetry |
| Add continuous context and partial liquidation | Closes the largest known shadow-friction gap | More event and state-machine complexity | Do next |
| Start live adapter immediately | Reaches canary sooner | Calibrates against a known liquidation mismatch | Begin only after no-submit gap tests |
| Add strategy filters | May reduce trades | Violates the fixed strategy contract and confounds execution evidence | Do not add |

The recommendation would be falsified if recorded Hyperliquid evidence shows
that the documented partial-liquidation rules do not apply to this BTC position
class or if the active context stream cannot provide sufficiently fresh mark
events. In that case, retain the explicit approximation and use actual user
events as the only liquidation authority during the canary.
