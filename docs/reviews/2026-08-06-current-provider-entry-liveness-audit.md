# Current Provider Entry-Liveness Audit

**Observed:** 2026-08-06 09:48 UTC  
**Live run:** `bidirectional-live-1785976389611`  
**Active profile:** `multi_asset_bidirectional_evidence_routed_hype75_eth_observer_v11`  
**Profile fingerprint:** `9f0f53d5c3c75bcec36a8b29c75d93146d686dbd46e90d25ef5ef400b8df685c`  
**Execution effect of this audit:** none

## 1. Problem restatement

Determine whether the current portfolio's non-HYPE strategies are disconnected,
unable to form entries because of defects, excessively constrained for the
desired trading cadence, or correctly producing signals that the explicit live
routing scope withholds.

Success criteria for this audit are:

- every configured provider-symbol receives fresh completed-bar evaluations;
- eligible signals become attributed intents;
- execution-authorized intents reach the router;
- observer intents remain recorded with an explicit withholding reason;
- entry scarcity is separated from historical expectancy;
- the approved HYPE v1 implementation and live process remain unchanged.

## 2. Known facts and provenance

The authoritative checkpoint was
`data/runtime/bidirectional_cohort/latest_checkpoint.json`. At observation time
the backend was `running_consistent`, had no faulted assets, and had one protected
HYPE short. The profile contained 14 provider-symbol mappings, of which only two
had automatic order authority:

- `hype_breakout_onset_bidirectional_v1|HYPE`;
- `hulk_expansion_bidirectional_tuned_v2|BTC`.

All other mappings were observer-only. The run had seven eligible strategy
intents: two became HYPE entry actions, four were explicitly withheld as
`provider_symbol_observe_only`, and one was withheld because a same-direction
HYPE position was already open.

Focused provider, poller, configuration, and observe-only routing validation
passed 54/54 tests. The staged ETH-canary configuration and transition controls
passed another 17/17 tests. These tests validate deterministic logic and routing;
they do not establish market edge.

## 3. Current-run entry audit

The current run covers about 9.2 hours. A one-minute provider has 555 completed
evaluations, the five-minute source-follow provider has 112, and the 30-minute
Hulk provider has 19.

| Provider / symbol | Scope | Evaluations | Eligible | Operational verdict |
|---|---|---:|---:|---|
| HYPE breakout / HYPE | live | 555 | 3 | Working; two actions and one same-position hold |
| HYPE breakout / BTC | observe | 555 | 1 | Working; order withheld only by routing scope |
| HYPE breakout / ETH | observe | 555 | 1 | Working; order withheld only by routing scope |
| HYPE breakout / SOL | observe | 555 | 1 | Working; order withheld only by routing scope |
| ETH compression/pullback / ETH | observe | 555 | 1 | Working; its only canonical ETH onset passed both added conditions |
| Hulk expansion / BTC | live | 19 | 0 | Data path works; exact expansion setup did not occur |
| Hulk expansion / ETH | observe | 19 | 0 | Data path works; no exact expansion setup |
| Hulk expansion / HYPE | observe | 19 | 0 | Data path works; no squeeze release despite high displayed readiness |
| Hulk expansion / SOL | observe | 19 | 0 | Data path works; no exact expansion setup |
| Source-follow / BTC | observe | 112 | 0 | Data path works; current setup conditions absent |
| Range onset / BTC | observe | 555 | 0 | No hourly SMA10/30 cross |
| Range onset / ETH | observe | 555 | 0 | No hourly SMA10/30 cross |
| Range onset / HYPE | observe | 555 | 0 | No fresh cross; most 5m states also not admitted |
| Range onset / SOL | observe | 555 | 0 | No fresh cross; most 5m states also not admitted |

The cross-asset breakout statement therefore needs precision: the rule is
already **evaluated** on all four assets, but the current configuration and
configuration validator permit this provider to **execute** on HYPE only.

## 4. Strategy-by-strategy reasoning

### HYPE breakout onset

This is not over-constrained in code. Eligibility requires a fresh completed 5m
`BREAKOUT` transition and a non-neutral completed-hour SMA10/SMA30 structural
direction. It produced eligible events on all four assets during this run.

