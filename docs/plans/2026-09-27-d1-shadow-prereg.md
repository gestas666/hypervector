# D1 crypto breakout shadow (Sleeve S1): Stage-0 pre-registration
- **Date:** 2026-09-27.
- **Status:** pre-registered before the seed run. The file's sha256 and the commit that adds it are recorded in HANDOFF.md.
- **Seed-run recovery:** if the seed does not exit 0, or its last `daily_mark` is not `bar_date` 2026-09-26 in `mode: backfill`, move `ledger.jsonl` aside to a dated `*.partial` file (never delete it), re-run the seed into an empty ledger path, and do not load the launchd agent until the seed is clean.
- **Operator approval (2026-09-27):** "install the daily-breakout shadow runner".

## 1. Scope and hard limits
- This is an observe-only shadow of Sleeve S1 (D1 Donchian 20/10) from docs/reviews/2026-09-27-v94-review-and-swing-research.md, sections 3–5. `execution_authority: none`.
- **It places no orders.** It constructs no exchange or execution client, signs nothing, reads no wallet or API secret, and never calls Hyperliquid.
- Its only network peer is an HTTPS GET to data-api.binance.vision (Binance public spot 1d klines). An allow-list transport guard enforces this; redirects are refused and `trust_env` is off.
- Every run logs `http_requests_by_host=... hyperliquid_client=none`.
- It lives in `scripts/`, outside the live identity (the entrypoint, pyproject.toml, uv.lock and src/hypervector/**/*.py).
- It imports only the standard library, numpy, pandas and requests, and runs under `python -I`.
- Nothing in this lane arms, funds or sizes anything. Stage 2 (0.5% per trade) is a separate explicit decision by Albert, with its own sub-account, approval, `--enabled --i-accept-live-risk` and rollback.

## 2. Identity
- **Code:** scripts/d1_shadow_runner.py, sha256 `3496738ee6e98c8dd54ecb75f933b17aae80c36466b7eef3ca48ed713fba4471` (branch commit accb051; main commit `bc39f21`).
- **Config:**
  - Sizing: book_equity 4800 (static notional), risk_fraction 0.005.
  - Book limits: max_slots 10, gross_cap 1.5, min_fill_fraction 0.25.
  - Costs: funding_apr 0.1095, fee_bps 4.32.
  - Universe: universe_size 25, min_history_bars 90.
  - Config fingerprint `c9ea5f06dd1658e4`.
- **Census:** data/research/d1_shadow/census_perps.csv.
  - sha256 `0373cca0cb1eb11ae16e22f2fe46c75ad5003a600e1158076d35d14362e339ab`, mtime 2026-09-26T23:38:54Z.
  - 527 rows, 178 eligible main-dex rows, volume column `dayNtlVlm`.
- **Ledger:** data/research/d1_shadow/ledger.jsonl, schema `d1_shadow_ledger_v1`.
- **Changes:** any code or config change needs a new ledger path plus an amendment. The runner itself refuses a config change but not a code change, so the code hash above is the check.

## 3. Rule set (as implemented)
- **Universe:** frozen monthly. It is the top 25 HL main-dex crypto perps by census volume that have a Binance USDT spot pair with at least 90 completed daily bars before the month and a bar on the prior day. A pair priced more than 2x away from the census markPx is rejected.
- **Entry:** the daily close is above the prior 20-bar high (long) or below the prior 20-bar low (short); the signal bar is excluded. The fill is the next 00:00 UTC open.
- **Stop:** 2 x Wilder ATR(20) of the signal bar, measured from the fill. It is checked intrabar; an open beyond the stop fills at that open.
- **Exit:** the close breaks the opposite prior 10-bar channel; the fill is the next open. No max hold. Shorts are labelled hedge.
- **Book:**
  - At most 10 taken positions, and gross notional up to 1.5x book equity (a partial fill down to 25% of the wanted size is allowed).
  - Risk is 0.5% of $4,800 at the stop.
  - Leverage L = min(3, floor(1/(MMR + 2.5 x stop))), capped at 2 for shorts, with MMR = 1/(2 x maxLeverage).
- **Context tags only:** the BTC close vs SMA200 switch state, and SMA50/SMA200 for BTC, ETH and SOL.
- **Parity:** verified against the research engine from 2024-01-01 to 2026-09-25: 693 of 693 trades on the 22 coins that were members every month, stops within 1e-7.

