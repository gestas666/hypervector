# Hypervector v90 — Critical Review

## Scope

Box-only review of `/workspace/hypervector` (partial extract). No machineId. Operator intent: **option B** — aggressive bankroll builder, **no profit lock on any route**. V90 is live as `bidirectional-live-1790053305835` (HANDOFF). Compared `configs/multi_asset_growth_first_5000_bankroll_builder_candidate_v90.toml` to V89, the profit-lock stack, hourly/ETH/HYPE/BTC/band providers, friction/evidence for `xyz:TSLA` / `xyz:SNDK`, config/runner/stage, and docs/plans for option-B contradictions. Pack is incomplete (runner imports many modules not shipped here); claims below are from present files + HANDOFF.

## Executive summary (highest value only)

**Option B is correctly configured and fail-closed against silent re-locking.** The candidate omits all `profit_lock_*` keys (default `"none"`); unlocked `hourly_donchian_20_10_atr20_bidirectional_v1` refuses lock smuggling in validation tests; `CohortProfitLockController` returns immediately when `plan.profit_lock_policy == "none"` (`src/hypervector/live/cohort_profit_lock_controller.py:144`). Approval scopes include option B; live fingerprint matches the post-correction value `c8938787268cfa94…`.

Executable aggression is intentional: BTC sweep (~$536 @ 10x) + Donchian 20/10 on SOL / `xyz:SNDK` / `xyz:BRENTOIL` / `xyz:TSLA` (8x; SNDK ~$1,948 ≈ 3.9×). ETH, HYPE, `xyz:SPCX` are observe-only (`execution_symbols = []`). That is concentration, not capital-preservation creep.

**Highest-value issues are footguns / ops, not a silent 100/25/50 re-lock:** (1) HYPE still carries V89-sized `margin_fraction = 0.08` / `max_notional_usd = 2500` while observe-only — one TOML edit re-arms ~half the bankroll; (2) fail-closed validation exits 1 so the supervisor treats refusal as crash (already burned one armed start per HANDOFF); (3) BTC asset `stop_bps = 80` vs provider `stop_bps = 60` (provider wins today). `provider_recipe_exit_policy = "honor"` + `target_policy = "none"` is **not** “exits never fire” — Donchian recipe exits are the option-B stack.

## Findings

### Finding 1 — High

- **Severity:** High
- **Location:** `configs/multi_asset_growth_first_5000_bankroll_builder_candidate_v90.toml:49-55` (HYPE asset), `:148` (`execution_symbols = []`); same pattern ETH `:127`, `xyz:SPCX` `:160`
- **What's wrong:** Observe-only demotion cleared execution membership but left the largest asset envelope in the book. At ~$4,870 equity, HYPE sizes to `min(4870×0.08×10, 2500) = $2500` (~51% notional). HANDOFF already proved `validate_runtime` rejects **provider `sizing_overrides` outside executable scope**; asset-level caps are a separate path — setting `execution_symbols = ["HYPE"]` without cutting size arms a half-bankroll route V90 deliberately sidelined.
- **Impact on aggressive bankroll building:** No clip on current live PnL (observe-only). One-edit arming footgun can wipe the SNDK-led bankroll plan.
- **Recommended fix:** Shrink observe-only envelopes (e.g. HYPE `margin_fraction ≤ 0.02`, `max_notional_usd ≤ 500`) **or** add validate_runtime rule: symbols with empty execution membership across all providers must sit under an observe ceiling. Refresh fingerprint/approval if TOML changes.

### Finding 2 — High

- **Severity:** High
- **Location:** HANDOFF `docs/handoff_excerpt/HANDOFF_v90_head.md` (first armed start / follow-up 1); live entrypoint error path (not fully present in pack)
- **What's wrong:** First arm fail-closed on `provider entry sizing exceeds executable provider-symbol scope` (inert ETH/HYPE overrides). Exit **1** made the supervisor treat a correct refusal as a crash, relaunch, and write another ~900 MB replay. HANDOFF follow-up: map that error to exit **2**.
- **Impact on aggressive bankroll building:** Delays entries, fills disk, invites panic restarts. Does not alter option B when healthy.
- **Recommended fix:** Entrypoint `sys.exit(2)` on validation / `MultiAssetLiveRunnerError`; keep exit 1 for unexpected crashes; require `scripts/cohort_runtime_validation_check.py` before every armed start; ensure LaunchAgent does not restart on exit 2.

### Finding 3 — Medium

- **Severity:** Medium
- **Location:** V90 TOML BTC asset `stop_bps = 80.0` (`:22`); BTC provider execution `stop_bps = 60.0` (`:118`). Precedence: `BoundExecutionPlan.stop_price` / provider contract (`src/hypervector/live/cohort_execution_plan.py`); asset stop is friction fallback only when a provider has no execution block (`src/hypervector/research/cohort_friction_contracts.py` runtime path).
- **What's wrong:** Live BTC protective stop for the executable sweep is **60** (matches `liquidity_sweep_long_1h_stop60_target60_v2`). Asset 80 is inert for that route but looks like a wider safety stop.
- **Impact on aggressive bankroll building:** None today. A future “prefer asset stop” change would **widen** BTC risk vs the 60/60 research contract.
- **Recommended fix:** Set BTC asset `stop_bps = 60.0`, or assert asset/provider equality in config validation for symbols with provider `fixed_bps` execution.

### Finding 4 — Medium

