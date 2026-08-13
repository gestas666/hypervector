# SOL range-onset live-canary preflight

## Problem and success criteria

The $150 Hyperliquid canary is intended to validate real execution rather than
claim profitability. Before arming, the system must prove that the configured
account and SOL market can be inspected without signing capability, that the
live process remains fail-closed, and that venue state can be reconciled before
any signal evaluation.

Success requires mainnet SOL metadata matching the frozen contract, positive
account equity, enough notional for one venue lot, no unknown SOL exposure or
orders, a parseable account fee schedule and L2 book, and both explicit live
acknowledgement flags. These are technical-validity checks, not strategy
performance gates.

## Current verified state

- `SolHyperliquidReader` owns all account, metadata, order, fill, funding, and
  book reads. It has no exchange client or submission methods.
- `OfficialSolReadOnlySdkBuilder` accepts no wallet key and constructs only the
  official SDK `Info` HTTP client with WebSocket disabled on mainnet and a
  ten-second request timeout.
- Unified-account mode is detected explicitly. Its USDC equity comes from the
  spot clearinghouse state; the legacy perps summary is not treated as account
  equity in unified mode.
- The wallet-only dotenv loader ignores the signing-key field.
- The order-capable adapter is constructed only after live mode, `--enabled`,
  `--i-accept-live-risk`, wallet presence, and signing-key presence all pass.
- The authenticated factory then requires an API-agent signer whose parent is
  the configured funded account. A main-wallet key or mismatched agent is
  rejected before the Exchange client is constructed.
- One advisory process lock owns the live ledger and venue lifecycle. A slow
  live shutdown is left running with its STOP request rather than terminated
  during a possible order transition.
- Shadow and live modes own separate STOP files. Starting the no-submit observer
  cannot delete or consume a live backend's cleanup request.
- The one-terminal supervisor waits for a new run ID with the exact profile
  fingerprint and expected arm state before opening the TUI; an old ledger is
  not accepted as startup success.
- The frozen profile is SOL mainnet, 5x isolated, 3% margin, $22.50 maximum
  notional, one SOL position, 80-bps native stop, 48-hour maximum hold, and
  metalabel off.
- The focused SOL/live suite passed 138 tests, the TUI suite passed 43 tests
  with warnings denied under clippy, and the complete non-network Python suite
  passed 1,919 tests with four intentional deselections.
- The execution-incapable mainnet preflight observed `unifiedAccount`,
  $153.61038949 equity and withdrawable USDC, zero SOL positions, zero open
  orders, zero recent SOL fills, a 20x SOL venue maximum, 0.015% maker and
  0.045% taker rates, and a $22.50 planned canary notional. It reported
  `technically_ready=true` and `execution_client_constructed=false`.
- Credential identity is not ready: the configured signing key currently
  derives the funded main account and receives role `user`, not `agent`.
  Live construction now refuses this overprivileged pairing.
- Each entry, native stop, reduce-only close, and exact cancellation persists
  an identity before mutation. Lost responses use bounded exact CLOID/OID
  lookup and do not resubmit. Restart tests cover every intermediate lifecycle
  state, including rejected/canceled operations and a stop that fills before
  its acknowledgement or replacement becomes visible.
- The stale observer stopped through its control file without ledger reset.
  Fresh-code shadow is active under profile fingerprint
  `babd1167765a22160887fce4d2db35da83be4ba589fcf6496aebc4505b7d7daa`,
  remains flat, and reports no execution authority or place attempt.

## Failure modes and controls

| Failure mode | Detection | Control or rollback | Evidence still missing |
|---|---|---|---|
| Duplicate entry | Reconcile position and owned order IDs before every decision | Fault new entries; preserve verified stop | Mainnet race/latency |
| Partial fill | Poll actual fills and clearinghouse position | Stop only reconciled quantity; cancel residual where supported | Real partial fill |
| Entry without stop | Stop acknowledgement plus exact open-order reconciliation | Emergency reduce-only close and fault | Real stop acknowledgement |
| Stale account read | Bounded eventual-consistency polling | Refuse state transition after timeout | Mainnet propagation delay |
| Unknown position/order | Startup reconciliation ownership check | Fail closed; do not guess or cancel broadly | Funded-account state |
| Network timeout | Ten-second SDK timeout plus exact durable order identity | Recover by CLOID/OID without resubmission; restart protects or flattens reconciled exposure | Real mainnet transport behavior |
| Shutdown while open | Owned stop remains at venue | Stop process without canceling protection | Operator shutdown canary |
| Stop fills while offline | Restart matches exact owned stop fill | Recover OPEN to FLAT with recorded reason | Real offline fill |
| TUI/backend mismatch | Backend ledger defines mode, authority, run, and position | Display disconnected/mismatch; never infer trades | Live ledger session |
| Fee/funding mismatch | Venue fill fees and user funding ledger | Record signed deltas and compare with shadow | First real trade |
| Liquidation estimate mismatch | Clearinghouse liquidation price | Display venue value; never synthesize missing value | First real position |

## Validation sequence

1. Keep the now-verified funded main wallet address and restore the authorized
   API-agent signing key locally; never paste either into chat or commit them.
2. Run `uv run python scripts/sol_range_onset_preflight.py` and archive the
   sanitized report. This command has no live flags or execution client.
3. Require `technically_ready=true`, inspect any readiness reason, and verify
   the expected approximate $150 account value. A materially different balance
   is surfaced for operator review rather than silently resized.
4. Require signer role `agent` and require its returned parent to match the
   funded wallet before constructing an authenticated client.
5. Keep the verified response-loss/restart suite green after any execution
   change; current evidence is 138 focused and 1,919 full-suite tests.
6. Keep the fresh-code no-submit observer running until the signer is corrected.
7. Restore an authorized API-agent key, rerun role/parent and account preflight,
   then launch the one-terminal live backend/TUI with both explicit risk
   acknowledgements and monitor the first lifecycle continuously.

## Confidence and falsifiers

Confidence is high that the read-only path cannot place and high that the
funded account, unified balance, flatness, fee tier, and current venue contract
were reported correctly at the observed timestamp. Confidence is medium-high
for the offline-tested lifecycle and remains medium for real execution because
no mainnet fill, stop, cancel, funding, latency, or restart has occurred. Any
unexpected exchange-client construction during preflight, non-flat unknown
venue state, cap violation, duplicate exposure, unprotected position, or
ledger/TUI divergence falsifies readiness and stops new entries.
