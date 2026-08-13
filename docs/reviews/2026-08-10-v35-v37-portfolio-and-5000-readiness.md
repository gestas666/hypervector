# v35–v37 portfolio, strategy, regime, and $5,000 readiness review

> Superseded for current runtime, roster, and sizing facts by
> `2026-08-10-live-v38-and-5000-readiness-update.md`. This file preserves the
> earlier review history; its nine-asset sizing tables and stopped-backend state
> must not be used for current decisions.

## 1. Problem restatement

The system must provide one accurate read-only TUI over backend truth, preserve the
current approximately $500 research configuration, stage the evidence-selected v36
strategy roster, and prepare a separate $5,000 sizing candidate without silently
arming or restarting live execution.

Success means:

- active and staged configuration identities remain distinguishable;
- all nine configured assets, routes, positions, trades, costs, and regimes remain
  visible without fabricated fallback data;
- strategy changes are traceable to evidence and explicit user authority;
- the $5,000 candidate uses percentage sizing with venue leverage limits;
- only technical failures block execution; performance remains a reported result;
- current venue position/order state is reconciled before any live transition.

## 2. Explicit assumptions and known facts

### Evidence identity

| Artifact | SHA-256 |
|---|---|
| v35 live audit | `08b69d85d3a7976afed73d58ba0fcda9c2dc1b2514c040c52a9a829ea103492c` |
| v35 config | `4b5b35b2045e5c600a6acd4c7365e9acc771ee6074b18b5e7d30268ba17432cc` |
| staged v36 config | `1356bff0aa67e2b8a2acaf6361ea2e71afc4e935a55a11e8ad591be01a4ae9f3` |
| v37 $5,000 candidate | `7f92cd9f249a16262049a5ac8881ef3c181ba47c9e696deddae7636a14ed1da2` |
| 3% sizing stress | `137614965f85190ac6b0b4c69ba6d4ab3473c707c05fa01a2f4075185ce5b4cb` |
| 5% sizing stress | `eda5c7af30acaa3b954a9e39fea1160e1ccebd533fb84809e8b848056e3f28c7` |
| 7% sizing stress | `ec69218ee6d021fda75c557b19b4201fc662d1dfa3a20a0bc7b7dda53bb67776` |

The latest checkpoint was generated at `2026-08-10T21:22:19.663243Z`.
It reports fresh public venue valuation but a stopped v35 execution ledger:

- portfolio value: `$507.68523369`;
- execution collateral: `$504.69526449`;
- non-USDC spot: `$2.98996920` of AAPL;
- v35 runtime fingerprint: `8acc70105f8254dc6a7a3f690cebbaec8b3b81c94547d11b895eb6bbe03a24c4`;
- staged v36 fingerprint: `e472701ef9c386de7b68afcf28679f940ee4e00f1c4f8949c076a0576c0be522`;
- lifecycle: `stale_running_heartbeat_after_asset_stop`;
- generation: `stale_runtime_configuration`;
- transition blocker: `xyz:GOLD`.

High confidence: these values are directly serialized in the checkpoint. They are
falsified or superseded by a newer checkpoint or current authenticated venue
inventory.

### Evidence comparability

The 47 historical closed lifecycles are descriptive, not a v35/v36 expectancy
sample:

- 42 are incompatible with the exact v35 execution contract;
- five are not fully verifiable;
- zero are exact-profile compatible;
- the final v35 run had zero closed trades, 578 evaluations, and zero routed actions.

High confidence: the compatibility audit binds the source ledgers and profile
identities. The conclusion changes only if an audit defect is reproduced or exact
v36/v37 forward trades arrive.

## 3. Analysis and reasoning

### Closed portfolio performance

| Scope | Trades | W/L | Net USD | PF | Net excluding largest winner |
|---|---:|---:|---:|---:|---:|
| Mixed historical archive | 47 | 23/24 | +0.9974 | 1.1035 | -1.0568 |

Additional mixed-history facts:

- fees: `$1.7193`;
- funding: `+$0.0578`;
- median trade: `-$0.0034`;
- median return on margin: `-0.0701%`;
- closed-sequence maximum drawdown: `-$4.6849`;
- largest winner: BRENTOIL `+$2.0542`.

Medium confidence for accounting, low confidence for future expectancy. The
accounting is falsified by fill/fee/funding reconciliation errors. The expectancy
interpretation is updated only by exact-policy forward evidence.

### Strategy results and staged changes

