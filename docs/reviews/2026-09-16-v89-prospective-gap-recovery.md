# Forward source collectors resumed after a 49-hour interruption

Both research collectors had stopped at **September 13, 23:01:29.064 UTC**.
At discovery on **September 16, 00:15:32 UTC**, their original PIDs were absent,
writer locks had no owner, and saved health explicitly said `stopped`. Both
reported no error. The stop's origin is unknown; matching timestamps and the
graceful-stop code path do not identify who or what requested it.

**High confidence** applies to the observed stopped state, frozen source hashes,
raw/index timing reconciliation and exact resume preservation. The original
prospective studies now have incomplete timely source coverage. Backfill cannot
make the lost observations timely. No strategy outcome was opened or calculated.

## Preserved evidence and measured gap

Before resuming, both SQLite indexes were copied from read-only connections and
passed `quick_check`. Saved health bytes bracketed each backup unchanged. All
**26 collector/helper files and two protocols** matched their frozen manifests.
The original capture directories, raw files, manifests and study windows remain.

An independent timing-only reader authenticated **35,586 indexed raw requests**
and reconciled **44,936 first-observation identities** with the preserved indexes.
Independent SQL reproduced coverage counts and lateness. The requests include
two historical failures for the pair collector and eighteen for seven assets;
these failures remain explicit. Valid response clocks alone feed the timing audit.

At the discovery cutoff, each SNDK/Brent pair stream lacked **196 quarter candles
and 49 funding identities**. The seven-asset collector lacked **2,953 minute
candles per core asset**, **196 quarter candles per XYZ asset**, and **49 funding
identities per asset**. Before the interruption, seven-asset core timing already
contained eleven late candles: BTC two, ETH/SOL/HYPE three each. These older late
receipts are retained separately from the interruption.

## Resume and validation

The documented public-data resume command was used from each original worktree,
with a credential-free environment and unchanged source/manifest contracts.
No financial process, live configuration or strategy was controlled or changed.

| Collector | New PID / tool session | Initial verified heartbeat |
|---|---|---|
| SNDK/Brent pair | 43671 / 14590 | September 16 00:18:56.540 UTC |
| Seven assets | 45939 / 63338 | September 16 00:19:19.168 UTC |

Both processes owned their individual writer locks and reported `waiting`, no
error and `outcomes_evaluated=false`. This means waiting for the next scheduled
capture, not a stopped process. Their actual live handles were checked.

Read-only post-resume snapshots preserve every original **35,586 request row**
and **46,100 value-version first-observation rows**, including original receipt
times and value hashes. Latest-observation fields may legitimately advance.
Deliberately changing an original first receipt in a private memory copy was
rejected for each collector. No preserved live evidence was mutated by that test.

The post-resume raw/index comparison authenticated **35,641 requests**. The raw
archives contain exactly those indexed files, and every member hash verifies.
Their combined uncompressed content is **290,639,964 bytes**. Archives and both
before/after indexes are retained for reproduction without fresh market requests.

At the first post-resume snapshot, all expected core minutes were present, with
the recovered interval honestly counted late. Each XYZ stream still lacked five
older quarter candles, and each stream lacked one older funding settlement.
These are bounded-recovery work: the frozen scheduler fetches at most one older
day per stream per due cycle. The remaining quarter identities are September 14
23:00 through September 15 00:00; remaining funding is September 15 00:00.
Pair recovery runs each quarter; seven-asset funding recovery runs each hour.

Eight newly available core candles—two per core asset—were independently
verified after the first resumed receipt, all within the frozen sixty-second
allowance. Maximum measured receipt delay was **19,011 ms**. This is public
collector timing, not live order or strategy latency. The next normal quarter
and hourly funding receipts were retained as explicit follow-up checks.

At the actual **00:30 UTC** quarter, all five XYZ source streams across the two
collectors published timely observations. Raw response hashes and native time
fields verify delays of **6,149–9,604 ms**, inside the sixty-second allowance.
All older missing quarter candles were recovered; their first receipts remain
late. Pair funding coverage also recovered. The seven-asset collector still
has one old funding gap per asset, scheduled for recovery at **01:00 UTC**.
This observed normal cycle strengthens resume qualification; it does not repair
the original block's lost timeliness.

## Disposition, risks and next work

**Recommendation / why now:** retain the unchanged resumed collectors to prevent
further loss of prospective source evidence. Leaving them stopped would extend
the gap. Rewriting their frozen implementations or redefining study dates would
weaken comparability and would not recover timely observations already lost.

**Applicable regime / proposed live change:** this is a source-continuity issue
independent of market regime. No allocation, entry/exit, leverage, sizing, risk,
route, financial execution or deployment setting changed. Existing continuous
research authority covers public-source capture; no live approval is requested.

**Expected upside / limitations:** future observations can again be collected
and audited. This establishes no trading edge or profitability improvement.
Original first-observation validity cannot be restored by late acquisition.
Current throughput does not prove future uptime, uninterrupted final coverage,
or absence of contention with other clients sharing the same IP.

Both original financial seals remain unchanged: **September 22 04:00 UTC** for
the pair and **September 23 00:00 UTC** for seven assets. Their incomplete
timeliness must be reported at evaluation. The original pair protocol requires
a later predeclared block; the separate
[gap disposition](../plans/2026-09-16-v89-prospective-gap-disposition.md) fixes
September 23 04:00–October 7 04:00 UTC without moving either original window.
That later collector is preregistered work, not an already launched experiment.

**Failure / rollback triggers:** changed source or manifest, lost original
receipt, wrong writer ownership, stale/stopped/faulted health, missing scheduled
observations or a raw/index discrepancy reopens collection qualification.
Any corrective process stop must affect only the owned research collector,
retain its evidence and record the resulting gap. Do not restore an old SQLite
snapshot over newer observations. No financial backend restart is required.

**Next highest-value investigation:** verify the resumed coarse/funding cycles
and add passive collector-health observation, so a stopped collector is detected
before another multi-day gap. The existing financial lifecycle and diagnostic
watchers continue in their distinct scopes; neither covers these research jobs.

Evidence:
`data/logs/research/bidirectional_cohort/v89_prospective_gap_recovery_20260916_v1/`.