- **Severity:** Medium
- **Location:** V89 Brent on `hourly_donchian_8_4_atr20_bidirectional_v1` → V90 Brent on `hourly_donchian_20_10_atr20_bidirectional_v1` (`:132-138`); evidence honesty in `src/hypervector/live/hourly_price_evidence.py` (`mechanism_standardisation_untested`, p≈0.52)
- **What's wrong:** Wiring and friction for Brent on 20/10 are present; the **edge claim for the mechanism swap** is not. Bankroll path funds an untested standardisation.
- **Impact on aggressive bankroll building:** Can dilute/invert Brent’s contribution; does not reintroduce locks.
- **Recommended fix:** Keep if operator accepts the swap; else restore 8/4 under its identity for Brent only, or observe Brent until a pre-registered 20/10 vs 8/4 cell clears. Do **not** “fix” with 100/25/50.

### Finding 5 — Medium

- **Severity:** Medium
- **Location:** `docs/plans/2026-09-21-v90-profit-protection.md`; `docs/reviews/2026-09-21-v90-profit-protection-readiness.md` still describe prepared 100/25/50. Counterweight: aggressive plan option-B banner; `docs/reviews/2026-09-21-v90-profit-lock-exit-review.md` prefers B; approval scopes `option_b_no_profit_lock_…`
- **What's wrong:** Skimming the protection plan could push arming protected `…_profit_lock_bidirectional_v2` or pasting 100/25/50 onto v1 (tests refuse the latter).
- **Impact on aggressive bankroll building:** Process risk of undoing option B; live TOML currently unlocked.
- **Recommended fix:** Banner those docs **SUPERSEDED BY OPTION B — DO NOT ARM**. Leave protected v2 frozen in source only.

### Finding 6 — Low

- **Severity:** Low
- **Location:** ETH/HYPE providers `:123-128`, `:144-149` — `sides = ["long","short"]` with `execution_side_overrides` long-only and empty `execution_symbols`
- **What's wrong:** Dead short membership on observe-only routes. Not a live short leak; not a short disable that guts the funded book.
- **Impact on aggressive bankroll building:** Noise / future footgun if execution is re-enabled and overrides forgotten (would stay long-only).
- **Recommended fix:** Align `sides` with observe intent or document observe side semantics once.

### Finding 7 — Low / informational

- **Severity:** Low
- **Location:** `maximum_positions = 8` (`:4`); five executable symbols
- **What's wrong:** No contention (5 < 8). Leftover venue positions on observe symbols could consume slots after a messy transition (HANDOFF preflight claimed flat).
- **Impact on aggressive bankroll building:** None while flat and observe-only stay empty.
- **Recommended fix:** Optional `maximum_positions = 5`, or keep 8 for deliberate re-arm headroom after size review.

### Explicit scare-list verdicts (not bugs)

| Scare | Verdict |
| --- | --- |
| Silent 100/25/50 re-lock | **Not found.** TOML omits lock keys → default `"none"`; v1 refuses lock params (`tests/test_v90_profit_protection.py`); controller early-return on `"none"` (`cohort_profit_lock_controller.py:144`); option-B tests + approval scopes. Protected v2 only as derived test config. |
| `honor` + `target_policy = none` ⇒ exits never fire | **False.** Honor applies Donchian/band **recipe** exits; no fixed take-profit is the option-B design (structural clamp + channel exit + max hold). |
| `timeframe = "15m"` vs hourly strategy | **Intentional.** Provider publishes source 15m / signal 1h (`hourly_price_provider.py`). |
| `xyz:TSLA` missing friction ⇒ fail-closed skip | **Present.** `v90_hourly_modeled_contracts()` includes TSLA; evidence row present; `HOURLY_PRICE_SYMBOLS` includes `xyz:TSLA`; `execution_symbols` lists TSLA. |
| SNDK `0.05` / `2600` mis-wired | **Correct at asset level.** At ~$4870 equity: `4870×0.05×8 ≈ $1948` < $2600 (cap non-binding). Matches HANDOFF. Size is an **unvalidated risk preference** (evidence says so), not a mis-wire. |
| Accidental whole-book de-risk vs V89 | **No.** BTC cut is intentional; unlocked Donchian expansion + SNDK upsize + no lock is the aggressive package. ETH/HYPE/SPCX observe concentrates capital on funded routes. |

## What looks solid

- Option-B tests: unlocked v1 on all hourly funded routes; refuse lock keys on v1; protected v2 only via derived config; TSLA allowlist / friction / evidence honesty.
- Candidate vs V89: retires SOL range-short, Brent 8/4 as sole Brent mechanism, executable ETH/HYPE/SPCX; funds BTC sweep + Donchian 20/10 on SOL/SNDK/Brent/TSLA; strips the observe `sizing_overrides` that failed the first arm.
- Profit-lock controller + defaults: no in-pack path injects 100/25/50 without an explicit provider contract / identity change.
- Staging (`cohort_profile_stage.py`): forces observe, disables live flags, clears `transition_approval`, fingerprint-checks round-trip.
- `AGENTS.md` `SRS_HV1_NO_GATES`: aligns with option B (no implicit profit/drawdown abort gates).
- Approval: live transition approved; scopes include option B, TSLA add, post-approval correction; fingerprint `c8938787268cfa94fd6c92026c191985a11c0225325452f415787b23fe6cb841`.

## Suggested fix order

1. **Supervisor exit codes** — validation / runner config errors → exit 2; confirm no auto-restart on 2; keep pre-arm runtime validation check (High ops).
2. **Observe-only size footgun** — cut HYPE/ETH/SPCX envelopes or enforce observe ceilings in validate_runtime; refresh fingerprint/approval if TOML changes (High).
3. **BTC asset `stop_bps` 80 → 60** (or equality assert) (Medium).
4. **Doc supersession banners** on profit-protection plan/readiness (Medium process).
5. **Brent 20/10** — explicit accept or observe until evidenced (Medium research).
6. **Disk hygiene** — HANDOFF ~97% full / ~900 MB bundles per start; prune aborted prestarts (High ops, outside pack, live-threatening).