| Strategy | Mixed trades | W/L | Net USD | PF | v36 action |
|---|---:|---:|---:|---:|---|
| Hulk Expansion | 5 | 4/1 | +1.4678 | 14.34 | Retain BTC/ETH/SOL/HYPE |
| HT-Breakout | 27 | 13/14 | -0.4513 | 0.920 | Retain BTC/ETH/SOL/HYPE |
| ETH Pullback | 2 | 1/1 | +0.0047 | 1.77 | Retain ETH |
| Source Follow | 5 | 3/2 | -0.1046 | 0.695 | Retain BTC |
| HIP3 Swing CMD | 4 | 1/3 | -0.0500 | 0.976 | Remove all routes |
| HIP3 Swing IDX | 3 | 1/2 | +0.3052 | 1.24 | Remove all routes |
| Range Onset | 1 | 0/1 | -0.1744 | 0 | Retain SOL only |
| HIP3 Breakout | mixed with HIP3 history | — | — | — | Retain all five HIP3 assets |

The v35-to-v36 diff makes only two roster changes:

1. HIP3 Swing is removed for SP500, SPCX, SNDK, GOLD, and BRENTOIL.
2. Range Onset is reduced from BTC/ETH/SOL/HYPE to SOL only.

This is explicit route selection, not a hidden performance gate. The user approved
the successor update. Strategy outcome metrics continue to be reported and cannot
automatically halt or reject trials.

#### HIP3 Swing CMD

It was addressed by removal, not by pretending the weak mixed sample could be
repaired with tuning. Its four CMD trades were 1W/3L and depended on one BRENTOIL
winner; the last v35 GOLD state also lacks canonical regime attribution. A new
Swing design may remain a research challenger, but the staged executable roster no
longer depends on it.

Confidence: medium. Falsifier: a point-in-time, venue-matched, walk-forward Swing
study or clean forward shadow/live evidence that remains positive without its
largest winner and resolves source/regime provenance.

#### Range Onset

Range Onset was not made artificially more frequent. It is retained only for SOL,
where its intended contract remains 1m bidirectional entry, 60 bps stop, no fixed
target, and 48-hour maximum hold. During the final v35 window every sampled Range
Onset readiness evaluation was ineligible, without a provider fault.

Confidence: medium that no runtime exception prevented signals in that bounded
window; low that its thresholds are economically optimal. Falsifier: a completed
bar satisfies every serialized recipe condition but produces neither an intent nor
an explicit non-action record. That requires a provider parity defect fix, not a
threshold relaxation.

#### HT-Breakout exits

The staged contract uses an eight-hour soft hold, extension only while regime
support remains, and a 24-hour hard ceiling. Mixed historical HT-Breakout results:

- maximum-hold exits: 13 trades, 11 wins, `+$4.6815`;
- provider-native exits: 12 trades, 12 losses, `-$5.3815`;
- manual exits: two wins, `+$0.2487`.

The current provider recipe exit is therefore ignored by the backend, while the
bounded timer policy remains authoritative. Only three historical lifecycles were
eligible for the aligned extension counterfactual, so there is not enough evidence
for another exit revision.

Confidence: medium for keeping the already-staged policy, low for claiming edge.
Falsifier: exact-policy forward lifecycles show the timer extension consistently
loses more after friction than the ignored provider exit.

### Protective exits

Across mixed history:

| Exit family | Trades | W/L | Net USD |
|---|---:|---:|---:|
| Maximum hold | 20 | 15/5 | +6.2326 |
| Manual close | 3 | 3/0 | +2.3030 |
| Opposite intent | 2 | 0/2 | -0.3337 |
| Protective stop | 15 | 0/15 | -7.7325 |
| Restart stop | 2 | 0/2 | -0.9430 |
| Target | 5 | 5/0 | +1.4710 |

Losing stops do not by themselves prove the stops are wrong: their job is to bound
loss after a failed entry. Resolved post-stop directional closes averaged -5.14 bps
at 5m, -0.43 bps at 15m, +2.94 bps at 30m, and +2.69 bps at 60m. That is too small
and unstable relative to friction to justify removing or widening protection.

Recommendation: retain venue reduce-only stops and existing 60/75/80 bps provider
contracts. Confidence: medium. Falsifier: exact venue replay plus forward evidence
shows avoided reversals are consistently smaller than missed recoveries after fees,
slippage, funding, and gap risk.

### Regime detector

