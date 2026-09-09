# Historical market inputs and canonical export startup

Source `c02c9c628c36a4071790c74702da9e4cb0c639ee` adds explicit historical
price/funding bindings and a complete native canonical export runner. Confidence
is high in the bounded checks below. Complete real-history market binding,
native account results and improved profitability remain unqualified.

The market adapters authenticate original Parquet sources and preserve original
row indices. Native provider candles remain distinct from the existing flat,
zero-volume previous-close continuity proxies. Funding retains observed signed
rates and the exact price basis used at each hourly settlement. No receipt time
or missing rate is invented. These adapters have not yet been applied to all
real historical price/funding streams.

All 39 focused tests pass in the worktree (2.89 seconds) and frozen archive
(3.17 seconds). They cover source tampering, missing/invalid prices and funding,
future-candle exclusion, missing current observations, UNKNOWN preservation and
failure before atomic daily publication. Ruff and file/function/type/docstring
checks pass. The archive reproduces all 5,482 tracked Git blobs, file kinds and
executable bits. The eight real initial canonical payloads exactly match the
previously registered native report.

The complete canonical export was observed running at **September 9, 2026,
18:24:42 UTC**: parent PID 26037 and four workers (26050 BTC, 26047 ETH, 26049 SOL,
26048 HYPE), all first-source streams with initial output. Zero daily chunks
were complete at this startup observation. Preserve exec session **32156**;
do not restart the job. It covers the original eight core source streams,
July 21 through September 7, with 552,960 minute checks plus separate initial
observations. This is canonical evidence generation, not account evaluation.

Evidence directory:
`data/logs/research/bidirectional_cohort/v89_historical_canonical_history_20260909_v1/`.
It contains `source_verified.json`, `archive_tests.log`, `startup_status.json`,
`source.tar.gz`, the extracted `source/`, `run.log` and `export/`.
Archive: 33,476,155 bytes,
SHA-256 `8e7a22d97a42e411682174bfe9b4393ca43f51e336d33dc4e3c56c9759f94b22`.
The source archive is frozen; the active log/export are incomplete running
artifacts and must not be mistaken for a finalized journal result.

Startup free disk was 7,505,145,856 bytes. Monitor output growth and collector
health; this observation does not identify a cause of trading losses or prove
a collector failure. Do not delete existing evidence to accommodate the job.

Continue the complete historical account plan: qualify the complete original
market streams, integrate native decision-time positions, required canonical
history and HYPE UNKNOWN soft-deadline behavior, then reproduce the full original
source/cost/clock/allocation matrix. Preserve conditional proxy labels and
terminal open positions. Changed source identities, failed archive reproduction,
missing daily output or unexplained account differences invalidate the affected
qualification. Do not repeat previously completed provider comparisons.

No live process, configuration, strategy, execution client or deployment was
changed. Neither prospective outcome seal was opened. Current live account
outcomes were not refreshed. The full research goal remains active.
