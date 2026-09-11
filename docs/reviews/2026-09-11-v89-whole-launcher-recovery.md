# V89 full-backend recovery and first accounting publication

Research-only experiment on September 11, 2026 UTC. The third isolated replay
completed at **17:56:34 UTC**; its full accounting verification passed.

## Question and scope

Can funding candidate `0c2b81933f4df480e0e8bb6b5289b8ea47504761` reconstruct
the exact stopped seven-asset cohort, satisfy the real supervisor's 900-second
fresh-identity deadline, and publish the first complete funding accounting
without changing original files or requesting orders?

High confidence applies to directly verified bytes, observed process outcomes,
and the bounded replay assertions. A changed input identity, unexpected adapter
call, missing or duplicated financial record, or failure before complete
publication would falsify acceptance. One local replay cannot establish a
worst-case startup bound, fresh live eligibility, or profitability.

The original profile and per-asset fingerprints are preserved. Eight complete
ledgers are distinct-inode APFS clones, including the 4,336,519,850-byte cohort
ledger with 603,313 rows and 104 prior run IDs. Relative runtime paths resolve
inside each separate replay directory. Real backup creation and verification,
runtime locking, engine construction, history reconstruction, collector
construction/activation, runner startup, and readiness validation are exercised.

The candidate remains uninstalled. The installed source, profile, TUI binary,
original ledgers and original runtime are not mutated by the experiment.

## Two preserved failed attempts

| Attempt | Fresh identity | Worker outcome | Finding |
|---|---|---|---|
| V1 | No; child exited after 618.110 s | Exit 1 | The strict mock rejected the existing flat BTC `configure_isolated_leverage(20)` call |
| V2 | Yes, after 682.110 s | Exit 1 after 683.118 s | The scripted poll omitted the required seven market-bar symbol keys |
| V3 | Yes, after 678.716 s | Exit 0 after 694.902 s | Two complete accounting cycles; final bounded stop |

V1 falsifies the assumption that full startup is read-only. The existing flat
startup path reasserts configured isolated leverage through the exchange adapter.
The open-position adoption path returns before that setting operation. V2/V3
therefore permit simulated acknowledgements for BTC 20x, ETH/SOL 15x, and
HYPE/SPCX/Brent 10x. An SNDK setting write, wrong leverage, order submission,
cancellation, position close, or protection mutation remains forbidden. These
are simulated setting writes; they must not be described as zero requested
financial operations. No real venue client or financial request is constructed.

V2 appended the known +$0.004137 SNDK funding credit during reconciliation, then
failed before any complete cohort snapshot, heartbeat or committed funding
window. Passing the fresh-identity check was insufficient for whole-cycle
acceptance. The failure belongs to the incomplete scripted poll, not a proven
production market-data defect. The real market-map validator reproduces the V2
failure and accepts V3's exact seven keys mapped to empty tuples. No candles or
signals are fabricated. Strategy calculation and market-driven exits are outside
this fixture's acceptance scope.

Both failed attempts retain their original operators, logs, plans, backups,
complete appended suffixes and terminal supervisor results. Closing verification
authenticated all eight original files and each clone prefix. No new fill or
charged-fill-fee row was appended. Startup `fee` rows with
`source=venue_fee_schedule` are metadata, not duplicate cash charges. V2 permits
the six setting acknowledgements, but its failed worker did not emit final
mock-call counts; those counts are not claimed as independently verified there.

## Timing and accounting acceptance

The supervisor's initial inventory took **23.962 s**, separately from its
**678.716 s** fresh-identity wait. The worker completed two cycles and exited
zero after **694.902 s**. The 900-second readiness deadline had **221.284 s**
remaining at acceptance. These are measured local results, not a restart SLA.

| Non-overlapping worker stage | Seconds |
|---|---:|
| Prestart backup, including two internal verifications | 143.878 |
| Engine construction | 153.963 |
| Cohort telemetry/history reconstruction | 222.306 |
| Runner construction, including durable funding cursor scan | 79.082 |
| Guarded start, two cycles and bounded completion | 92.079 |

Post-run verification authenticated all eight originals and clone prefixes,
checked contiguous appended sequences, and found exactly one added funding row:
**+$0.004137 at venue timestamp 1789142400047**. No fill, charged-fill-fee or
order row was appended. Both committed funding windows, both snapshots and both
heartbeats were present; no runtime fault or degraded poll was published.
The first window began at 1789059000000 and committed through 1789145400000;
the second began at that committed boundary and did not duplicate the credit.

Both snapshots retained seven assets and the exact SNDK short, entry OID
`542326864971`, stop OID `542326955281`, original entry clock and complete
execution plan. All seven final clone states are `STOPPED / bounded_run_complete`
with no fault. The worker's complete call records verify exactly six simulated
setting acknowledgements, none for open SNDK, and no requested orders.