The regime engine is useful as market-structure telemetry and conflict arbitration,
not as a proven direction oracle:

- one-year venue evaluation: RANGE had lower absolute movement in 48/48 cells;
- magnitude/strength associated positively with movement in 48/48 cells;
- canonical directional state had 0/32 positive pseudo-holdout cells;
- gap quarantine preserved RANGE separation in 48/48 cells.

Mixed historical trade association:

- directionally supported: 33 trades, `-$0.3355`;
- mixed/transition: seven trades, `+$1.0777`;
- HIP3 regime unavailable: seven trades, `+$0.2552`;
- same-side BREAKOUT: 29 trades, `-$0.4466`.

Therefore v36 does not add a zero-size RANGE gate or directional regime sizing.
Regime remains visible, point-in-time, and report-only unless a provider explicitly
uses a documented regime-aware exit contract.

Confidence: high for the movement/range conclusion, low for direction prediction.
Falsifier: new untouched point-in-time windows show directional classification
consistently improves net results after friction without sample leakage.

### Missed-opportunity review

The final v35 run produced 268 provider observations and 227 unique directional
opportunities. Cost-clearing markouts remained weak:

| Horizon | Resolved | Cost-clearing | Mean after friction | Mean excluding largest |
|---|---:|---:|---:|---:|
| 5m | 205 | 34 | -10.39 bps | -10.91 bps |
| 15m | 165 | 33 | -7.16 bps | -8.15 bps |
| 30m | 103 | 25 | -3.90 bps | -5.39 bps |
| 60m | censored | — | — | — |

This argues against broadly loosening thresholds. It does not prove the current
thresholds are optimal because opportunity windows overlap and the fixed hurdle is
not fully venue-specific.

Confidence: medium. Falsifier: non-overlapping, venue-specific opportunity samples
become positive after fee, spread, impact, latency, and funding.

### ML and MU research

No machine-learning score has live execution authority in v36/v37. Metalabeling
remains observation/annotation. ML4T-style point-in-time and walk-forward practice
supports collecting comparable forward labels before promotion.

The report-only MU 15m breakout development track was economically positive but
technically unresolved: 43 of 56 selected lifecycles crossed incomplete mark paths,
only 13 resolved, validation/holdout remained closed, and no promotion occurred.
It is not in v36 or v37.

Confidence: high on the technical no-promotion outcome. Falsifier: a prospective MU
ledger proves exact candle/pressure parity and resolves every selected lifecycle's
mark path under the frozen provider identity.

Trade Oracle and ML4T notebook queries returned no cited sources. Their suggestions
are treated as hypotheses only. Technical identity/data/stop reconciliation checks
are useful; sample size, profit factor, drawdown, and model scores remain report
alerts rather than automatic gates. Suggested RANGE scaling was rejected because
current evidence establishes lower movement, not positive directional edge.

### $5,000 sizing analysis

The v37 candidate freezes 3% isolated margin per occupied asset at 5x, with a $750
notional ceiling. Nine assets use at most 27% margin; the tenth slot is capacity only
until another asset is qualified.

| Per-slot margin | Margin/slot | Notional/slot | 10-slot margin | p90 stop wave | p99 stop wave | Five p90 waves |
|---:|---:|---:|---:|---:|---:|---:|
| 3% | $150 | $750 | 30% | 1.495% | 1.564% | 7.477% |
| 5% | $250 | $1,250 | 50% | 2.496% | 2.625% | 12.482% |
| 7% | $350 | $1,750 | 70% | 3.499% | 3.694% | 17.497% |

The 3% candidate is the recommended first $5,000 sizing experiment because it
preserves meaningful scaling while leaving more isolated-margin headroom than the
5% and 7% alternatives. This is a risk trade-off, not a profit forecast.

Observed p99 modeled loss for one $750 stopped position ranged from `$6.34` for
SP500 to `$10.29` for BRENTOIL. The depth evidence was complete for the sampled
notional, except SNDK at 99.993% completeness. Crypto evidence contains 113 recent
book samples per asset; HIP3 evidence uses historical 0xarchive windows.

Confidence: medium for relative 3% versus 5%/7% stress, low for realized joint-loss
probability. Falsifiers include live IOC slippage above the modeled tail, stop gaps,
correlated waves worse than deterministic aggregation, or per-asset capacity decay.

## 4. Uncertainties, risks, and failure modes

1. The backend is stopped; timed exits and telemetry are not active.
2. The stale ledger reports a GOLD long and venue stop, but current authenticated
   venue position/order truth has not been re-verified in this review.
