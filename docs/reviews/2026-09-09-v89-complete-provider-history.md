# Complete historical provider inputs and initial account boundary

The original core comparison is now independently verified across its complete
48-day scope. All eight streams contain 69,120 minute checks each, totaling
552,960 checks in 384 daily chunks with zero comparison differences. The six XYZ
streams contain 27,648 quarter checks and 6,912 archived hourly checks in 288
daily chunks, also with zero differences. Confidence is high in these bounded
source and comparison results; financial impact remains unmeasured.

The final aggregate reports agree exactly with their manifests, per-stream reports
and daily summaries. All declared original inputs and the frozen implementation
files reauthenticate. The core source remains `04ec3a0`; XYZ remains `fc7383f`.
The completed jobs were not restarted. The independent check consumes saved
comparison rows rather than relying on worker completion messages.

The authenticated reader from `f2808cc` consumes all four combinations of
first/latest core inputs and full-prefix/rolling-14-day XYZ inputs across the
entire July 21–September 7 interval. Each combination contains 69,120 complete
minute sets, 290,304 scheduled provider records and 295 emitted entry intents.
All complete evaluation/readiness and intent fields survive exact typed round
trips. Native routing cycles and account outcomes were not evaluated by this
reader check. Earlier hypothetical-position routing experiments remain separate.

| Asset | Emitted entry intents per complete source combination |
|---|---:|
| BTC | 3 |
| ETH | 4 |
| SOL | 5 |
| HYPE | 6 |
| xyz:SPCX | 58 |
| xyz:SNDK | 89 |
| xyz:BRENTOIL | 130 |

The four core assets therefore supply 18 intents and the three XYZ assets 277.
These counts precede position occupancy, sizing and account constraints; they
are not executed or independently profitable trades. Counts agree across all
four combinations while full payload hashes differ, so complete payload equality
between source variants is not claimed.

A separate raw-JSON check ties every compared value back to its provider payload,
including absent/current publication presence and emitted intent identity fields.
It verifies 416,894 core evaluations and 36 core intents across both source
variants, plus 27,648 XYZ evaluations and 554 XYZ intents across both XYZ history
variants. There are zero discrepancies. Four deliberately altered publication,
price, duplicate-evaluation and ineligible-intent records are rejected. The older
core control comparison covers 18 fields; original historical full readiness
payloads do not exist in those controls.

The account requires its initial July 21 00:00 UTC publication, which the original
comparison's open-start interval excludes. A separate native probe recovers all
14 starting provider publications and eight independent-identity core canonical
publications. None emits an entry intent. SPCX retains its configured close flag;
this is not an account close or a forced terminal action. Core canonical states
are RANGE for BTC/ETH/SOL and TREND_UP for HYPE at this one historical boundary.

The initial core windows retain their missing warmup minutes: BTC 5, ETH 5,
SOL 6 and HYPE 5. Each XYZ starting window contains only 192 native quarters and
retains 1,152 missing nominal warmup quarters. XYZ one-minute canonical evidence
remains unavailable. No missing candle or receipt time is manufactured.

An independent source-selection path reads the raw Parquet through DuckDB and
repeats the initial native collectors from the older `fc7383f` archive. All 14
provider payloads and eight core canonical payloads agree exactly. Native live
and regime source files are unchanged between that archive and `f2808cc`.
Classifier arithmetic shares the native implementation across these checks.
This qualifies the starting publications, not whole-history canonical evidence.

The final integrity pass reauthenticates 5,595 unique consumed references across
the comparison snapshot, final manifests and initial publications. The five new
probes pass Ruff; all six scripts pass the recorded length/annotation checks. The
unchanged earlier snapshot helper retains one E701 style failure, preserved with
its already registered bytes. No production code,
strategy, deployment configuration or live process was changed. Both prospective
outcome seals remain intact. Process reads confirm the two existing source-capture
PIDs remain present; this does not establish current live execution or account state.

Continue the [complete account plan](../plans/2026-09-09-v89-gap-market-account-followup.md).
The next implementation must separate the original gap-bearing provider inputs
from conditional execution-price calendars. Existing provider/calendar adapters
require complete native grids; the missing intervals must become explicit input
states while preserving every original source/cost/clock/allocation case. Carry
the initial publications into the start-inclusive account interval, retain the
end boundary's completion evidence, and preserve open terminal positions.
Whole-history canonical availability and HYPE UNKNOWN soft-deadline handling
remain unresolved requirements of that account qualification.

Changed source identities, incomplete calendars, raw/typed disagreement, altered
publication/intent relationships or failed boundary reproduction would falsify
the relevant findings. Historical or future profitability is not established.

Evidence: [journal revision 1](../research-journal/v89-complete-provider-history-20260909-v1.json).
