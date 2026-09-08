# First completed V89 trade: SNDK protective stop

High confidence: the native venue records, frozen asset ledger, and closed-trade
checkpoint reconcile exactly for the SNDK long. This audit changes no live
strategy, order, process, sizing, leverage, or configuration.

| Item | Verified observation |
| --- | --- |
| Entry | 0.276 SNDK at 1803.4, 2026-09-08 01:00:14.162 UTC |
| Exit | Full 0.276 at 1788.2, 2026-09-08 05:08:57.911 UTC |
| Entry order / trade | 538806415304 / 996830541684107 |
| Stop order / exit trade | 538806460232 / 923869374782070 |
| Gross result | −4.195200 USDC |
| Entry plus exit fees | 0.085646 USDC |
| Four signed funding settlements | +0.000542 USDC |
| Net result | **−4.280304 USDC** |
| Holding time | 14,923,749 ms, about 4 hours 9 minutes |
| Native state after exit | No SNDK position or open order |

Seven individually timed unsigned Info requests captured both order statuses,
fills, funding, open orders, perp state, and the account fee schedule. No signing
client was constructed. Both statuses are filled; the original stop is identified
as reduce-only, Stop Market, and Triggered. The full position size matches.
After triggering, the native status reports `triggerPx=0.0` and `isTrigger=false`;
these fields do not mean that the resting stop originally had a zero trigger.

The frozen current-run asset ledger contains 9,517 consecutive records and
preserves an exact previously hashed 10,212,418-byte prefix. Its resting-stop
reconciliations retain the native 1788.6 trigger. There are 996 reconciliations
after stop acknowledgement and before the venue exit; each includes the original
stop order ID. The remaining stop-field checks are retained in the supplement.

The venue exit precedes the local fill record by 14,036.807 ms, within the
configured approximately 15-second polling cadence. This is observation delay,
not measured trigger-to-fill latency. The checkpoint's 992 ms acknowledgement
belongs to the original stop submission at 01:00:17 UTC, roughly four hours
before the exit, and should not be interpreted as a fresh exit acknowledgement.

Validation matched both fill prices, quantities, fees, sides, directions, venue
times, order IDs, trade IDs, transaction hashes, and taker flags. Each of the
four funding amounts, signed sizes, rates, times, and identities matched the
ledger. Decimal arithmetic reproduced the checkpoint's net result. Fifteen
mutations of native identity, cost, direction, protection, funding coverage,
checkpoint PnL, and flat-state evidence were rejected.

The original audit artifact retained an unused import. A separate v2 source
removed that import, passed Ruff, and reproduced the same economics and fifteen
rejected controls. The original evidence remains available.

Limitations: sequential native requests are not atomic. This audit does not
independently establish the exact venue mark-price crossing or trigger-to-fill
latency. One completed losing trade does not establish a performance change or
justify reopening rejected strategy variants. No live change is recommended
from this sample. Changed evidence hashes, an unmatched fill, or discrepant
funding/position evidence would invalidate the corresponding conclusion.

Evidence under `data/logs/research/bidirectional_cohort/` in the live checkout:
`v89_sndk_exit_native_20260908_v1/`, `v89_sndk_exit_ledger_20260908_v1/`,
`v89_sndk_exit_checkpoint_20260908_v1/`, and
`v89_sndk_exit_acceptance_20260908_v2/`.
