# V89 Brent entry: causal signal, exposure and margin evidence

High confidence within the retained native window: the September 16 12:00 UTC
Brent short matches its completed hourly breakout rule, configured 10x isolated
leverage and protective stop. Endpoint cash movements reconcile. The evidence
does not establish profitable expectancy, the original ATR seed or the exact
opening mark. This review updates the earlier unresolved entry investigation.

The audit authenticated contiguous original cohort byte ranges, the asset
ledger and nine relevant source/configuration files from the backend's actual
September 15 18:30 pre-start backup. It reconstructed 600 completed one-minute
candles into ten hours, 02:00–12:00 UTC. Reselecting the retained older raw prefix
recovered the intervening candles without changing the earlier SPCX capture.

| Check | Native evidence and reconstruction |
| --- | --- |
| Fresh short | Previous close 102.40 was above the prior channel low. Entry close 101.89 fell below the preceding eight-hour low 101.94. The current bar is excluded from that channel. |
| ATR update | True range 0.59; `(19 × 0.6503147470717348 + 0.59) / 20 = 0.64729900971814806`. Recorded ATR differs by 4e−17. This checks one recurrence from recorded prior state. |
| Stop anchor | `101.89 + 2 × ATR = 103.1845980194362962`, matching the recorded anchor within 1e−10; venue trigger 103.18. |
| Availability | Last required candle published at 12:00:08.650148, before the asset decision at 08.651773 and dispatch at 08.652. Later cohort reporting is not used as the causal cutoff. |
| Fill | Order 546683502888: short 4.9 at 101.88, $499.212 notional against the configured $500 cap; fee $0.043131. Submission age 8,652 ms against the declared 30,000 ms deadline. |
| Protection | Order 546683530230: accepted resting stop, then 28 observations of a 4.9-unit reduce-only buy Stop Market at 103.18. All 28 nonflat position samples report 10x isolated leverage. Fill to observed stop acknowledgement was approximately 2.712 seconds. |
| Regime context | 1m TRANSITION, 5m TREND_DOWN, 15m TREND_DOWN; short alignment 5/6. This is a diagnostic score, not an 83% win probability or a standalone entry gate. |

Before entry, account value and withdrawable were $4,828.10005949. The first
captured account value equals that amount minus the $0.043131 fee and $0.049
unrealized loss. At the last captured position, 12:06:38.433224 UTC, unrealized
PnL was +$0.196 and the account endpoint again reconciles exactly. Withdrawable
fell by $50.029: $49.985869 of isolated collateral net of PnL plus the entry fee.
These endpoint identities do not show an unexplained debit.

The earlier $0.107800 difference arose when comparing collateral with an
unqualified fill-price margin model. Hyperliquid documents initial margin using
mark price and applies isolated unrealized PnL to position margin.
[Official margining documentation](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/margining).
An opening mark of 101.90 would reconcile the inferred initial-margin model,
but that mark was not independently captured at the fill. Book midpoint is not
evidence of the venue's margin mark. Full opening-margin qualification remains
incomplete.

Only 16 of 28 same-poll account/position pairs match the simple cash identity;
12 differ by −$0.147 to +$0.098. Separate valuation reads are a possible cause,
consistent with the retained reader implementation, but exact request clocks
are unavailable. The audit retains every difference and qualifies only the two
cash endpoints. It does not silently substitute a synchronized snapshot.

Validation: 38 tests pass, including controlled missing/duplicate/future candles,
wrong channel/ATR/direction, altered fees/leverage/size, contradictory stops,
absent coverage and future regime context. Eight initially failing boundary
tests exposed omissions in this new offline audit, which were corrected before
accepting its result; they are not demonstrated runtime trading defects.
Coverage is 220/225 statements and 25/26 branches. The untested lines are the
CLI entry path, which two actual sandboxed runs exercised successfully with
network access and `.env` reads denied. The two 17,881-byte outputs are identical,
SHA256 `b0b11d13d92da60f6d74303a0ca125513723308ad146c4d94ac3c7c22c0279a1`.
This demonstrates repeatability of one audit implementation, not independent
implementation agreement.

Recommendation: retain the current strategy settings on this evidence and
follow the open lifecycle through exit, costs and stop behavior. This removes
an unsupported entry-defect hypothesis; it does not predict a winning trade.
Changing leverage or entry rules from this one observation has no demonstrated
advantage. No live change or new approval is requested. Existing passive
observers and full source/account research runs remain separate investigations.

Falsifiers are mismatched source bytes, a noncausal input, different venue
size/leverage, absent protective coverage, an unexplained endpoint cash movement
or a final outcome inconsistent with native receipts. A new finding requires a
new journal revision; retain this audit and its prior failing cases. No financial
process or live parameter was changed by this work.

Evidence: `data/logs/research/bidirectional_cohort/v89_captured_provider_assembly_20260916_v1/brent_entry_signal_v1/`.
