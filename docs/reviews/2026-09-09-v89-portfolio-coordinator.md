# Chronological portfolio coordinator: archived synthetic qualification

Source `bc8e1ab4f22ed04c57e09efa6bcf72fa0c455221` connects the incremental
account, accepted exposure, original route costs, pending exits, native source
phases and both registered intrabar clocks. The broader allocation suite passes
973 tests in the isolated worktree and again from the complete source archive.
The 72,404-byte synthetic report reproduces byte for byte from archived code.

Confidence is high for the tested synthetic accounting and phase contracts.
Source-backed metadata/provider integration, full regime/provider parity, all
24 prospective cells and future profitability remain unqualified. No prospective
signals, positions, trades, cash flows or returns were read or reconstructed.
The work remains in the research worktree; no live source, profile, process,
TUI, order or execution authority changed.

## Account and source ownership

Account preview and commit share the same transition implementation. Repeated
previews do not consume opportunities, settle funding twice or finalize the
account. The timestamp planner settles funding, closes existing positions, sizes
ordered incoming opportunities and then applies new-entry immediate exits. An
immediate stop cannot retrospectively admit an already rejected competitor.
Funding-only events refresh surviving accepted quantities and cumulative funding.

The coordinator owns immutable published positions, pending decisions, deferred
opening stops, proposed entry identities and retained source-bar progress. It
builds the account and route-book changes before committing either. An external
account step invalidates its ownership. Failed planning or account commitment
preserves the previous account and book. Invalid entry geometry is retained as
a rejected proposal; invalid route identity, source contract, price or fee is an
explicit technical error. Accepted entry prices and fees must match the frozen
quote for the supplied opening, without applying entry freshness a second time
using the current risk bar's later knowledge clock.

Calendar assembly preserves core one-minute and XYZ fifteen-minute intervals,
native funding offsets, completed decisions and observed opening offsets. A new
opening takes mark precedence over the preceding close at a shared timestamp.
No missing source bar, rate, price or terminal exit is invented. The owner rejects
advancing past required undelivered risk/completion phases and requires the
declared universe's source coverage through its exclusive terminal boundary.

## Clock correction and pending exits

The initial prototype waited for delayed risk before processing a completed exit
decision. A synthetic 20-millisecond opening offset exposed that this changed
the completion clock too. The final implementation processes each phase at its
own registered time and retains overlapping bars by symbol and source-bar start.

The boundary controls place an old bar's risk before, exactly at, and after the
next opening. With offsets 0, 1 and 20 milliseconds, the artificial old position
closes by stop at 59,999, by stop at 60,000, and by an already completed ordinary
exit at 60,000 respectively. A later risk event from the old bar cannot attach
to the newly accepted position. These are conditional timing-model results,
not observations of achievable venue execution or a new strategy rule.

HYPE opening stops retain priority over pending ordinary exits. In the late
variant their original costed price, timestamp and competing pending evidence
remain owned until the scheduled close. A second opening gap cannot overwrite
that already selected deferred order. Earlier modeled exits still remove any
later pending/deferred actions belonging to the closed lifecycle.

Complete HYPE simulations preserve the 480-minute soft exit and 1,440-minute
hard exit using completed regime evidence. Six complete two-day terminal controls
cover both clocks and final opening offsets 0, 1 and 20 milliseconds. They leave
remaining exposure marked and retain pending decisions, including when the last
risk timestamp falls at or after the exclusive end. The frozen historical HYPE
model still has no liquidation trigger. Shared liquidation uses its existing
maintenance assumption and actual accepted rounded quantity, opening fee, margin
and signed cumulative funding; it is not a claim about current venue mark/tier
semantics.

## Independent evidence and reproduction

Twelve synthetic shared-portfolio cases cover all seven routes, three frozen
cost records, both exit clocks and two artificial notional caps. The 84 route
trade comparisons are repeated synthetic controls, not independent market
trades or the 24 prospective cells. Independent Decimal arithmetic checks
rounded exposure, side-aware prices, opening/closing fees, signed funding,
gross/net cash and exact exit identities/clocks. The largest absolute numerical
residual is `4.547473508864641e-13`; acceptance uses absolute tolerance `1e-10`
and zero relative tolerance. The harness rejects altered cash, prices, counts,
count types, exit clocks, duplicate symbols and nonfinite values.

The nine affected account/risk/coordinator modules have 842/842 statements and
268/268 branches covered by unit tests. The qualification driver's CLI I/O is
exercised by the actual worktree and archive runs and is outside that coverage
claim. All 23 changed/new Python files since the archived holding milestone
pass size, annotation, public-docstring and indentation checks. Ruff and
whitespace checks pass. All 5,334 Git blobs match their committed archive
identities; the nine critical imports resolve from the extracted archive.

Archive SHA256:
`2242b29f00ca85edf7417fe19bd5c24a7fb0be68b855aa5ab73d633d1f42fc6d`.
Report SHA256:
`b59e098d724f79182212e4e408d2d2cd5db8c9fcd5e17986a54a282d8dafe33f`.
The expanded reproduction copy was removed only after backup identity, tests,
post-test source hashes and exact report reproduction were verified.

At 05:54:25 UTC both public collectors were alive; all fifteen pinned collector
sources and the live profile hash were unchanged. All 2,412 prior evidence files,
totaling 927,213,350 bytes, matched their recorded identities. This is source
health and evidence integrity, not a venue account reconciliation.

## Remaining qualification and falsifiers

Next bind source-backed metadata and complete provider/regime output to the new
calendar and entry plans. Preserve provider decision/model time T, actual source
knowledge K and native settlement S separately. Reuse the qualified core daily
gap-fill correction before full historical provider probes; the worktree's older
extractor remains unsuitable for that purpose. Complete source/metadata semantics
and the full 24-cell evaluator remain false in the journal.

Any wrong generation, skipped event, changed phase clock, double funding/cost,
altered quantity, stale or forged pending evidence, early terminal close, changed
registered inputs or failed archived reproduction invalidates the affected
qualification. Both September 22 and September 23 outcome seals remain in force.

Evidence: the original repository's
`data/logs/research/bidirectional_cohort/v89_portfolio_coordinator_20260909_v1/`.
