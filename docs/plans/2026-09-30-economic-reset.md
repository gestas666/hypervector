# Economic reset implementation plan

**Goal:** Establish the recorded causes of losses and test a distinct return
mechanism without changing armed execution.

**Architecture:** A scripts-only report consumes a frozen checkpoint and local
hourly funding files. It validates accounting and coverage, separates historical
strategy identities, and measures funding revenue capacity with explicit capital
and cost assumptions. No signer, venue client, database writer or live policy.

**Tech stack:** Existing Python environment, pandas, pytest and local JSON/Parquet.

1. Add tests for net = gross - fees + funding, mismatched aggregates, finite
   values, complete calendar-month funding and missing-hour rejection.
2. Implement `scripts/strategy_economic_reset.py`; preserve full input hashes,
   reject output overwrite and label all outputs report-only.
3. Freeze the current checkpoint into a new research directory. Run the report
   on BTC/ETH native funding history already retained locally. Use every complete
   month; no parameter search. Assume hedge notional is 50% of total capital,
   and show 0/10/30 bps monthly cost allowances per hedge notional. These are
   sensitivity assumptions, not observed fees or complete strategy PnL.
4. Validate arithmetic and provenance and write the economic verdict. Compare
   against existing rejected research before claiming novelty.
5. Continue the candidate only into a paired spot/perp replay that accounts for
   basis, actual funding oracle marks, fees, liquidity, asynchronous fills and
   separate-leg margin. Historical funding alone cannot authorize a live carry
   implementation or establish its profitability.

Success is a reproducible economic diagnosis and an honest measured candidate
screen. Positive expectancy remains a hypothesis; neither a revision count nor
passing software tests establishes it. No new performance abort gates are added
to the live engine. Existing frozen approvals and strategy files stay intact.