Blindly enabling the unchanged rule on every asset is not supported by the
existing historical transfer test. Under modeled fees, slippage, funding, an
80-bps stop, and fixed eight-hour exit, ETH and SOL were negative in both the
development and opened final-60-day blocks. BTC was negative in development and
positive only in the recent block, with the improvement entirely from shorts.

**Confidence:** high that cross-asset signal generation and withholding work;
medium that unchanged ETH/SOL transfer is economically weak; low that recent BTC
short performance is durable. Fresh reconciled outcomes with stable positive
after-cost results would update the economic assessment.

### ETH breakout compression/pullback

This provider adds two conditions to the canonical breakout onset: prior
15-minute BBWP minimum at or below 40 and a directional candle body at or below
zero. In this run those additions did not remove any canonical ETH entry: the
single canonical ETH onset passed both and became eligible.

The staged v12 profile grants this separate provider ETH execution at a $25
notional cap while preserving HYPE v1. Its historical selected shape produced
338 trades across a development-plus-opened-final-year window, about 0.93 per
day, with PF 1.1111 in development and PF 1.1208 in the opened final block. The
selection was multiple-tested and side leadership rotated, so this remains a
low-confidence canary candidate rather than an established edge.

**Confidence:** high that the provider is operational and not responsible for
the current lack of ETH orders; low that its thin historical edge survives live
friction. A provider mismatch, duplicate ETH position, missing venue stop, or
materially negative reconciled live sample would falsify canary readiness.

### Hulk expansion

The actual entry path is substantially narrower than its TUI readiness meter:

1. a wave cross, squeeze release, or Krown turn creates a candidate;
2. the runtime retains only the `hulk_rebuilt_expansion_v1` archetype;
3. `adx_usable` evidence must be present;
4. the evidence score must reach eight.

The readiness meter instead counts six contextual conditions and treats either
`squeeze_on` or `squeeze_release` as satisfying its squeeze row. Consequently a
display such as five-of-six ready does not mean the executable trigger is one
condition away. This is a telemetry semantics defect, not evidence that the
signal engine stopped.

The current bidirectional profile is also marked `failed_forward_diagnostic` in
the frozen research registry. It had positive development but negative
validation and pseudo-holdout results. Its roughly 2.3 trades/week historical
cadence is too sparse to serve as the portfolio's main active engine.

**Confidence:** high in the code-path mismatch between readiness and entry
semantics; high that the current mapping is operating; medium in the historical
economic rejection because bar replay cannot reproduce live fills. An exact
fresh expansion signal that fails to become an intent would falsify the
operational verdict.

### Source-follow BTC

This path requires a fresh primary regime onset, a directional primary label,
minimum classifier confidence, and a configured source-range interval. Current
blockers show all four conditions are changing and being evaluated. Its exact
deployed historical shape still generated about 2.1 trades/day, so its present
zero count is not primarily caused by excessive frequency filtering.

The larger issue is expectancy: the exact one-year replay reported 782 trades,
PF 0.6193, and negative results on both long and short sides after fees. Loosening
the onset rule in the existing one-blocker forward audit also remained negative
on three resolved cases.

**Confidence:** high that the provider is technically alive; medium that its
current entry/exit contract is economically unsuitable. A new causal contract
with prospectively positive after-cost evidence would constitute a different
hypothesis.

### Range onset

This rule waits for a completed hourly SMA10/SMA30 cross and then admits it only
when the 5m regime is `RANGE` or `BREAKOUT`. Zero entries in nine hours is normal
for this construction, not a transport defect. Historical cadence was about 1.5
trades/week for the accepted SOL evidence.

That makes it operationally too sparse for the user's repeated-edge objective.
Removing the hourly cross would change the mechanism into a different strategy,
not merely repair a gate. Earlier one-blocker BBO estimates looked favorable on
small BTC/HYPE/SOL long-only samples and unfavorable on ETH, but those samples
were overlapping, tiny, and report-only.

**Confidence:** high that range onset is live and sparse by design; low that a
cross-relaxed replacement has edge. Fresh bidirectional, non-overlapping,
after-cost evidence would be required to update that assessment.

## 5. Failure modes and trade-offs

