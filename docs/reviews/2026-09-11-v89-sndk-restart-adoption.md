# V89 stopped SNDK lifecycle: offline adoption evidence

At 16:06:40 UTC on September 11, the installed engine restored the exact stopped
SNDK lifecycle in an offline replay. It retained entry OID `542326864971`, stop
OID `542326955281`, signed size `-0.306`, original entry clock
`1789135200000`, no target, and the complete persisted execution plan. The
adapter received only mocked `preflight` and `reconcile` calls. It did not
submit, cancel, close or configure leverage.

Technical confidence is high for this bounded engine-startup result. It does
not prove a live launcher restart, current market eligibility, future transport
behavior or continuing strategy exits. A changed position, order or profile
identity would invalidate applying this capture to a later recovery boundary.

The replay used all **22,569 exact-profile records** selected while validating
the original SNDK ledger through the installed reader. The original ledger's
SHA-256 before and after was
`41a941368e3e2f161ea0d3464caba1d884ac51173c5d5cd47cf9cdfe0eeb0907`.
The production append method was overridden only in a research subclass to
write simulated events into the experiment directory. The real history, path
and profile fingerprint remained intact. No signing credentials were loaded.
All venue access was mocked and HTTP requests were explicitly forbidden.

Native account, position, stop and fills came from the authenticated unsigned
15:52:43 UTC snapshot. Installed symbol-aware parsers produced the reconciliation
objects. Preflight market precision and fee metadata were explicitly synthetic;
those values are not claimed as fresh venue evidence. The initial replay failed
because the synthetic preflight lacked mandatory HIP-3 fee metadata. Its
operator, error log and simulated output were preserved. Adding the missing
fixture metadata allowed the rerun to finish with exit code zero; production
code was unchanged.

Seven altered cases were rejected by the installed pure startup reconciler:

| Alteration | Observed rejection |
| --- | --- |
| Different profile fingerprint | Exposure without local ownership |
| Missing owned stop | Exact stop OID missing |
| Position size -0.305 instead of -0.306 | Position size mismatch |
| Stop size 0.305 instead of 0.306 | Stop size mismatch |
| Sell stop for the short | Stop side mismatch |
| Stop not reduce-only | Owned stop is not a reduce-only trigger |
| Additional order | Unknown additional order |

These are reconciler-level negative cases, not seven full launcher invocations.
The positive case exercised actual engine startup. Separately, **22 existing
offline reconciliation/restart tests passed**, including protected ownership,
foreign-profile refusal before mutation, execution-plan retention and target
bracket restoration. The experiment operator passes Ruff and contains 227 lines,
with a maximum of 49 lines per function. No new production feature or test
coverage percentage is claimed.

The restored plan retains `hourly_donchian_20_10_atr20_bidirectional_v1`, taker IOC
entry, structural stop anchor 1673.1726065095456, configured 20–250 bps clamp,
no target, 86,400-second fixed hold and `provider_recipe_exit_policy=honor`.
The existing native stop remains the venue order; recovery did not recompute
or replace it. The original entry clock was not reset by the replay.

A subsequent unsigned check completed **16:07:50 UTC / 12:07 Eastern**: core
remained flat/order-free; XYZ still had the **0.306 SNDK short at 10x isolated**
and its exact full-size reduce-only buy Stop Market at **1669.9**, status open.
Marked unrealized PnL was -$3.4272 at that capture. It is not a closed result.
The seven original ledger terminals remain `STOPPED / operator_stop`, and the
original trading/TUI processes remain absent. Strategy-managed exits remain
stopped. Native reads are sequential snapshots, not continuous protection proof.

The earlier stop-intent clarification and optional source-only installation
decision for [the latency candidate](2026-09-11-v89-entry-latency.md) remain
pending. This replay grants no restart or financial authority. No source,
profile, leverage, position, order, TUI or runtime process was changed. Both
prospective hypothetical outcome studies remain sealed.

Evidence is retained at
`data/logs/research/bidirectional_cohort/v89_sndk_restart_adoption_20260911_v1`:
the predeclared plan, original and corrected operators, full selected history,
simulated events, native receipts, outcome, regression log, verification and
checksum manifest. The simulated events retain engine-authored live-mode fields
but are isolated research output with no execution authority or runtime consumer.

Next: audit stop-to-restart fill/funding continuity against the frozen ledger
and unsigned post-stop venue records. Engine ownership restoration is now
supported; accounting continuity and fresh whole-launcher preflight remain
separate requirements for a concrete authorized recovery. A future restart must
refresh position/stop truth and preserve the original lifecycle identity. A
position closed by its stop during downtime requires the corresponding filled
stop recovery path rather than assuming this open-position snapshot still holds.
