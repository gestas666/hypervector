# BTC beta sleeve (50% of book): rule and execution (2026-09-27)

**Operator approval (2026-09-27, in conversation):** "approved - opt in to auto-resume
after a host restart. The transition needs a drain, 50%,  install the daily-breakout
shadow runner". "50%" selects option 4 of docs/reviews/2026-09-27-v94-review-and-swing-research.md
§6: about half the book in 1x spot BTC on a 200-day switch.

**What it is.** This is labelled **beta, not edge**. It is the only exposure with positive
expectancy in the 2024–26 research. The SMA200 switch is a drawdown governor, not a
signal with edge.

Book-level history (single-author combination, not independently replicated):

| Period | CAGR | Max drawdown |
|---|---|---|
| 2024–26 | 13.3% | −17% |
| 2020–26 | 20.2% | −36% |

P(−50% in 12 months) ≈ 0.1%.

## Rule (explicit, as the charter requires)

- **Holding.**
  - Hold 1x UBTC (Hyperliquid spot pair `@142`, UBTC/USDC) while the last completed
    Binance BTCUSDT daily close is above its 200-day simple moving average.
  - Otherwise hold USDC.
- **Risk controls.** No leverage and no other stop. There is no drawdown or kill rule,
  and none is implied.
- **Signal.** The D1 shadow runner's daily `regime_tag` BTC switch state (`btc_beta_switch`),
  which launchd writes about 00:10 UTC under EDT.
- **Acting on a switch.**
  - Act only after that day's tag exists.
  - Act outside minutes :58–:03 of any hour. The live backend shares the host's
    Hyperliquid request budget.
  - If the tag is missing, compute it independently from Binance daily closes before acting.
- **Rebalancing.** Rebalance between the sleeve and the cohort account only during a
  cohort drain, or while the cohort is flat with no open orders. Any transfer changes
  the cohort's sizing equity immediately.

## Mechanism

- **Account.** A new Hyperliquid sub-account (suggested name `btc-sma200`) under the
  master wallet. The cohort (V94/V95) reads only the master's unified USDC. It never sees
  the sub-account and never sizes from it.
- **Who acts.** The operator, by hand, in the Hyperliquid web app with the **master**
  wallet. The engine's API agent `hl-api` cannot sign transfers.
- **Never, in the sub-account:**
  - approve another API wallet named `hl-api` (it would deregister the engine signer);
  - accept any account-mode or abstraction change on the master;
  - cancel or modify master orders from the UI.
- **Confirm before each sleeve action** that the UI's account selector shows the sub-account.
- **Custody.**
  - UBTC is Unit-bridged BTC: a 2-of-3 guardian MPC (Unit, Hyperliquid Labs, Infinite Field).
    It is not native BTC.
  - Its audit, insurance and recovery status is unknown.
  - Depeg risk exists if withdrawals halt.
  - Off-venue BTC is the fallback if this is unacceptable.

## One-time execution (2026-09-27/28)

1. **Create the sub-account** (UI → Sub-Accounts). The account is eligible: $329K all-time
   volume against the $100K requirement, with 0 existing sub-accounts.
2. **Transfer.** Only while the V94 transition drain is `active` (new entries are withheld)
   or the book is flat, outside :58–:03.
   - Amount: half the master's spot USDC total plus the ≈$3 AAPL dust, about $2,405.
   - Move it master → sub-account into its **Spot** balance.
   - Leave the isolated margin of any open position untouched.
   - If it lands in Perps, move it Perps → Spot inside the sub-account.
3. **Buy.** In the sub-account on `@142` (not `@234`, UBTC/USDH, which has no volume):
   - a limit buy, TIF IOC, at best ask × 1.001, rounded down to 5 significant figures;
   - size = floor((USDC − $2) / price, 5 dp).
   - Resubmit any remainder once at the new ask × 1.001, with a total cap of 25 bps.
   - A partial fill never delays the cohort. A $2.4K order fills at the touch today:
     spread 0.12 bps, $462K ask depth.
4. **Record** the sub-account name, fill price and size in HANDOFF.

## Effects on the cohort

- **Sizing.** V95 sizes from the master's remaining USDC, about $2.4K. The book check at
  $2,403 is 1.74% at-stop and 11.59% margin, which is accepted.
- **Evidence.** Any ladder or drawdown evidence must be anchored at equity **after** the
  transfer (the V95 start). A window spanning the transfer reads as −50%.
  `scripts/cohort_ladder_evidence.py --since` must start at or after the V95 start.
- **Visibility.** The cohort cockpit and checkpoint do not show the sleeve. Track book-level
  P&L as master plus sub-account.
