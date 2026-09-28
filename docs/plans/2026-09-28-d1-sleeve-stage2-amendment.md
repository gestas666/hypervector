# D1 crypto breakout sleeve: Stage-2 pre-registration amendment (live, automated)

- **Date:** 2026-09-28.
- **Amends:** `docs/plans/2026-09-27-d1-shadow-prereg.md` (Stage 0, observe-only shadow).
- **Operator decisions (2026-09-27, in conversation):**
  - "forget about the btc spot, replace with other hi gain per strategy trades".
  - Choices recorded: **automated executor**, **1% ($48/R) risk per trade**, keep the hourly routes at rung 0.
- **Arming:** this document does not arm anything. Arming needs:
  - the operator-authored approval JSON pinning the hashes below and this file's sha256;
  - `--enabled --i-accept-live-risk`;
  - the operator's one-time setup: sub-account, API wallet, env file, transfer, canary.

## 1. What is being traded, and the honest label

The D1 Donchian 20/10 sleeve of the Stage-0 pre-registration trades live on a dedicated Hyperliquid
sub-account.

**This is a labelled mania option, not a proven edge.** From docs/reviews/2026-09-27-v94-review-and-swing-research.md §3–4:
- 2021 alone is 41% of the historical R.
- The 2024+ holdout t is 0.45–1.7.
- Excluding ZEC it is about 0%/yr, with a −56% drawdown.
- Winners run 10–50R. Most trades lose small.
- Plan for sleeve drawdowns of −50% or worse.

**Deviations from Stage 0 (all operator-chosen or engineering-required):**
- **Risk.** 1% of BOOK equity (master + sub) at the stop, instead of 0.5%. This is over-Kelly on the
  evidence and is accepted by the operator.
