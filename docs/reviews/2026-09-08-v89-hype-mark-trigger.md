# HYPE August 26: sampled marks and actual historical execution

The actual HYPE long in the August 26 entry minute closed at maximum hold with
**+$52.769613 after recorded fees and funding**. All ten entry and exit fills
match public trade records. This is an older V61 lifecycle with 60.36 HYPE and
different sizing and exit settings; it is not a recovered V89 result.

Neither available mark source establishes continuous trigger history. The
modeled adverse V89 stop loss remains an unresolved counterfactual. No current
strategy PnL is revised and no live change is proposed.

Confidence is high in the source-qualified arithmetic and sampled observations.
Confidence is low in transferring the old outcome to the current strategy or
inferring profitability from one trade. Different source bytes, inconsistent
public fills, missing settlements, or failure to reproduce the report would
falsify the corresponding result.

## Actual lifecycle

Times are August 26, 2026 UTC. The first saved signal publication was
02:25:21.069494. Five venue entry fills occurred at 02:25:23.786, with total
quantity 60.36 and fill-weighted price 81.87890324718356527501656726. The account
position and acknowledgement retained entry basis 81.8789.

The requested 80-bps stop was 81.2238688. The acknowledgement was accepted and
resting; 1,899 account reconciliations show the same reduce-only sell Stop Market
order, size 60.36, trigger 81.224. Its order ID is 526893353287. All 1,899 nonzero
position observations retain 60.36 HYPE, entry basis 81.8789 and isolated 10x
leverage. These are observations, not continuous venue-state coverage.

The maximum-hold close intent occurred at 10:25:18.223447. Five exit fills
occurred at 10:25:19.857, all at 82.83. The backend verified flat at
10:25:21.471000. Entry order 526893306250 and close order 527205198616 are distinct
from the protective stop.

| Recorded economics | USD |
|---|---:|
| Entry fill notional | 4,942.21060 |
| Exit fill notional | 4,999.6188 |
| Venue reported gross closed PnL | +57.408396 |
| Entry and exit fees | −4.294864 |
| Eight hourly funding settlements | −0.343919 |
| Net using reported gross PnL | **+52.769613** |

The direct difference between fill notionals is 57.40820. The **0.000196**
difference from reported gross PnL reconciles exactly to the retained rounded
entry basis. Both quantities remain explicit. Fee events duplicate the fill fee
fields and are checked rather than charged twice. Funding covers the eight
03:00–10:00 settlements. Public prints independently verify fill ID, time,
direction, size and price; fees, funding and account state rely on the captured
primary ledger.

## Sampled mark evidence

| Source and window | Observations | Minimum mark | Maximum observation gap |
|---|---:|---:|---:|
| 0xArchive, 02:25–10:26 | 476 | 81.306 at 09:24:30.660 | 62.600 seconds |
| 0xArchive, 09:22–09:24 | 2 | 81.402 at 09:23:29.868 | 60.585 seconds |
| Native open-position valuation, 02:25–10:26 selection | 1,899 | 81.293 at local receipt 09:24:49.838080 | 21.232390 seconds |

The full vendor series has median spacing 60.610 seconds; the native series has
median spacing 15.070614 seconds. Native marks use position value divided by
absolute nonzero size. Flat-position market references are excluded. No missing
mark values occur in these captured series.

The report retains 30 thresholds: actual requested and observed wire stops,
both original modeled cases, and both quantities' six fixed publication-offset
quotes, with unrounded and inferred wire values kept separately. None has an
observed mark touch. Every non-touch remains `unresolved_between_samples`;
`continuous_trigger_coverage=false` and `revised_v89_pnl=null`.

Archived rounding code matches the current pure normalization function and its
constants. Historical size-decimal metadata was not recovered. The four size
precision cases consistent with the observed 81.224 wire all produce the same
wire price for each retained hypothetical threshold. That is an explicitly
labeled inference, not a claim to possess old venue metadata. Local receipt and
venue clocks are uncalibrated; their differences are not measured latency.

## Contract boundary

The pre-start backup verifies V61 HYPE maximum notional $5,000 and margin
fraction 0.10. The current V89 comparison has maximum notional $2,500 and margin
fraction 0.08, plus a long-only execution override. The old persisted execution
plan ignores provider recipe exits; current V89 honors them. Both contain an
80-bps stop and an eight-hour soft maximum hold with a 24-hour hard maximum.
The modeled quantities in the preceding study are approximately 30.53 HYPE.

The historical cohort fingerprint starts `3ca27a84`; its asset-specific ledger
fingerprint starts `4834882e`. Their scopes differ and are retained separately.
The current comparison fingerprint starts `39e334fc`. These identities must not
be pooled as one compatible live-performance sample.

## Verification and disposition

Source revision: `f3314c4a3f44f1fbd4bcf9372b813974c18f515f`, in the isolated
`hypervector-v89-storage-spcx-20260908` research worktree. Production execution
source and running processes are unchanged by this study.

The primary HYPE selection contains 7,692 raw events including session start.
Its registered 702,225,309-byte imported prefix hashes to
`d605ae1f7d5df7ee596855f9470fa6ce00a90518dd96b1a9749bbbce87fe03bb`;
every selected payload and event type matches DuckDB. Raw price/trade pages,
normalized files, request IDs and historical backup contents are checked.

**81 offline tests pass**. The new pure mark/economics module covers 97/97
statements and 40/40 branches. Separate source tests reject altered checksums,
price semantics, windows, cursors, request IDs and normalization. An independent
Decimal calculation verifies economics and native mark statistics. All 5,060
tracked archive members match their committed Git blob identities, and isolated
archive replay reproduces the final report exactly. Ruff, formatting, function
and file limits, public docstrings and annotations pass.

Evidence resides in
`data/logs/research/bidirectional_cohort/v89_hype_aug26_mark_trigger_20260908_v1/`.
The immutable journal pins the final report, captured primary ledger, raw source
bundles, archived implementation and verification results.

| Option | Evidence and trade-off | Disposition |
|---|---|---|
| Leave the earlier stop assumption unqualified | Retains known mark-versus-candle ambiguity | Superseded by this qualification |
| Substitute the old actual profit into V89 | Changes size and contract; misleading comparison | Reject |
| Revise the hypothetical lifecycle from these mark samples | Leaves unobserved trigger intervals | Defer pending continuous trigger evidence |
| Attribute the later-period losses by lifecycle exit type | Uses existing qualified history to locate the next material question | Next research task |

Next investigation: `v89_hype_later_period_exit_attribution_v1`. Partition the
existing HYPE modeled lifecycles over the already declared first-28/later-20-day
split by protective stop, provider exit and maximum hold. Reconcile exact source,
cost and direction before interpreting results; retain this trade's trigger
ambiguity. Inventory the journal first, fit no new thresholds, and do not open
the sealed prospective experiment. The aim is to determine whether later losses
are dominated by a recurring exit mechanism or by cost/source assumptions.

No deployment approval is requested by this study. It supplies an observation
and a defined next experiment, not a live-change recommendation.