The SNDK snapshot's **compatible-profile-history** accounting equals the
independently loaded retained history plus that one credit: fees $0.301042,
funding -$0.012585, realized PnL -$21.484460 and eight retained fills. These are
history-scoped fields, not the open lifecycle's isolated funding or this
replay's trading result. No trade was executed during the replay.

The initial supervisor ledger inventory is measured separately and precedes the
900-second wait. The wait itself uses the production timeout unchanged. An
observation timeout does not restart or terminate the worker; its original
process handle is followed to an actual terminal result.

The accounting clock is fixed at 16:50 UTC, using authenticated native position,
stop, fill and funding evidence captured before that time. Both same-day replay
windows include the known funding credit. The separately frozen
[restart-accounting experiment](2026-09-11-v89-restart-accounting.md) proves the
longer-downtime cursor distinction; this full-size experiment adds startup and
publication evidence rather than inventing future native payments.

## Independent native preflight

The actual Info-only seven-asset preflight is timestamped **17:34:32 UTC**. It
constructed no execution client, required no signing key and reported the same
active/candidate profile fingerprint. All seven assets reconciled to the stopped
ledgers, had resolved fees and technically valid sizing, and had complete visible
buy/sell depth for the declared planned quantities at their sequential reads.
Its sizing-reference equity was **$4,807.25695649**, from the actual account.
These observations are not simultaneous or guarantees of later execution depth.

SNDK remained **-0.306 at 1629.2, 10x isolated**, with exact full-size reduce-only
Stop Market OID `542326955281` at **1669.9**. Preflight marked protection complete
and reported **-$0.8568 unrealized** at that read. The flat-profile-transition
predicate is false solely because this protected lifecycle and order are open.
That predicate neither disproves same-profile recovery nor authorizes closing it.

All seven actual reads report `unifiedAccount`. The replay uses raw perp account
fixtures and synthetic book, precision and fee metadata; it does not model the
actual unified spot collateral. Its balance fields must not be presented as
current account equity. Independent native preflight qualifies those actual
inputs separately and does not replace the frozen simulation inputs mid-run.

## Current boundary and decision

At **17:51:05 UTC**, a further seven unsigned native reads confirmed the same
SNDK size, isolated leverage and exact open full-size stop. Unrealized PnL was
**-$2.9988** at that capture. At **17:53:10 UTC**, the original five trading/TUI
processes remained absent, all seven original terminal records were unchanged,
and the profile/TUI/cohort/SNDK hashes matched. The three read-only observers
retained their original process births; no prospective outcomes were inspected.
Strategy-managed exits and new entries remain stopped. The stop origin/intent
remains unproven. No runtime process was signaled or restarted.

Recommendation: retain the existing funding candidate as a source-only
installation proposal, incorporating this measured recovery evidence. The
reason is exact accounting across downtime, independent of market regime. No
return, hit-rate, larger-win or profit forecast is established.

| Alternative | Benefit | Trade-off |
|---|---|---|
| Leave installed source unchanged | No deployment action | The separately reproduced longer-downtime funding omission remains |
| Extend the fixed lookback | Smaller source change | Another finite boundary and incomplete pagination remain |
| Durable cursor plus pagination | Covers the validated recovery cases | Adds history scanning and potentially more unsigned requests |

Success requires exact profile/ownership continuity, complete funding retrieval,
unique financial rows, timely fresh startup and correct first accounting
publication. Unexpected source changes, duplicate/missing funding, incorrect
cursor commits, changed venue ownership, or startup regression invalidate the
corresponding acceptance and require investigation. The prior source and exact
candidate are preserved, and isolated reverse/forward rollback was verified in
the linked funding study.

The existing installation request remains pending under the mandate's Human
control clause. Its scope is source-only candidate `0c2b819`; it grants no
automatic restart or order action. The candle-session candidate `f59d54c` and
stop-intent clarification remain separate. Both candidates touch the launcher;
if both are approved, compose and validate them before installation.

Next investigation: the separate checkpoint and TUI projection of a recovered
run, including retained accounting history and explicit stopped/stale status.
An initial direct checkpoint-publication trial exited 1: both fixed-clock cycles
gave every asset the same book-receive timestamp, 1789145400000. The actual causal
book validator rejects that duplication for all seven assets. No checkpoint was
published. This is an identified simulation chronology limitation, not evidence
that the production clock duplicates those observations. Its original operator,
failure log and follow-up diagnosis remain under
`v89_recovery_checkpoint_20260911_v1`; the first diagnostic's wrong event-name
selector is explicitly corrected by the retained `chronology_diagnosis.json`.
Continue with a coherent advancing simulation clock and synthetic book clock;
do not weaken the validator, retimestamp the preserved V3 output, or claim TUI
acceptance from the successful backend accounting replay.
Full strategy-candle recovery, fresh real-client behavior and actual live
post-start acceptance remain separate requirements. Original Terminal visual
acceptance remains unverified after Computer Use rejected access; isolated
rendering is not acceptance of that original window. Prospective outcome seals
remain closed, and this experiment introduces no performance rejection gate.