- **Timing.** Live now, without the 4–8 weeks of observe-only parity.
- **Execution.** Real orders on a sub-account, with a separate API wallet named `d1-sleeve` (never the engine's `hl-api`).
- **Stop anchoring.** The stop is attached to the entry (grouping `normalTpsl`) at 2×ATR(signal) from the
  pre-fill reference price, so the venue places it on a full fill. It differs from "from the fill" by at
  most the 50 bps entry slippage cap on a stop of 4% or more. On a partial fill the sleeve places the stop
  from the actual fill.
- **Real-book allocation.** Every fresh virtual entry at today's open is a candidate, allocated in shadow
  priority order against the REAL sub book:
  - caps: 10 slots, gross ≤ 1.5 × book, 5% collateral reserve;
  - scaled takes between 25% and 100%.
  The existing shadow book is NOT adopted, so the sleeve starts empty and ramps as virtual trades turn over
  (about 25 entries a month in 2026, median hold 16 days).
- **Exits.** Exits follow every shadow close (channel, intrabar stop, gap stop, liquidation gap) and the
  sleeve's own venue stop. There is no max hold.
- **Leverage.** L = min(3, floor(1/(MMR + 2.5 × stop))), with shorts ≤ 2. It is always isolated. A position
  whose liquidation price is at or inside the stop is closed as a technical response.
- **Cadence.** Hourly idempotent runs at :15, with a 6 h entry window after 00:00 UTC. Entries and exits run
  only in minutes :05–:45, the sweep runs until :56, and nothing runs in :57–:03 except the protective stop
  exception of note 11.
- **No kill, drawdown or P&L rule** (SRS_HV1_NO_GATES). Only technical failure halts entries, for one run.

## 2. Protection design

1. **Venue-attached stop on every entry.** This is the normalTpsl child.
2. **Protect every position.** Every sweep puts a reduce-only stop on every position visible in the
   dedicated sub-account:
   - owned positions get the rule stop;
   - unattributed positions get the rule distance from the latest shadow ATR (or a conservative fallback),
     always on the protective side and never beyond liquidation. They are critical `unknown_position`, and
     the sleeve never trades them down.
3. **Proof-of-fills floor.** Acks, venue children and any read of the run size the stop, so a lagging read
   cannot shrink protection within a run.
4. **Loud failure.** Any position that some read in a run showed and that lacks full stop coverage makes
   the run critical, with a non-zero exit.

## 3. Known limits accepted for go-live, with operator procedures

- **Residual (i).** A fill that NO read in an entire run can see (a venue info node lagging the whole run)
  is protected by the first later run that sees it.
- **Residual (ii), silent.** A manual armed rerun within about a minute of a run, through a node lagging
  53–90 s, can shrink a doubled trade's stop.
  - **Procedure:** never start a manual armed run within 10 minutes of another run.
  - A node stalled across hourly runs can do the same on the scheduled cadence. This is rare, and later
    runs re-cover the position.
- **NB-SR1.** After a loud `exit_incomplete`, a later single lagging read can close the remainder's
  bookkeeping and cancel its stop.
  - **Procedure:** treat any `exit_incomplete` critical as an operator page. Inspect the sub in the app and
    run `flatten --coin` if needed.
- **NB-SR2.** A P7 cut short by the quiet window exits 0 with protection judged from local state.
  - **Procedure:** read the daily status. `stops_ok` must equal the position count.
- **Complexity.** The executor is about 6,200 lines with overlapping protective mechanisms. **The bytes are
  frozen.** Any change requires a new approval and a re-run of the full verification harness set (fuzz,
  probes, mutation drivers) preserved under `data/logs/research/d1_sleeve_verification_20260928/`.

## 4. Code and configuration pins (authoritative; supersede any hash in the appendices)

| File | sha256 |
|---|---|
| scripts/d1_sleeve_executor.py | `2fb94efd2b1af84fc4b5bcdf08d7dda2e3fcac0367b32b049d4400d241243516` |
| scripts/d1_sleeve_core.py | `cb76c74b11e51c6dad1cbac7d401521975062a962b7307ae00d4ac5fff533f8f` |
| scripts/d1_shadow_runner.py | `3496738ee6e98c8dd54ecb75f933b17aae80c36466b7eef3ca48ed713fba4471` |
| scripts/local.hypervector.sleeve.d1_executor.plist.example | `55c6f9d5ab5a1938a9f4c2f194c07d8dc1aa6978a84fd47532fbe1c6171209b8` |
| tests/test_d1_sleeve_executor.py | `8afd7cff6722c0ebd81401e9e60b966a624d6a25f04421a86fac94e70af085b0` |
| tests/test_d1_sleeve_core.py | `660962b6b3bc81c0a4cbd6d290122eab7dd083d509b5bb923518b7209b1443c6` |

- SleeveConfig fingerprint `63ff377d8e4b87df`.
- Shadow config fingerprint `c9ea5f06dd1658e4`.

## 5. Verification record (2026-09-27/28)

- **Process:** design (two competing designs plus a judge), build, then three-lens adversarial review
  (live-safety, correctness, venue-mechanics) over four passes and eleven rounds. The last round was
  independent, with no fixes: **0 blocking; all three reviewers approve**.
- **Tests:** the final suite has 420 tests (sleeve plus shadow). Line coverage is 89% for the executor and
  95% for core.
- **Mutation:** over 100 targeted mutants, all killed.
- **Fuzz:** tens of thousands of fuzz seeds across lag, stall, reversal, dust and suspend harnesses.
  - 0 runs ended with a position that some read showed but that lacked a stop, exit 0.
  - 0 quiet-window, vault, secret or crash violations.
- **Wire format:** the normalTpsl, trigger, updateLeverage and cancel wire payloads were verified against
  hyperliquid-python-sdk 0.24.0 (the same bytes as the live venv).
- **Not yet proven live:** these are the canary's job.
  - orderStatus by cloid on a filled IOC;
  - venue acceptance of an oversized reduce-only trigger;
  - child behaviour on a margin-cancelled partial.

## Appendices: implementation notes (chronological; later deltas supersede earlier ones)

### Appendix A. Base behaviour notes (hardening pass)

The Stage-2 pre-registration amendment must record these behaviours:

1. **Sizing.** Risk is 1% of BOOK equity at the stop, not the pre-registered 0.5%.
   - Book equity is master equity plus sub equity, read once per run; after exits it is the master value plus a refreshed sub value.
   - want = risk / stop_fraction.
   - max_order_to_book 0.5 is a technical sanity bound (sizing_sanity), not a size cap.

2. **Stop from the Hyperliquid fill.**
   - stop = venue entryPx (the average after partial fills) − d × 2 × ATR(signal) × unit, normalised. unit is 1000 for kPEPE-style coins. The shadow's Binance stop is not used.
   - Isolated leverage L = min(3, floor(1 / (MMR + 2.5 × stop_fraction))), with MMR from the venue maxLeverage. Shorts are capped at 2.
   - A position that is not isolated, or whose liquidation price is at or inside the stop, is closed as a technical response.

3. **Real-book allocation.** Every fresh virtual entry at today's open is a candidate, whether the shadow marked it taken or not. Candidates are allocated in shadow priority_rank order against the REAL sub book:
   - 10 slots and gross ≤ 1.5 × book, both counted over every sub position, unowned ones included;
   - sub collateral with a 5% reserve;
   - scaled takes between 25% and 100% of want.
   The existing shadow book is not adopted. Virtual trades open at go-live count as lost slot races. There are no late entries and no substitution. Results are compared with the shadow in R by trade_id, never in dollars.

4. **Priority inversion on retryable skips.** A higher-ranked candidate can hit a retryable skip: leverage_failed, sub_collateral, no_mid, coin_not_flat, stop_file, or a halted entry phase. A lower-ranked candidate may then take the last slot in the same run, and the higher-ranked one becomes a terminal slots_full at its next attempt. The slot race is decided in rank order only among candidates that can be entered at that moment.

5. **6 h entry window.**
   - Entries are allowed from 00:00 UTC of day T until T + 6 h; window_expired is terminal.
   - At most 3 attempts per trade (attempts_exhausted is terminal) and at most 2 IOC sends per run.
   - Entries cost 50 bps of slippage. Partial remainders are sent only if worth at least $11. There are no top-ups.

6. **Hourly runs.** launchd runs the executor at :15. Runs are idempotent. Exits and entries happen only in minutes :05–:45; the sweep and final check run until :56. A deferred or quiet-window run exits 0 unless a critical problem was raised.

7. **Exits follow every shadow close and the venue stops.**
   - A shadow close for any reason (channel_exit; stop_intrabar, recorded as shadow_stop; gap_stop; liquidation_gap) closes the real position with a reduce-only ladder at 100, 200 and 400 bps. Exits never expire; late_exit_days is recorded.
   - The trade is also closed when its own Hyperliquid stop fires. The coin then stays blocked until the virtual trade exits, and a later re-entry uses a new trade_id.
   - A trade the ledger does not know is held, protected and raised as critical.
   - A venue stop that fires between the P1 snapshot and a P5 exit is journaled with the shadow reason and exit_px None. This affects reporting only.

8. **No kill, drawdown or P&L rule** (SRS_HV1_NO_GATES). Only technical failure aborts. entry_overfill, gross_drift and every other alert sell nothing.

9. **Entry halt semantics.** Any of the following halts NEW entries for the rest of that run only:
   - through the problem codes: technical_failure (any exception in a phase), unprotectable, unprotected_position, exit_incomplete, not_isolated, stop_behind_liquidation, unresolved_entry, fill_not_visible, clock_skew, entry_overfill;
   - directly: hl_budget_exhausted, ambiguous_entry (an ambiguous entry whose fill the reads do not show), fill_not_visible.
   Halted candidates are not journaled as skips; the next hourly run retries them inside the window. Exits and protection are never halted. This is a technical-failure abort, not a strategy gate. An entry_overfill first seen by a later run's P3 growth check (item 12) halts that one run's entries; it is raised once per new size, so it never halts run after run.

10. **Dust-close severity** (a conservative deviation from spec §11 P6.9). For a dust fill (|szi| × min(entry, stop) < $11), the executor first tries to close it (dust_fill). If the reduce-only close is rejected, the stop is still placed and a dust_open notice is raised. The rejected close also raises critical exit_incomplete: the run exits 2 and later candidates in that run wait one hour.

11. **Quiet-window exception for protective actions** (amends spec I4 and I11, "no Hyperliquid call in minutes 57–03").
    - Only one kind of action may go out after the phase deadline and inside minutes 57–03: a reduce-only market stop-trigger order protecting an owned position.
    - That means at most two attempts (the first and one retry), only for the position being protected when the deadline passed. Each attempt is one /exchange action of weight 1.
    - The gateway and the pacer enforce it, and place_stop is its only call site.
    - No reads, cancels, leverage updates or closes are exempt. A stop repair's place-then-cancel may therefore leave a duplicate reduce-only stop resting until the next run.
    - If the stop still cannot rest, the run raises critical stop_missing and exits 2.
    - Any abort that skips P7 raises stop_missing for owned positions the local book shows without a stop covering the whole position: quiet window, budget, technical, unexpected and refusal aborts.
    - The next run's P3 treats every opened trade without a stop as critical stop_missing and places those stops first, before exits and entries.

12. **Double-entry guard and lagging fills (H1).** Before any entry retry that follows an attempt with no acked fill (no_fill, never_landed or canceled), the executor re-reads the sub position after 1 s.
    - **Same-direction position.** That read is the proof that the attempt filled.
      - The fill is journaled for the attempt at once: outcome filled, venue_status position_reread, avg_px None, filled_sz equal to the position size read. So it is owned even if the run fails before its stop.
      - The position from that read is adopted and protected. No second position read is trusted over it, and a second IOC is never sent.
      - Reports take entry price and size from trade_opened, and fees from fills, never from that outcome.
    - **Lag notice.** An order_status_lag notice is raised. It is raised before the trade is opened, so it stands even if the open fails. After the stop, orderStatus is asked once more: a fill answer that adds an oid or status is journaled; an answer that the order did not fill is not.
    - **Opposite position.** Critical unknown_position. The coin is blocked for the run and never touched, with no retry and no stop. Other candidates still enter.
    - **A failed position read after a never_landed answer.** This covers two reads:
      - the re-read before a retry;
      - the first read after the entry loop, when the loop ended at its send limit or at the :45 deadline.
      Any exception counts, including budget exhaustion and the quiet window. The attempt is journaled position_unverified (venue_status reread_failed) and the error then propagates. The attempt then owns a same-direction position on its coin, and P7 or the next run's P3 adopts and protects it through crash recovery.
    - While such an attempt is not adopted, critical unresolved_entry is raised and that trade takes no entry.
    - **Settling a mark.** A later session's P1 read settles the mark as never_landed (venue_status position_flat) only if the coin is flat and the mark is at least 10 minutes old. The trade then retries normally. This writes to the local journal only.
    - **Ownership scope (accepted by design).** An unsettled position_unverified mark, like an unresolved (ambiguous) entry, adopts and protects ANY same-direction position on its coin, including one placed by hand on the sub. This is acceptable on a dedicated sub-account: an unknown same-side position with a stop is safer than a bare one.
    - **Overfill.** A venue size at least one lot above the sized entry raises critical entry_overfill and halts entries for that run. The stop covers the whole position, so that trade may carry more than 1R at the stop; nothing is traded down. It is checked in two ways:
      - (i) At open and at crash recovery, against that entry's sizing (fill_fraction > 1).
      - (ii) In every sweep (P3 and P7), after the stop is placed or repaired, for each opened trade. It is raised when the position is at least a lot above all of: the largest size any entry attempt of the trade was sized for, its opened size, and any size already raised. That alert is journaled as position_grew and is not raised again unless the position grows further.
      - Growth only up to the sized entry raises nothing (the read at open lagged the entry's own second fill); the stop is re-sized to cover it.
    - **Known limit.** This needs three faults together: a lost POST response, an orderStatus that lags (never_landed), and a position read that lags. The position read SUCCEEDS but shows the coin flat, and the attempt is treated as not filled.
      - (a) **The retry fills.** The position is doubled. entry_overfill is raised at open if the read at open shows both fills. Otherwise it is raised by the first later read that shows the grown size (P7 in the same run, or P3 of a later run), and the stop is re-sized then. Until that read the stop covers only the first fill: up to about 2R at risk, with the excess unprotected.
      - (b) **No retry fills.** If every read in that run also misses the first fill, the run can exit 0 with that position unowned and unprotected. The next run flags it critical unknown_position (coin_held_unowned for the trade) and never touches it. flatten refuses it as not owned, so it needs manual action in the Hyperliquid UI.
      - (c) **Pre-existing, low: a later candidate sized one position short.** After a lagging fill is adopted, a later candidate in the same run may be sized from a read that hides the adopted coin. Its slot count and gross are then one position short for that run. Collateral is still accounted (sub_free is reduced at open) and the adopted stop is kept. A resulting 11th slot is flagged critical (slots_gross_violation) at run end when P7's read shows it.

13. **Budget and failure handling (H4).** The per-run caps are unchanged: 900 info weight, 150 info calls, 120 exchange actions, 200 weight per minute.
    - **Hold-back.** In the hourly run, 80 weight, 12 calls and 20 actions are held back from P1–P6 for the final check (P7). The configured caps are never exceeded.
    - **Earlier cut-off.** Entries and exits stop while a budget is within its sweep reserve (120 weight, 20 calls, 30 actions) on top of that hold-back. They therefore stop with 200 weight, 32 calls or 50 actions left, which leaves room for an entry in flight to finish before the hard limit. Exits deferred this way run next hour.
    - flatten, canary, probe and status --venue have no P7 and keep the full caps.
    - **Budget exhaustion in P2–P6** raises critical hl_budget_exhausted and skips the remaining phases. P7 (re-read and stop repair) still runs on the held-back reserve.
    - **Budget exhaustion in P1** goes to the outer handler: no P7 runs, and stop_missing is flagged for owned positions without cover.
    - **Exceptions in P2–P6** are critical technical_failure and do not stop the later phases or P7. Only a refusal or the quiet window stops the process. A sleeve TechnicalError is recorded with its own redacted text. Any other exception is recorded by its type only, and stderr gets stack frames and the type only, never the message.

14. **Off-host alerting (H5).**
    - The webhook and dead-man values must each be one https:// URL with no whitespace, control characters or inline comment. Anything else is refused at env load (exit 3), and the refusal never shows the value.
    - The refusal hits every command that loads the env: run, flatten and canary (armed or dry, including the dry canary plan), probe, status --venue and approval-template. Only offline status still works. A command started in the quiet window exits before the env is loaded.
    - Until the env file is fixed there are no exits, no stop repair and no flatten. Stops already resting on the venue stay.
    - For an armed refusal, the preflight alert reaches only the local banner and alerts.jsonl.
    - Delivery is otherwise best effort: it never fails a run and never logs a URL.

15. **Reconciliation (H6).** A coin reconciled as venue_flat_other (flat with no known close fill) is critical, keeps its stop that run, and takes no entry for the rest of that run (retryable coin_not_flat).

16. **Canary (H7).** The canary is a one-time supervised proof run of about $15 at 3× or less. It refuses before any order if half its size is under one lot, or if its stop at 0.9 × entry is under $11 (above the $10 venue minimum). If anything fails after its fill, it closes the position.

17. **Probe capacity (H8).** 0.6 × book of free sub collateral is a guideline and a hint, never a failure. The recommended $2,500 (about 0.52 × book) is below it on purpose: on a crowded day, entries fill slots until collateral runs short, then later entries scale down (to no less than 25%) or skip as sub_collateral and retry next hour.

18. **Sub-account and control.**
    - Trading is automated on a dedicated sub-account (vault = sub) with a separate d1-sleeve API wallet, never hl-api.
    - Unowned positions and orders are never touched; they count toward slots, gross and margin, and are critical.
    - STOP means reduce-only mode. flatten and launchctl bootout are the operator's off switches; flatten needs a valid env file (item 14).

19. **Risk flags (spec §22), to record as accepted.**
    - 1% is double the pre-registered risk and over-Kelly.
    - Correlated crypto perps behave as about one bet (N_EW 1.7), so 10 longs put about 10% of the book at the stop, on top of V95.
    - An isolated liquidation costs at least 2.5R.
    - The evidence is a labelled mania option (holdout t 0.45–1.7; about 0%/yr excluding ZEC; −56% drawdown).
    - Going live now skips 4–8 weeks of observe-only parity.

20. **Code pin.** The approval must pin the new sha256 values of both sleeve scripts:
    - core dfdf6e9b00e507d964af4c98d87d29e848e111d76ce80d5237bc1e0e44f7f455;
    - executor 7a3d89b02ddead4d78ef81c1e2bda2fa4da8d29c69712b3c297f59d778007221.
    The shadow runner sha (3496738e…) and the config fingerprint (63ff377d8e4b87df) are unchanged. The journal gains one event kind, position_grew (item 12).

21. **Operating prerequisites** (the setup guide must carry them; subagents could not edit d1exec_setup.md).
    - Keep free disk space: the write-ahead journal stops all stop repair on a full disk.
    - Use the one-https-URL rule of item 14 for both alert URLs. A mistake in that line refuses every command except offline status, flatten included, until the env file is fixed; resting stops stay.
    - capacity_hint is advisory (item 17).
    - The canary is about $15, not $12.
    - A critical unknown_position on a coin the sleeve was entering (item 12, Known limit b) needs manual action in the Hyperliquid UI.
    - Not yet proven live: orderStatus-by-cloid on a FILLED IOC.

### Appendix B.1. Verification pass 2, round 1 resolver

**Note 11 (quiet-window exception): amend the abort bullet.**
- Any abort that skips P7 (quiet window, deadline, budget, technical, unexpected or refusal) first marks some entry attempts position_unverified, with venue_status no_final_check.
- It marks every entry attempt of this session that said never_landed, if its trade did not open and its coin is not held on the other side.
- The run is then critical unresolved_entry. A quiet-window abort that would have exited 0 exits 2.
- The next run's P3 adopts and protects a same-direction position on that coin, or its P1 read settles the mark.
- The abort then raises stop_missing as before.

**Note 12 (double-entry guard and lagging fills, H1): replace the parts below.**

(1) Replace the bullet "A failed position read after a never_landed answer" with:
- **A failure during the entry.** This covers any exception between an entry's first send and the first position read after its loop:
  - the re-read before a retry;
  - the mid read for a retry;
  - the read after the loop.
- It includes budget exhaustion and the quiet window, and applies however the loop ended: its send limit, the :45 deadline, the budget-reserve cut-off, a quiet minute or the 3-attempt cap.
- It marks EVERY attempt of that trade in this session that said never_landed position_unverified (venue_status reread_failed), not only the last attempt. The error then propagates.

(2) New bullet: **the final check (P7) uses the same rule.**
- After each of P7's two position reads, a same-direction position is treated as an attempt's fill when all of these hold:
  - the coin had an entry attempt in THIS session that said never_landed;
  - that attempt's trade has not opened.
- The fill is journaled for the latest such attempt: filled, venue_status position_reread, filled_sz equal to the position size.
- An order_status_lag notice is raised.
- It is protected in the same run (recovered trade_opened). entry_overfill is raised if the fill is above the sized entry, as with a doubled position.
- An attempt from an earlier session is never adopted.
- If P7's second read shows an owned position with no open trade, P7 sweeps once more and re-reads the orders before it verifies stops. That position was either adopted then, or is owned by an unresolved or unverified entry.
- Any other position the sleeve does not own is critical unknown_position in that run; before, it was first raised by the next run.
- For a fill adopted in P7 the oid is not queried again, so trade_report may miss that entry's fee. This affects reporting only.

(3) New bullet: **a flat read in the same run proves nothing.**
- At the end of P7, an entry attempt of this session is marked position_unverified (venue_status flat_in_run) when all of these hold:
  - it still says never_landed;
  - its trade did not open;
  - the final read shows its coin flat;
  - no read during its entry showed the coin held on the other side.
- Reason: every read of a run may come from the same lagging node. That node needs a lag of at least ~50 s to answer never_landed, and in a single-entry run P7 reads only ~55 s after the fill.
- The run raises critical unresolved_entry and exits 2.
- The next run's P3 adopts and protects a same-direction position on that coin. Otherwise its P1 read shows the coin flat (the mark is then at least 10 minutes old), the mark settles as never_landed (position_flat), and the trade retries in that same run, within its window and attempt cap.
- Accepted cost: when the attempt truly never landed, the run sends one precautionary critical. No entry opportunity is lost, because the trade could not have retried before the next run anyway.
- The unresolved_entry message is now: "an entry said never_landed and no read of a later run has shown its coin flat: it owns a same-direction position there until one does".

(4) Overfill (ii): replace "after the stop is placed or repaired" with:
- The check runs after protect(), for each opened trade whose position is still open.
- It is skipped for a trade that protect() just closed (breach or unprotectable).
- It does not run for a coin whose protect() raised: that sweep records technical_failure, and the next sweep raises the growth, so the alert can come one sweep late.
- Growth must be at least half a lot above the largest of the sized entry, the opened size and any size already raised.

(5) Replace the "Known limit" bullet with:
- **Known limits (the H1 residue).** They need a lost POST response plus an info node at least ~50 s behind.
  - **(a) The retry fills and its ack arrives.** What happens depends on what the read at open shows:
    - **Both fills:** entry_overfill at open, with a stop over the whole position.
    - **One fill** (a node between the two fills): the trade opens with a stop for one fill. entry_overfill and the stop re-size come from the first later read that shows the grown size: P7 in the same run, or P3 of a later run. Until then up to ~2R is at risk, half of it unprotected.
    - **Neither fill** (flat, and flat again 1 s later): critical fill_not_visible and entries halted. There is no stop until P7 adopts the whole position with entry_overfill, or until the next run's P3 does if P7's reads miss it too.
  - **(a') The retry's ack is lost as well (never_landed).** P7 adopts the whole position with entry_overfill. If every read of the run misses it, the end-of-run mark hands it to the next run.
  - **(b) No retry fills.** P7 adopts the fill if a final read shows it. Otherwise the end-of-run mark makes the run critical and the next run adopts and protects it. The fill stays unowned only if a later session's P1 read, at least 10 minutes after the mark, also misses it (a node about an hour behind). That run then settles the mark and its P7 raises critical unknown_position. flatten refuses it as not owned, so it needs manual action in the Hyperliquid UI.
  - **(c)** Unchanged.

**Note 20 (code pin): replace the executor hash.**
- The approval must pin executor 6ecee13adb1f07006cddfff78806eb9244c0d6b2f8f75d89ad15ba3dbef487a3.
- Core dfdf6e9b00e507d964af4c98d87d29e848e111d76ce80d5237bc1e0e44f7f455 is unchanged, as are the runner sha 3496738e… and the fingerprint 63ff377d8e4b87df.
- No new journal event kinds. position_unverified outcomes gain two venue_status values, no_final_check and flat_in_run; reread_failed is unchanged.

**Note 21 (operating prerequisites): replace the unknown_position line with two items.**
- **(i) A critical unresolved_entry** means an entry's status said never_landed and nothing in that run proved its coin flat.
  - Check the Hyperliquid UI for a same-direction position without a stop on that coin.
  - The next hourly run adopts and protects it, or clears the mark, without help.
  - Most such alerts are precautionary: a transport error before the order reached the venue.
- **(ii) A critical unknown_position** on a coin the sleeve was entering (Known limit b residue, a node about an hour behind) still needs manual action in the Hyperliquid UI.

### Appendix B.2. Verification pass 2, round 2 resolver

Note 11 (quiet-window exception): replace the abort-mark bullet with the following.
- When a run loses P7 (a quiet window, deadline, budget, technical, unexpected or refusal abort), every entry attempt of that session that answered never_landed, and whose trade did not open, is marked position_unverified (venue_status no_final_check).
- The mark is skipped only when:
  - the local reads show the coin held on the OTHER side from the attempt, or
  - the entry's re-read saw it held on the other side (the coin is blocked unowned).
- A coin shown held on the attempt's OWN side is marked. That position may be the attempt's own lagging fill, shown by a later entry's read or by P7's first read. Through the mark it becomes owned, so the run raises critical stop_missing and unresolved_entry, and the next run's P3 adopts and protects it first.
- Before round 2, the code skipped every held coin: a naked sleeve fill could exit 0 and stay orphaned for good.
- Correction to the round-2 fuzz claims: "silent 0 / orphans 2" held only for single-candidate lag patterns. The 600-seed G1 fuzz, which adds a second candidate, was 6 silent and 24 orphans; it is now 0 and 0.

Note 12(5)(a), "the retry fills": add this sub-case.
- If the first read to show the grown size is P7's SECOND read, P7 does not re-size the stop and does not raise entry_overfill.
- unverified_stops fails that trade, and P7 closes the whole position as critical unprotectable.
- The result is safe and loud, but a legitimate trade is closed.

Note 12, known limits: add these.
- (d) The process is killed after an entry answered never_landed and before P7 (SIGKILL, a reboot, or launchd bootout's SIGTERM, which runs no handler), and the fill was real but hidden by the H1 lag.
  - Nothing marks the attempt, so the fill stays unowned.
  - Each later run raises run_stuck, then critical unknown_position and coin_held_unowned every hour.
  - flatten refuses the position. It needs manual action in the Hyperliquid UI, as for limit (b).
- (e) An IOC fills partially and the remainder IOC fills too, but the post-loop reads and P7's reads come from a node that lags between the two fills.
  - The trade opens at the partial size, with a stop for that size.
  - The rest has no stop until the next run re-sizes the stop.
  - Only a partial_fill notice is raised.
- (f) Two P7 artifacts from stale final reads (no capital at risk):
  - After a same-run P5 close, a stale final read raises a false critical unknown_position.
  - A stale read of a closed position can be adopted as the fill of a same-coin re-entry that truly never landed. That makes a phantom trade: a reduce-only stop on a flat coin, which the next run closes as critical venue_flat_other, and that re-entry is not retried.

Note 15 (reconciliation, H6): add the following.
- **Close verification.** Every close through close_position is checked (exits, breach, unprotectable, dust, not_isolated, stop_behind_liquidation, P7 and flatten). If its last read shows the coin flat, the acked reduce-only IOC fills must account for the position it started from, to within half a lot.
  - A close that started from a read already showing the coin flat also fails this check. That read is usually one made for another coin, such as an earlier close's ladder, and no IOC was sent.
  - When the check fails, the executor raises critical exit_incomplete and journals no trade_closed. The trade stays open and keeps its orders; flatten does not cancel them either.
  - If the position is still there, P7's reads protect it in the same run.
  - If the coin is truly flat, the next run's P2 reconciles it from fills, after its double read: venue_stop, liquidation, the close's own reason, or venue_flat_other.
- **Cost.** A venue stop or liquidation that fires between a close's reads, or a close whose ack is lost while its orderStatus lags, raises one critical exit_incomplete in that run and halts entries for the run. flatten exits 2; run it again.
- Before this change, one flat read from a lagging node closed the trade in the journal and cancelled its stop. That left the position naked and unowned for good: 64 of 78 orphans in the lagging-node fuzz.
- The canary's own close ladder is not covered by this check. After the canary, confirm in the Hyperliquid UI that the coin is flat.

Note 20 (code pin): the executor sha256 is now f654fd259ef65b9cf5cf6a3b3ef4ed27722bffb0d830e4b847c4f39e5af62677. The core sha (dfdf6e9b…), the shadow runner sha (3496738e…) and the config fingerprint (63ff377d8e4b87df) are unchanged. There are no new journal event kinds.

Note 21 (operating prerequisites): widen the manual-action line to cover known limit (d). It should read:

"A critical unknown_position, or coin_held_unowned, on a coin the sleeve was entering (item 12, known limits b and d; d usually comes with run_stuck) needs manual action in the Hyperliquid UI. A critical exit_incomplete settles itself in the next run; check the UI if it repeats."

### Appendix B.3. Verification pass 2, round 3 resolver

These edits apply to the round-2 note text. Numbers are the ones the reviewers cited.

**Note 9 (entry halt)**
- Add: fill_not_visible is also raised at run end by the acked-fill check (note 12, new item 'Acked fills').
- Add: when both reads at open miss an acked fill, entries halt directly, and the run is critical at once only if an attempt of that entry said never_landed in this session.

**Note 11 (abort mark and G1 mark scope)**
- Replace the skip rule with: "Every never_landed entry attempt of this session whose trade did not open is marked position_unverified, at the end of P7 and when a run loses P7.
  - A coin held on the other side is skipped, whether the local reads show it or the entry's re-read saw it (blocked unowned).
  - Exception: a side THIS session closed on that coin (a same-run reversal) does not count as held. A read from a node that lags the close still shows the sleeve's own closed position, which proves nothing about the new entry's fill.
  - Ownership stays direction-filtered, so the mark never owns a position on the other side."
- Add to the list of what flag_unprotected raises: critical fill_not_visible for a trade opened below its acked fills that no later read showed in full.

**Note 12 (double-entry guard and lagging fills)**
- New item, **Acked fills.** If the reads at open show less than the acked entry fills, the trade opens and its stop is sized at the read size. This covers a node between two fills (partial then remainder), or both reads missing them, in which case P7 opens the trade.
  - At the end of P7, or in flag_unprotected when P7 is lost, a trade still open whose last read still shows less than its acked fills is critical fill_not_visible (not raised again at later run ends).
  - The next run's first true read re-sizes the stop. Growth up to the sized entry raises nothing, as before.
  - A trade closed in the run (breach, unprotectable, dust) is skipped.
- (5)(a) 'Neither fill': now exact. If both reads at open miss the acked retry fill and an attempt of that entry said never_landed, the run is critical fill_not_visible at once, even when P7's reads then show only one of the two fills and open the trade at it. Every known-limit-(a) case has such an attempt. The next run's true read raises entry_overfill and covers the whole position.
- (5)(b): drop the claim that the remaining orphans need a node about an hour behind or a kill.
  - The same-run reversal case (B1, a stale read of the sleeve's own closed side) is now marked. The run is critical unresolved_entry, and the next run adopts and protects the fill.
  - Remaining: a stale read of a side closed by an EARLIER session, which needs a node about an hour behind; and the flipped-position cases of the lag fuzz, which come from the fake venue applying a reduce-only IOC as a plain fill.
- (e): replace the description.
  - Old: the run opens at the read size, exit 0, with only a partial_fill notice.
  - New: it is now critical fill_not_visible (Acked fills).
  - State the weak preconditions: no lost response, and a node lagging from the second fill through P7's reads, from a few seconds up to the gap between the two fills.
  - Exposure until the next run: the unread part of the position has no stop, but the run alerts.
  - Cross-reference 12(5)(a)'s sub-case: at a lag of about 3 s, P7's second read shows the growth and closes the trade as critical unprotectable.
- New residual known limit, not coded. It needs all four together:
  - a partial entry fill (acked);
  - a lost POST response on the remainder;
  - an orderStatus that did not know it (never_landed);
  - reads lagging between the fills through P7.
  The trade opens at the partial size, and the run can exit 0 with the remainder unprotected until the next run re-sizes the stop.

**Note 15 (reconciliation, H6)**
- Reword. A close whose acked fills do not explain a flat read keeps the trade and its orders (exit_incomplete).
  - After a P3 or P5 close, P7's reads protect a position that is still there.
  - After a close in flatten, in P7's re-sweep or in its final loop, no read follows. The run is critical exit_incomplete, and the next run's P3 protects it.
- Add: flatten keeps the orders of a coin P2 reconciled as venue_flat_other (hold_orders_on), as the hourly run does.
  - flatten --coin X within the node lag of X's entry therefore keeps X's stop.
  - X's trade is closed venue_flat_other and the run exits 2.
  - If X is still held, later runs raise unknown_position for it (unowned, stop kept), and it needs manual action.

**Note 20 (code pin)**
- executor fa8eeea3af618f5026f0d76be3fa4c4a215c03d507972e4be256e2ea42057e38.
- Unchanged: core dfdf6e9b00e507d964af4c98d87d29e848e111d76ce80d5237bc1e0e44f7f455, runner 3496738e…, plist 55c6f9d5…, fingerprint 63ff377d8e4b87df.
- No new journal event kinds.

**Note 21 (operating prerequisites)**
- Drop 'remaining orphans need an hour-behind node or a kill'.
- Add:
  - A critical fill_not_visible on an open trade means its stop covers only the size read. The next hourly run re-sizes the stop; to act sooner, check the position in the Hyperliquid UI.
  - flatten --coin on a coin just reconciled venue_flat_other keeps its stop. If the position is still there, it is unowned but stopped and needs manual action.
  - On a reversal whose entry fill the reads hid, enter() may also raise a false unknown_position alongside the real unresolved_entry. The next run adopts the fill.

### Appendix B.4. Protect-all redesign (architect)

These edits apply to the round-3 note text.

**New note 22: A1, the venue-attached stop.**
- **How an entry is sent.** Every entry IOC is sent as ONE action (grouping normalTpsl) together with a reduce-only stop-market child:
  - the child's size equals the IOC's;
  - it is on the closing side;
  - its trigger is the IOC's reference mid (the mid its limit is computed from) − d × 2 × ATR(signal) × unit, normalised.
  - The gateway builds both orders and refuses a child that is not on the protective side of the limit.
  - Both intents (role entry; role stop with the next stop version) are journaled before the send, and both outcomes after it.
- **When the venue places the child.** The venue places the child when the IOC fully fills, whatever becomes of the reply or the reads. It cancels the children of a parent that does not fully fill: an IOC's cancelled remainder leaves NO child.
- **How the child's outcome is journaled.**
  - After a full-fill ack: resting.
  - After a partial fill, no fill or rejection: canceled. A child error is rejected.
  - After a lost reply: ambiguous. P7's resolve_unresolved (or the next run's P2) settles it.
  - The first order read that lists it journals its oid (outcome open, venue_status listed), so a fill of the child reconciles its trade as venue_stop.
- **Stop anchor: re-anchored to the fill, so exact.** The trade's stop remains venue entryPx − d × stop_dist (note 2 unchanged).
  - If the fill is at the reference price, the child IS that stop and nothing more is placed.
  - Otherwise, once a read shows the position, protect() places the fill-anchored stop and then cancels the child (the existing place-then-cancel; modify stays AST-banned).
  - Why exact: one stop rule on every path (entry, recovery, adoption); R stays exactly comparable with the shadow; nothing new to verify per path. The cost is 2 exchange actions per entry when the fill differs from the reference.
  - Until re-anchored, the child is the stop at the reference price. On the adverse side that is at most the 50 bps entry slippage cap away from the rule stop: at most about 0.125 R more at a 4% stop (0.116 R at the 4.3% historical minimum); usually a few bps.
- **The fallback when the IOC does not fully fill.** No child exists. The sleeve stops the fill as before: from the read, sized to the position.
  - New: if no read of the run shows an acked fill, a reduce-only stop is placed from the acks (the acked size, at the rule distance from the acked average price). It is placed unless a stop already covers it; a full fill's child does. The first read that shows the position re-anchors it.
- **Proof of fills.** THIS session's proof that an entry filled, whatever a read shows, is the larger of:
  - the sum of the trade's listed children (each rests only because its entry fully filled);
  - its acked fills that a read showed less of.
  - The proof is void once the session has sent a close for the trade.
  - When the read shows less than the proof:
    - protect() sizes the stop to the proof and keeps the trade's children;
    - P7's I6 check and the close verification (note 15) use the proven size;
    - the growth check raises entry_overfill in that run;
    - the run end raises critical fill_not_visible.
  - Without this, a doubled lost-reply entry's two children looked like duplicate stops to a lagging read and one was cancelled (seen in the fuzz; fixed).
- **Flat-coin cleanup** (sweep and flatten) never cancels a reduce-only stop of a trade that never opened (a child, or a stop from acks), nor a guard stop (note 23). Such a stop contradicts the flat read; on a truly flat coin it is inert, and protect() cancels it once a later trade on that coin has its own verified stop.
- **Settling a position_unverified mark** (note 12) is skipped while the P1 order read lists a child of that trade.
- **Canary (note 16).** The canary makes its entry the same way. The child is at 0.9 × the reference mid. New required checks:
  - canary_child_listed;
  - canary_child_cloid_matches;
  - canary_child_trigger_px_matches;
  - canary_child_sz_matches;
  - canary_child_order_type_ok.
  - The canary cancels both of its stops at the end.
  - Spec §23 changes: normalTpsl is now USED. Whether the venue accepts an IOC parent with a normalTpsl child, places the child on a full fill, and lists it with its cloid is settled by the canary. It is not proven live yet; do not arm before it passes.

**New note 23: A2, protect every position (amends I9 and note 18).**
- **The rule.** Every sweep (P3, P7, and the end of flatten) gives each position the reads show a reduce-only stop that closes all of it, whether or not the sleeve can attribute the position.
  - Coverage means one resting reduce-only stop trigger on the closing side, not a take-profit, of at least |szi| − half a lot, whoever placed it.
- **Owned position:** its rule stop (protect()). One still bare after protect() gets the rule stop as a guard, which P7 verifies as its I6 stop.
- **Unattributed position** (unknown_position, direction_conflict, canary_residue): a guard stop for |szi| at the rule distance from its entryPx.
  - Distance source, in order: the latest shadow entry's ATR for the coin; else the stop distance its last journaled entry was sized with; else 15% of entryPx.
  - It is moved to mark ∓ the same distance when the mark is at or beyond that level.
  - It is moved halfway from the liquidation price back to the mark when it would sit at or beyond the liquidation price.
  - If no such price exists, it is critical unprotected_position.
- **What stays the same for unowned exposure.** Such a position stays critical and is NEVER traded down or closed. flatten still refuses it. Orders the sleeve did not place are still never touched.
- **Mechanics.**
  - Guards use role guard, trade_id guard:<coin>, n counting up. No new journal event kinds.
  - A guard is a protective stop order: the quiet-window exception of note 11 now covers it. place_stop is still its only call site, with at most two attempts per position per sweep, and GUARD_MAX_TRIES = 4 per coin per run.
  - A notice position_guarded is raised every run while a guard is the protection.
  - P7 sweeps once more for a bare position its second read shows. After its re-read, a position no LISTED stop covers is critical unprotected_position.
  - A run that loses P7 raises unknown_position for an unowned bare position; the next run's P3 guards it before exits and entries.
  - A guard fill reconciles an owned trade as venue_stop.

**Note 11:** the exempt action is "a reduce-only stop-trigger order: an owned position's rule stop, or a guard (note 23)".

**Note 12, known limits:**
- **(a) Doubling is unchanged in mechanism:** a never_landed answer plus a flat, lagging re-read leads to the retry. But both fills are now protected at the venue by their children from the fill on. When both children are listed, the stop covers the proof and entry_overfill plus fill_not_visible are raised in that run (before: a stop for one fill until a later read).
- **(b), (d) and the round-3 reversal case:** a full fill that the sleeve cannot attribute (a lagging or stale read, a node an hour behind, a kill) is protected by its child. Any position a read shows is guarded (note 23). Ownership, and so exits that follow the shadow, may still need manual action in the Hyperliquid UI; exposure no longer does.
- **(e) partial then remainder:** the stop covers the acked size.
- **Remaining residual:**
  - a partial fill (no child) whose reply is lost (no ack), with every read of the run lagging: no stop until the first read that shows it (then marked/owned or guarded);
  - in a LATER session, a stale read that shows less can still re-size an existing stop down (as before this change).

**Note 15:** a close is verified against the larger of the read it started from and the fill proof (note 22).

**Note 20 (code pin):**
- executor 93c45994feb27ec49088f3be38b34ec1faa9c49663d585f5ad1bf9c5d539a181;
- core cb76c74b11e51c6dad1cbac7d401521975062a962b7307ae00d4ac5fff533f8f;
- runner 3496738e… and fingerprint 63ff377d8e4b87df unchanged.
- **Journal:** no new event kinds. ORDER_ROLES gains guard. Entry intents carry grouping normalTpsl and context stop_child. Child intents carry context child_of, trigger_px and d. Outcomes gain venue_status listed and waiting.

**Note 21 (operating prerequisites):**
- Run the canary, which must pass the 5 child checks, before arming.
- **unknown_position:** the position now rests under a guard stop (see position_guarded); decide in the UI whether to keep it, since flatten will not close it.
- **unprotected_position:** a stop could not be placed or listed; check the UI.
- Children and guards may rest on flat coins; they are inert and are cancelled when a new trade on that coin has its own stop.

### Appendix B.5. Protect-all redesign, round 1 resolver

These edits apply on top of the previous resolver-round delta (notes 22 and 23 as proposed there).

**Note 22, "Proof of fills": replace the paragraph.**
- **The definition.** THIS session's proof that a trade's entry filled is the SUM over its non-canary entry attempts of this session of the larger of two sizes:
  - (a) the attempt's acked or resolved fill. A fill journaled from a position read (position_reread) proves nothing a read does not;
  - (b) its stop child's size, if the child is listed now or journaled open. Open comes from a listing (learn_listed_oids at a sweep start) or from its orderStatus. The child stays proof after this session cancels it to re-anchor the stop.
- A child acked resting needs no proof of its own: its full-fill ack is the same size.
- The acked fills a read at open showed less of are part of this sum.
- The proof is still void once this session sends a close for the trade.
- **Why the sum.** In round 1 the proof was max(listed children, acks). Under a normal taker fill it under-counted:
  - Attempt 1's reply is lost and its orderStatus lags. The re-read is flat, the retry is acked, and the read at open shows 12.
  - protect() re-anchors the stop and cancels the retry's child. P7 lists only the first child, so the proof was 12, equal to the lagging read.
  - P7 then cancelled the first child as a duplicate. The run ended at exit 0 with no critical and 24 held under one 12 stop. The same happened for a partial fill plus a lost remainder: 6 of 12, or 1.2 of 12, unstopped.
- **When a read lags the proof.** As before: the stop is sized to the proof, the children are kept, growth raises entry_overfill, and the run end raises fill_not_visible. In addition:
  - P7 sweeps once more when, after its second read, an open trade's lagging proof has no single stop that covers it. This happens when a child the first final order read missed raised the proof. Before, the final check failed I6 and closed the position as unprotectable.
  - The run end also raises fill_not_visible when the last read shows the coin flat and the proof exceeds every size a read showed for the trade (its opened size, or a growth already raised).
- **Known over-statement (loud).** A stop or child that fires in the same run as its entry leaves the proof above the position. The result is a false fill_not_visible and an oversized reduce-only stop. The next run clears both.

**Note 22, "How the child's outcome is journaled": correction.**
- A listed child's oid is journaled by the first sweep (P3, P7, flatten) after an order read lists it, not by "the first order read".
- A child that fires before any sweep lists it reconciles as critical venue_flat_other. This is loud and affects accounting only.

**Note 22, "The fallback": add.**
- The same stop from the acks is also placed when the entry's reads are cut short after an acked fill: by the quiet window, a failed read or the budget, but not a refusal.
- It is placed before the failure goes on. A reduce-only stop is exempt from the quiet window and the deadline.
- It is skipped when a stop already covers the acked fill (a full fill's child does).

**Note 16 (canary): new required check.**
- canary_entry_ack_parsed: the grouped reply parsed with the IOC acked filled in full, so its child is resting.
- A reply format the parser does not know would turn every live entry ambiguous. The canary now has 6 A1 checks.

**Note 23: corrections and policy.**
- **I6 and guards.** An owned position's guard is P7's I6 stop only when it sits at the rule stop (source rule_stop). A guard moved to the mark or clamped at the liquidation price fails I6, and P7 closes the trade as unprotectable (loud).
- **I9 policy.** A2 places reduce-only guards on ANY position in the sub-account. This is acceptable only because the sub-account is dedicated to the sleeve: nothing else may trade in it. Unowned positions are still never reduced or closed, and unknown orders are never touched.
- **Leftover orders.** Children and guards kept on flat coins (keeps_on_flat) stay until a later trade on that coin has its own verified stop. They are inert but visible in the UI.

**Note 12 (known limits): replace (a) and update the residual list.**
- **(a) Doubling.** The mechanism is unchanged, but each fill is proven from the fill on, by its ack or its child, whichever child the session has cancelled.
  - Once any read shows the trade, the stop covers both fills. entry_overfill and/or fill_not_visible are raised in that run.
  - If no read of the run shows the coin, the trade never opens and both children rest (covered by their sum). unresolved_entry and fill_not_visible are raised.
- **Residuals:**
  - a partial fill (no child) whose reply is lost (no ack), with every read of the run lagging: no stop until a read shows it (unchanged);
  - a later session's stale read can still re-size an existing stop down (unchanged);
  - the proof over-statement above (loud);
  - if the fill-anchored stop is rejected twice, the trade is closed as unprotectable even though its child covers it. This is pre-registered §13 behaviour; it costs a trade, not protection, and it is loud.

**Note 15.** Unchanged in wording; "the fill proof" now means the per-attempt sum.

**Note 20 (code pin).**
- executor 00a1ca92d28eecb141a3451eb7ed1621238746ede97804e4dab61a5b67832c1d;
- core cb76c74b11e51c6dad1cbac7d401521975062a962b7307ae00d4ac5fff533f8f (unchanged);
- runner 3496738e… and fingerprint 63ff377d8e4b87df unchanged;
- no new journal event kinds.

**Note 21.** Before arming, the canary must pass the 5 child checks plus canary_entry_ack_parsed.

**Test note.** The fake exchange can fill at a taker offset (Harness.taker_bps). The A1 doubling, close-proof and mixed-proof tests run at the mid and at 3 bps. At 3 bps protect() re-anchors: it places the fill-anchored stop and cancels the child, which is the normal live path.

### Appendix B.6. Protect-all redesign, round 2 resolver

These edits apply on top of the round-1 resolver delta.

**Note 22, "Proof of fills": add a paragraph "Size a read showed".**
- For a trade with a non-canary entry attempt in THIS session, the proof is at least the largest same-side size any position read of this session showed for the trade once it was open. That includes the read it opened or was recovered at, and every later read (another coin's entry reads, refresh_account, P7). It is recorded after each such read.
- Why (verifier B1): a fill whose reply was lost and that left no child (a partial fill, or a child the venue rejected) is proven only by a read. A later read from a node that lagged it re-sized the stop down to the stale size and cancelled the full stop. The run then ended exit 0, no critical, with 6 of 12 (or 3 of 9) unstopped, although a read of the run had shown it all.
- Now that stale read counts as lagging: the full stop and the children are kept, and the run is critical fill_not_visible.
- **Scope.** Only trades with an entry attempt in this session. For an older trade, a later smaller read is a real reduction (or a node about an hour behind) and re-sizes the stop down as before. A venue stop that fires on an older trade in the run raises nothing.
- The proof is still void once this session sends a close for the trade.
- **Known over-statement (loud) now includes a read.** A stop, child, liquidation or ADL that reduces this session's trade in the same run leaves the proof above the position. The result is a false fill_not_visible and an oversized reduce-only stop; the next run clears both.

**Note 22, run-end check: add.**
- When two or more entry attempts of an open trade in this session said never_landed (still, or since marked position_unverified, or adopted from a position read), and no read of the run showed their summed size, the run is critical fill_not_visible.
- Reason: the coin was flat before the entry and the trade is open, so one of those statuses was wrong and the other proves nothing (live-safety N1: exit 0 with 24 held under a 12 rule stop and two 12 children).
- A false alarm is possible when the first attempt truly never landed and the second filled with its reply lost. The sleeve cannot tell 12 from 24; the next run's read settles it.

**Note 22, P7 re-sweep: replace "P7 sweeps once more when, after its second read, an open trade's lagging proof has no single stop that covers it".**
- P7 sweeps once more when, after its second reads, an owned trade's size to cover (its read, or its proof of fills while the read lags) grew past what the first final sweep protected, and no listed stop nor any stop this session saw acked resting covers it. If the first final read hid the coin, the first sweep protected nothing.
- This covers the round-1 case (a child listed only by the second order read) and live-safety N4.
- Growth first seen by P7's second position read is now stopped in the run instead of closed at market as unprotectable. It is raised as entry_overfill when it exceeds the sized entry.
- The round-1 report's claim that N4 "no longer applies to the doubled lost-reply entry" was inaccurate. It is fixed now.
- A coin the first final read hid is not re-swept while an acked stop covers it, so a lagging listing gets no duplicate for it.

**New note 24, "P7 order-listing lag" (live-safety N5).**
- Before closing a position as unprotectable, P7 re-reads the order listing up to LISTING_REREAD_TRIES (3) more times, LISTING_REREAD_BACKOFF_S (5 s) apart, after its 1 s re-read. It does so while all of these hold:
  - a failing trade would pass I6 once the stops this session saw acked resting, and sent no cancel for, are added to the listing (acked_plan_ok);
  - the sweep window is open;
  - the budget is above the sweep reserve.
- That is about 16 s at most. A listing that lags longer still ends in the unprotectable close (loud).
- A stop an earlier run placed that the listing no longer shows is not waited for: a lagging node would still list an hour-old stop, so its absence is not lag.
- The P7 sweep can still place one duplicate stop while the listing lags. It is inert and reduce-only, and the next run's P3 cancels it (keeping the lowest oid).
- These are code constants, not config: the fingerprint is unchanged.

**Note 12 (known limits): replace (a) and the residual list.**
- **(a) Doubling.** Each fill is proven by one of: its ack; its child, if listed or journaled open (from a listing or its orderStatus), and still after this session cancels it; or a read of the run that showed it.
  - A read shows the trade and the proof covers both fills: one stop covers the proven size, and entry_overfill and/or fill_not_visible are raised in that run.
  - Two attempts said never_landed: fill_not_visible is raised in the run. Until a read shows the full size, only the sum of the rule stop and the children the venue placed covers the position.
  - One attempt said never_landed, its fill left no attributable child (the venue rejected it, or listed it without its cloid), and no read of the run shows it: silent in the run, residual (i). The next run's first truthful read raises entry_overfill and stops all of it.
  - No read of the run shows the coin: unchanged.
- The previous delta's sentence "Once any read shows the trade, the stop covers both fills. entry_overfill and/or fill_not_visible are raised in that run" was false for live-safety N1 and N2. It is replaced by the above.
- **Residuals:**
  - (i) A fill with no ack (its reply lost) and no attributable child (a partial fill, or a full fill whose child the venue rejected or listed without its cloid), with every position read of the run lagging it: no stop for it until a read shows it. Measured silent classes: M9, N2, and M1/M3/M5 rows with rejected or no-cloid children. Each is protected by the next run.
  - (ii) Within a session, a later stale read no longer re-sizes the stop of a trade with an entry attempt in this session below what an earlier read showed. A later session's stale read still can (unchanged).
  - (iii) A read s with 0 < s < proof that shows the sleeve's own lost partial fill (live-safety N3) is taken as a lagging view. The stop covers the proof, not proof + s. The run is critical fill_not_visible and the next run's first read stops the rest (loud).
  - (iv) The proof over-statement (loud; note 22).
  - (v) Fill-anchored stop rejected twice: closed as unprotectable although its child covers it (§13; unchanged, loud).
  - (vi) An order listing more than about 16 s behind a stop placed in the run: unprotectable close (loud) and inert duplicate stops.

**Note 23: add.**
- **Guard with no mark.** When allMids lacks the coin, guard_stop_px enforces only the liquidation bound. A guard on an unowned position may then sit past the market and fire at once. Kept deliberately: the alternative leaves the position bare, and the sub-account is dedicated to the sleeve (I9).
- **Venue caveat.** If Hyperliquid keeps a normalTpsl child after a partially filled IOC parent, child_proof counts the child's full size. Every such partial fill would then give a false fill_not_visible and an oversized reduce-only stop (loud, safe). The canary checks full fills only. Confirm the docs' statement (untriggered children are cancelled with the parent) before arming.

**Note 15.** Wording unchanged; "the fill proof" now includes the size a read showed.

**Note 20 (code pin).**
- executor 9b11bf3f6969d2b5c05593750660ecb9c4931cb47dcf3a4a42673f1fd4681d01;
- core cb76c74b… (unchanged); runner 3496738e… (unchanged); fingerprint 63ff377d8e4b87df (unchanged);
- no new journal event kinds and no new problem codes (fill_not_visible is reused).

**Test note.** New helpers in the test file: `_position_node_lagging(..., fresh=)` (one current read among lagging ones), `_order_node_lagging` (a physically consistent order-listing node lag), `_order_reads_missing`, `_position_reads_seen`, `_second_run_entry`.

### Appendix B.7. Protect-all redesign, round 3 resolver (final bytes)

These edits apply on top of the round-2 resolver delta.

**New note 25, "P7: a proof the final reads miss" (verifier B1 and B2).**
- **The rule.** After P7's final reads and any re-sweep, each open trade with a non-canary entry attempt in THIS session gets one reduce-only stop, at the trade's stop, for its proof of fills, when:
  - its final reads show no position on its side (flat, or only the other side); and
  - that proof (`fill_proof`: acks, children, the largest size a read of the run showed, the cover floor of note 26) is more than any one owned stop on the coin covers (listed, or acked resting with no cancel sent).
- **Failure.** Two tries; if neither rests, the run is critical stop_missing.
- **Truly flat coin.** The stop is inert.
- **Run-end check.** `check_acked_entries` treats a read that shows only the other side as flat. It raises fill_not_visible when the proof exceeds the size the trade opened at and every growth already raised.
- **Why.** The sweep protects only the positions the reads show:
  - B1: another coin's entry read showed 12 and both final reads showed flat; the run ended loud with 12 under a 6 stop.
  - B2: a same-run reversal whose final reads showed the closed long ended exit 0, no critical, with short 12 under a 6 buy stop.
- **Scope.**
  - Not for a trade with no entry attempt in this session. For such a trade, a flat or smaller read is a real reduction, or a venue stop that fired.
  - Not for an entry that did not open in the run; see residual (vii).
- **Next run.** P3 keeps one stop for the read and cancels the rest.
- **Journal and codes.** No new event kinds or problem codes: stop_placed, stop_missing and fill_not_visible are reused.

**New note 26, "Dust at open" (live-safety D1-DUST).**
- **What counts as dust.** A trade is dust when the larger of the read at open and `fill_proof` is below min_order_usd, priced at min(entry, stop). The read alone no longer decides it: a node that lags a remainder's fill shows only attempt 1's dust partial, while the acks prove the whole entry.
- **Unsettled attempts block the dust close.** While any entry attempt of this session is unsettled (never_landed, or still ambiguous), the trade is never closed as dust. Instead:
  - the session's cover floor is set to the dust size plus the unsettled attempts' requested sizes (what they could have filled);
  - the floor is part of `fill_proof` until this session sends a close, so `protect()` stops that size from the open, keeps the children, and no later read of the session re-sizes it down.
- **If the attempt truly never landed.** The stop is oversized (inert beyond the dust), and the run is critical fill_not_visible. This false alarm cannot be avoided: the sleeve cannot tell a never-landed attempt from a lost reply behind a lagging orderStatus. The next run re-sizes the stop to its read. If the venue rejects a stop below $10, that run's P3 closes the dust as unprotectable (loud).
- **Floor above the sized entry.** This happens when an earlier attempt of the entry also said never_landed. check_growth raises it as entry_overfill (loud); it is the doubling it may be.
- **The dust close's ladder is capped.** It sells at most the dust it was decided on. It stops at a read that shows more than is left (a fill the proof missed, or an order the sleeve did not send). The run is then critical exit_incomplete (with dust_open), and `protect()` stops the size that read showed.
- **The proof is still void after a dust close.** A dust close still voids `fill_proof` for the session, as every close does. That drops nothing: a dust close is now sent only when every attempt is settled and the proof itself is dust. A child exists only after a full fill, which clears the minimum.
- **Reachability.** All of this needs a partial fill below min_order_usd.

**Note 22, "Proof of fills".** Add: the proof of a trade with an entry attempt in this session is also at least its cover floor (note 26).

**Note 22, N1 wording (verifier NB4).** "no read of the run showed their combined size" becomes "no read of the run showed the summed requested size of this session's attempts". With at most two sends per trade per session, the two readings are equivalent.

**Note 12 (known limits), (a) Doubling.**
- Replace the sentence "A read shows the trade and the proof covers both fills: one stop covers the proven size" with: "A read of the run showed the trade and the proof covers both fills: one stop covers the proven size, also when the final reads show the coin flat or only on the other side (note 25); entry_overfill and/or fill_not_visible are raised in that run."
- The round-2 note 12(a) sentence was false for B1 and B2; this replaces it.

**Note 12 residuals.**
- (i) Unchanged.
- (ii) Unchanged. Add: it is silent. A manual armed rerun within about a minute of a run, reading through a node about 53–90 s behind, re-sizes a doubled trade's stop to the stale read and cancels the full stop (live-safety r3: 20/20 rows). It also clears run 1's critical alert state.
  - Operator guidance until a cross-session floor exists: leave at least UNVERIFIED_SETTLE_AFTER (10 min) between a run and a manual armed rerun.
  - Proposed follow-up: in P3, floor a trade's stop at the largest stop_placed size journaled for it in the last 10 minutes. This uses existing events.
- (iii)–(vi) Unchanged.
- New (vii) (verifier r3 V5, loud): in a same-run reversal, the re-read before the retry can show the sleeve's own closed long. The entry then aborts (unknown_position). The short's lost partial fill has no stop in the run, even when a later read of the run (another coin's entry read) shows it. The run is critical (unknown_position, unresolved_entry), and the next run adopts it.
- New (viii) (verifier NB2, loud): if P7 runs within about 16 s of :56, the listing re-reads can use up the window before another failing coin's unprotectable close. That coin is still raised as unprotectable.
- New (ix) (verifier NB3, contrived, loud): a child acked with a placeholder oid and later cancelled by its real oid without its cloid stays counted in acked_stops.
- New (x): the false fill_not_visible and the oversized stop of note 26 (loud).

**Note 20 (code pin).**
- executor 2fb94efd2b1af84fc4b5bcdf08d7dda2e3fcac0367b32b049d4400d241243516;
- tests 8afd7cff6722c0ebd81401e9e60b966a624d6a25f04421a86fac94e70af085b0;
- core cb76c74b… (unchanged); runner 3496738e… (unchanged); fingerprint 63ff377d8e4b87df (unchanged);
- no new journal event kinds and no new problem codes.

**Test note.**
- New helpers `_position_nodes` (a physically consistent position node per read: fresh, a lag in seconds, or stalled) and `_ioc_sells`.
- Adopted the live-safety wire probe as `test_the_normal_tpsl_wire_on_the_real_sdk_for_both_sides`.
