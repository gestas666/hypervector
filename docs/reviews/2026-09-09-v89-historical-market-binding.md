# Complete historical price and funding bindings

The original 48-day account-price and funding inputs now bind across all fourteen
first/latest price cases for the seven assets. Confidence is high in source
membership and the reproduced arithmetic below. This qualifies inputs for the
native account replay; it does not establish account returns or better live performance.

| July 21–September 7, 2026, both price variants | Verified count |
|---|---:|
| Price rows | 580,608 |
| Retained candle rows | 580,456 |
| Explicit previous-close continuity rows | 152 |
| Hourly funding observations | 16,128 |
| Funding observations using retained candle prices | 16,128 |
| Unique consumed source/registration references reauthenticated | 28 |

The 152 continuity rows are the original 76 missing core minutes repeated under
first/latest variants: BTC 18, ETH 20, SOL 19 and HYPE 19 per variant. These are
conditional account prices, not recovered trades, quotes or provider candles.
XYZ prices retain complete native quarter-hour grids and remain the same physical
files across the two price cases. Their distinct provider-history variants remain
separate requirements for the account experiment.

The funding catalog preserves the original core funding directories rather than
silently switching to copies stored with revised candles. All observed rates,
including signed and explicit zero values, retain their original row indices.
No missing rates or local receipt times are invented.

The first full check found a new-reader format defect: pandas restores the XYZ
candle timestamp as a named index. The reader now exposes that retained timestamp
as a column before validating it. A regression reproduces the failure and confirms
the correction without changing any source file. The failed partial run and its
log remain preserved; only `worktree_v2` and `archive` are complete.

Source `c55c04b7b8f2b3641655c602551002ab4ccd5caa` passes 67 focused tests in
the worktree and archive. Unit tests cover 210/211 statements across the five
measured logic modules; the remaining registration-constructor statement runs
in every real-file case. The three market-binding modules and independent Arrow
verifier each have 100% statement coverage in the tests. Ruff, file/function
length, annotations and public docstrings pass.

Independent Arrow decoding checks every price/funding member and its economic
fields against the bound projections. Source and archive reports agree exactly
except the verification timestamp. All 5,489 archived Git blobs, file kinds and
executable bits match the source commit. Archive: 33,482,060 bytes, SHA-256
`4a64021e6122601de26014f842758ed72af7d4fac25594f36405d799944409d1`.
Evidence is under `data/logs/research/bidirectional_cohort/v89_historical_market_binding_20260909_v1/`.

At September 9 18:43:31 UTC the separate canonical export remains alive:
parent PID 26037 and four workers, exec session **32156**. Twelve complete daily
chunks contain 17,280 authenticated native observations; the full export is
unfinished. Preserve that job and its frozen source. Free disk at that checkpoint
is 7,211,024,384 bytes; monitor output growth and collector health.

Next connect the qualified market tables to native entry sizing, decision-time
positions and configured exits under the
[complete account plan](../plans/2026-09-09-v89-gap-market-account-followup.md).
Historical venue precision still needs an explicit evidence/assumption contract.
Whole-history canonical availability and the known difference between native
UNKNOWN handling and the older HYPE research support calculation remain required.
Do not manufacture canonical states from provider states or replace missing
receipt evidence with captured-source records. Preserve all original cases,
terminal positions and both prospective outcome seals.

Changed source identities, missing grid coverage, lost proxy labels, altered
settlement references, failed archive reproduction or unexplained account
differences invalidate the affected qualification. No live process, strategy,
configuration, execution client or deployment was changed. No account outcome
was refreshed. See the [immutable journal](../research-journal/v89-historical-market-binding-20260909-v1.json).