3. BRENTOIL is flat in the latest execution checkpoint; no close is needed.
4. v36 has zero exact-policy closed trades, so its expectancy is unknown.
5. The 47 historical trades mix profiles and cannot validate v36 or v37.
6. HIP3 fee evidence varies by asset; GOLD uses an observed fill-derived rate while
   other HIP3 assets use roster fee evidence. Future fee-tier changes can invalidate
   the friction model.
7. Visible books exclude queue position, cancellations, latency, adverse selection,
   and stop gaps.
8. Funding was held constant for 24 hours as sensitivity, not forecast.
9. The tenth position slot is not a tenth executable asset.
10. A percentage config scales until its `$750` ceiling; it is not unlimited dynamic
    sizing.

## 5. Validation and experimentation plan

### Required before any live restart

1. Query authenticated current venue positions and owned open orders.
2. Reconcile GOLD position, protective stop identity, size, side, and reduce-only
   coverage; fail closed on disagreement.
3. Require the backend to be flat with no owned orders before switching v35 to v36.
4. Launch v36 only with explicit live flags and record its new run/profile hashes.
5. Verify all 16 provider-symbol routes, nine assets, one-position-per-asset rule,
   and 10-position portfolio limit in the first checkpoint.
6. Confirm the TUI shows v36 as runtime rather than staged and denies manual commands
   whenever the heartbeat or identity is stale.

### Forward measurement

- reconcile every entry/exit with venue fills, fees, funding, stop orders, and marks;
- record eligible, ineligible, routed, withheld, duplicate, stale, and fault outcomes;
- score missed opportunities with venue-specific friction and non-overlap slices;
- report strategy/asset/side/regime results with and without the largest winner;
- record planned versus realized notional and slippage at each sizing level;
- keep performance and sample-size thresholds informational under
  `SRS_HV1_NO_GATES`.

### $5,000 progression

The v37 file is a non-activated candidate. A live transition requires a separate
explicit user authorization after v36 venue reconciliation and a preflight against
the actual funded balance. Start with the 3% contract; 5% or 7% requires new depth,
fee, funding, and correlated-wave evidence rather than an automatic escalation.

## 6. Recommendations and trade-offs

| Option | Benefit | Main risk | Recommendation |
|---|---|---|---|
| Keep stopped v35 | No transition risk | Obsolete roster; no data collection | No |
| Start v36 at current bankroll | Clean roster; new compatible evidence | GOLD must first reconcile; expectancy unknown | Yes, after technical preflight and explicit arm |
| Activate v37 now | Immediate scale preparation | Wrong bankroll/current stale state; no v36 forward sample | No |
| Prepare v37 but leave inactive | Locks percentage sizing and testable identity | Does not itself collect evidence | Yes |
| Use 5%/7% per slot | Larger profit/loss response | Less headroom; larger correlated stop waves | Not yet |
| Remove/widen stops | Fewer stopped recoveries | Larger gap/liquidation exposure | No current evidence |
| Make regime a trade gate | Fewer conflicting entries | Directional regime has no validated edge | No |
| Keep regime as telemetry/conflict context | Preserves information without hidden gating | Does not solve entry edge | Yes |

Recommended sequence:

1. Use the repaired TUI in monitor mode now.
2. Reconcile GOLD current venue truth.
3. When flat/no-owned-orders, explicitly arm staged v36 at the current bankroll.
4. Collect exact v36 forward evidence.
5. Re-run capacity/friction with current books and the actual `$5,000` balance.
6. Explicitly promote the already-prepared v37 3% candidate only after that technical
   preflight.

## 7. Current command and human decision boundary

Read-only TUI command:

```bash
cd /Users/gestas/Prototypes/hypervector
uv run python scripts/multi_asset_bidirectional_canary_tui.py \
  --mode monitor \
  --config configs/multi_asset_bidirectional_all_live_canary_v35.toml \
  --staged-config configs/multi_asset_bidirectional_evidence_roster_canary_v36.toml
```

The TUI does not start or arm the backend in monitor mode. It displays active v35
and staged v36 separately. The v37 `$5,000` candidate is intentionally not passed to
this command and is not referenced by a launcher or runtime checkpoint.

The next human decision is whether to authorize current-venue GOLD reconciliation
and, only when flat/no-owned-orders is proven, a v36 live restart. That decision is
separate from later v37/$5,000 activation.