## 4. Rule choices
- **(a) Universe volume:** the HL 24h `dayNtlVlm` snapshot at census capture. The current census has no trailing-30d column. A one-day spike can buy a month of membership. If a trailing-30d column is ever added, the runner prefers it automatically, which counts as a rule change and needs an amendment.
- **(b) Same-day priority:** trailing 30-day Binance USDT spot quote volume through the signal bar (not HL volume), then census rank, then coin.
- **(c) Always-in entries:** a coin still beyond its channel re-enters, not only on a fresh crossing. The builder reports this costs 5–9 re-entries, −4.5R to −8R. A signal that loses the slot race stays a virtual trade (`taken: false`) and blocks re-entry until it exits.
- **(d) Universe scope:** reversals and new entries apply only to coins in the current month's universe. A held coin that leaves the universe is managed to its exit, but it cannot reverse (`reversal_blocked: not_in_universe`).
- **(e) Order at the open:** a pending channel exit fills before the liquidation check (research-engine order). An open beyond the liquidation price is flagged `exit_beyond_liq_px`, and its loss is not capped at the margin. A gap beyond the liquidation price with no pending exit is booked `liquidation_gap` at −1/L.
- **(f) Backfill universes:** they use the 2026-09-26 census for every month, so they are not point-in-time (`frozen_by: backfill`, `point_in_time: false`). That includes September 2026. October 2026 is the first point-in-time month (census age 5 days).
- **(g) Seed:** `--backfill-from 2024-01-01`. The book depends on the seed; the book measured at the 2026-09-27 open for each seed is:
  - Cold start: WLD only.
  - 2026-09-01: 3 names differ.
  - 2026-07-01: 1 name differs.
  - 2026-01-01 and 2024-01-01: identical, converged since 2026-05-17.

  2024-01-01 is the research-engine parity window and the synthesis holdout start. It selects no particular book.

## 5. Census protocol
- Capture the census between the 24th and the last day of the prior month, UTC, so its age is 1–7 days at the month start. Place it with `cp -p`.
- October 2026 uses the 2026-09-26 census unchanged. Do not replace it before the October freeze has run.
- In the forward window, every `universe_frozen` event must show `frozen_by: daily` and `point_in_time: true`. A month that does not is reported, and its entries are analysed separately.
- A stale census (more than 7 days) stopping the run with exit code 2 is intended.

## 6. Forward plan: it tests execution, NOT edge
- **Forward window:** it starts at the first `mode: daily` `daily_mark`.
  - Seed events (`mode: backfill`) are context only and are excluded from every forward statistic.
  - Forward P&L is measured from the last seed mark. `hypothetical_equity_usd` already includes seed-period backtest P&L ($8,106 at the 2026-09-26 mark in rehearsal).
- **Measurements:**
  1. **Signal parity:** each month, re-run the research engine from 2024-01-01 through the latest mark on the ledger's universes. The target is 100% agreement on dates, sides and stops (within 1e-6). Every mismatch gets an erratum.
  2. **Stop slippage:** for each forward stop or gap exit, compare the booked price with the HL 1m path at the trigger. The synthesis criterion is median extra slippage of at most 50 bps.
  3. **Funding:** compare the flat 10.95% APR against realized HL hourly funding over each holding period. It flags if funding is sustained above 25% APR without a spot path.
  4. **Venue basis:** HL vs Binance at each entry and exit open.

  Measurements 2–4 need an offline reconciliation tool that is not yet built. It must be pre-registered as an amendment before the 4–8-week review, and it must fetch HL public data at low weight.
- **No edge conclusion:** a t of 2 needs about 3 years of trades. Shadow P&L is descriptive only and is not a gate.
- **Review:** after 4–8 weeks of clean parity, Albert decides on Stage 2 at 0.5% (never 2%). Any kill or drawdown rule for a funded sleeve must be declared explicitly by Albert (`SRS_HV1_NO_GATES`); none is implied here.

## 7. Operations
- **Schedule:** launchd at 20:10 and 22:10 America/New_York (00:10 and 02:10 UTC under EDT; 01:10 and 03:10 UTC under EST). A missed run is caught up by the next one.
- **Fail-closed (exit code 2):** a torn, edited or out-of-chain ledger line; a config change; a held or pending symbol with no completed bar; a stale or missing census at a freeze; any Binance or egress error.
- **No manual ledger edits,** except the documented truncation of a torn last line.
