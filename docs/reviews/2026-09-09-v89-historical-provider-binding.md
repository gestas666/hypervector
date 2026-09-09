# Historical publications bound to native admission

The complete historical publication binding is qualified as a research input.
It retains missing candles, complete native exit/readiness fields and explicit
modeled timing. It does not qualify the complete dynamic account or establish
profitability. Confidence is high in the reproduced binding results below;
economic impact remains unmeasured.

All fourteen unique streams cover July 21–September 7, 2026: four core assets
under first/latest inputs and three XYZ assets under full-prefix/rolling-14-day
inputs. The two disjoint source pairs cover 580,608 publications. Binding acts
independently on each publication; this is not a substitute for the four
cross-asset source combinations in the eventual account experiment.

| Per source pair, 48 days | Verified count |
|---|---:|
| Complete decision minutes | 69,120 |
| Provider publications | 290,304 |
| Provider evaluations | 222,271 |
| Entry intents before position/account constraints | 295 |
| Missing current core candles | 76 |
| Entry-expiry boundary probes | 295 |

The per-asset missing current counts remain BTC 18, ETH 20, SOL 19 and HYPE 19.
Declared missing warmup rows are retained. A missing current candle has no
fabricated provider evaluation. A current candle may still have no provider
evaluation when the strategy publishes less often. Neither case is inferred to
mean a flat market or absent quotes.

The binding uses the unchanged native freshness and canonical-preference helpers.
The 10-second historical knowledge delay is an explicit model assumption. It
does not establish actual local receipt time, latency or fill timing. Every entry
remains admitted at that assumed age. A separate probe one millisecond beyond
each configured deadline withholds the entry and preserves the original
publication, including configured exits. No historical receipt field is populated.

The full binding run from `ec94685` reproduces from its frozen archive; complete
report content agrees except the verification timestamp. Both payload hashes
match the earlier authenticated complete-history reader. Source verification
checks all 5,464 Git blobs, file kinds and executable bits against the commit,
and checks the extracted bytes. Tar group-write permissions are distinguished
from Git's tracked executable bit.

The starting-publication adapter is frozen as `28c1b34`. It reads the original
recovered report using its file hash and publication array index, retaining a
normalized copy of the original publication object. It does not manufacture a
comparison row or claim a historical comparison existed at the initial boundary.
The adapter reauthenticates each selected report member before binding it through
the same native admission path. Exact serialized comparisons reject numeric-type
substitutions that Python equality would otherwise accept.

All fourteen real initial publications bind at July 21 00:00 UTC, retaining eight
core canonical observations and zero entry intents. Core canonical states are
RANGE for BTC/ETH/SOL and TREND_UP for HYPE at this one boundary. XYZ retains 192
native quarters, 1,152 missing nominal warmup quarters, and unavailable native
one-minute canonical evidence. The initial binding report reproduces from its
frozen archive, whose 5,468 Git blobs and extracted bytes are verified.

The final source passes 338 offline tests in both worktree and archive, including
existing provider, historical-reader and native-account regressions. The three
historical modules cover all 252 statements. New source and tests pass Ruff,
file/function length, explicit parameter/return annotation and public-docstring
checks; implicit `self`/`cls` receivers are excluded from parameter annotations.
The final `28c1b34` archive also binds all 580,608 historical publications; its
complete report matches the preceding version except the verification timestamp.

Whole-history canonical evidence remains unsupplied in the complete-stream probe.
The binding distinguishes that state from a missing current candle, unsupported
XYZ source cadence and a real observed UNKNOWN state. UNKNOWN does not introduce
a standalone entry veto. HYPE UNKNOWN behavior at its soft holding deadline is a
separate, still-unqualified account requirement.

Continue the [complete account plan](../plans/2026-09-09-v89-gap-market-account-followup.md):
keep original provider publications separate from observed-market evidence and
explicit conditional price proxies; assemble all native decision-time positions,
configured exits, funding, costs, dynamic sizing and terminal open positions over
all original source/cost/clock/allocation cases. These binding results are a
prerequisite, not a narrowed replacement for that experiment.

Changed source identity, incomplete stream coverage, altered native payloads,
invented receipts, lost initial publications or failed archive reproduction would
invalidate the corresponding finding. No live strategy, configuration, process,
order client or deployment was changed. Neither prospective outcome seal was
opened; no current account outcome was refreshed.

Evidence: [journal revision 1](../research-journal/v89-historical-provider-binding-20260909-v1.json).