| Option | Activity | Evidence | Main risk |
|---|---|---|---|
| Keep v11 unchanged | HYPE breakout plus sparse BTC Hulk | Preserves current approved observation | Portfolio remains mostly one-strategy |
| Enable unchanged breakout on all assets | Higher | ETH/SOL historical transfer rejected; BTC unstable | More trades from a negative or regime-sensitive rule |
| Move to staged v12 at a flat boundary | HYPE plus separate ETH candidate | Best current second-provider evidence; about 0.93 historical trades/day | Thin, multiple-tested edge may vanish live |
| Loosen Hulk/range/source gates in place | Higher | Only tiny or negative one-blocker evidence | Changes strategy identity and can add fee churn |
| Build separately named relaxed challengers | Measurable without corrupting originals | Preserves attribution and rollback | More engineering and forward observation time |

## 6. Recommendation

Do not mutate or restart the open HYPE v1 lifecycle. The smallest evidence-backed
portfolio expansion is the already staged v12 transition: retain HYPE v1 exactly
and add the separate bidirectional ETH compression/pullback canary at $25
notional, but only after the account is verified flat and the user explicitly
approves that profile.

Keep BTC/ETH/SOL exact breakout transfer in observation rather than silently
granting it live authority. Treat source-follow and range-onset as measured
negative/sparse controls, not primary profit engines. Correct Hulk readiness
semantics before relying on its visual "distance to entry"; any relaxed Hulk or
range variant must have a new strategy identity and independent journal.

No performance result in this report automatically pauses or rejects a trial.
It supplies evidence for the operator decision, consistent with the ungated
execution charter.

## 7. Staged telemetry correction

After this audit identified the Hulk readiness mismatch, a test-first,
telemetry-only correction was staged without restarting the live backend. The
regression reproduced an armed squeeze with no release being shown as `long`
and 5/6 ready. The corrected next-start behavior reports no entry side, 0/4
exact entry conditions, and these explicit blockers:

- expansion trigger absent;
- moderate-ADX evidence absent;
- signal score not eligible;
- entry side unavailable.

ADX, volume, flow, squeeze, EMA/Supertrend, and Heikin-Ashi context remain
visible as indicators and metrics, but they no longer masquerade as the entry
contract percentage. The TUI setup inspector now labels the exact percentage as
`ENTRY CONTRACT` and labels a fully eligible setup `ENTRY CONTRACT SATISFIED`.
It checks the backend-authored `hulk_expansion_moderate_adx_v1` contract marker
before using those labels. The currently running legacy payload therefore stays
labeled `SUPPORT COVERAGE`; rebuilding the TUI before the backend restarts cannot
misrepresent its contextual 5/6 score as an exact entry contract.

This change does not alter `_signal_disposition`, signal generation, order
routing, sizing, stops, exits, provider authority, or HYPE v1. The currently
running process still has the pre-change Python modules loaded; the correction
will become active only at a later approved restart.

## 8. Verification record

```text
146 passed: Hulk/provider/poller/readiness/routing Python regression set
full hypervector-tui test suite passed
focused test demonstrated red before green for the readiness defect
legacy/new backend telemetry-generation compatibility test demonstrated red before green
ruff and changed-file rustfmt checks passed
Clippy passed with two unrelated pre-existing lints explicitly allowed;
strict Clippy remains red only on those two unmodified lints
```

Current source/config identities:

```text
v11 config  2a118e64ee0254134809acdf07b13c1bf581bd77f56a73097367e9f4d637c70e
HYPE v1     3210a0f85d62a13ef8f5d99277d62ae02b496cea5200fbf897196365a48d270d
ETH provider 11f50718099be4282027a8370144312121db126ca42d821c247bc00c3bfae497
v12 staged  b6551b4a4188a64098e70a92f5abbb828d5a308b94f154938c5d709f78e0f386
Hulk readiness staged 8d8648122c6b9be51f644c393c927061bb79f89beeeee7c1883b60b547538d51
Hulk decisions staged 34fd7de00a937bbd64a77c468e937a3df297084464999815509685f8249627c1
TUI detail staged 471ad3eb9d5de6e0af2af8b28f3c8a24319d3d84fdc14082e9639160d3c6639f
```

No live configuration, process, position, execution authority, or loaded HYPE
strategy was changed. Only next-start Hulk/TUI telemetry source was staged.
