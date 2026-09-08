# Inactive equal-cap proposal and configuration round-trip correction

Research/proposal authority only. No live source deployment, active configuration
write, strategy/route/parameter change, arming, orders or trading/reporter process
lifecycle action. Preserve the September 8–22 prospective seal.

The equal-cap quote study is complete and registered as revision
`608a4824c0a25588b1439ad19cee93ffbc366270e906c1db0afb6c492690c962`,
source-record SHA-256
`62443f8bd1fac1fe241c4fe7149c8bc27307046b3c187fce39c950345f1564b6`.
Its complete current snapshot capacity does not establish future profitability.

## Newly observed technical defect

Before preparing a candidate file, the existing pure `_toml` serializer was
tested with the unchanged V89 configuration. It writes BTC provider sides as
long/short instead of long-only; the observe-mode loader then rejects the file
for violating the exact liquidity-sweep long contract. It also omits all seven
explicit 0.002 entry-slippage values. If the direction error alone were repaired,
those omissions would select the configured legacy 0.01 fallback instead.

Main and research copies of `cohort_profile_stage.py` match SHA-256
`14a6a769dbaeef19a56405dae12d4bf515f50b540c4bebe081659a5337508ca7`.
This is a reproduced staging failure, not evidence of changed live orders or
the cause of the current stopped processes. The loader's rejection is observed;
actual live impact is unestablished. Confidence is high in this bounded defect.

Evidence:
`data/logs/research/bidirectional_cohort/v89_equal_cap_inactive_proposal_20260908_v1/existing_serializer_roundtrip.{toml,json}`.
No staging entry point was invoked; only pure serialization and observe parsing
were used. A bounded ledger ID search found no prior staging/serialization
hypothesis; this does not prove no related issue exists under another name.

## Work and validation

1. Add failing regressions for the exact V89 round trip, narrow asset/provider
   sides, and distinct entry/market slippage. Preserve provider direction and
   sizing overrides and verify the original source bytes remain unchanged.
2. Prepare the smallest serializer correction in the isolated research worktree.
   Do not deploy it. Reuse the existing serializer after qualification instead
   of writing another TOML generator. Keep the omission of stale transition
   approval explicit in the inactive candidate; do not copy old authorization.
3. Generate the exact fixed equal-cap proposal with the previously tested margin
   fractions, unchanged leverage/routes/exits, an explicitly inactive identity
   and separate research ledger/stop paths. Load in observe mode without live
   flags. Compare all typed configuration fields against an allowlist of intended
   allocation, identity and research-path differences. No outcome-fitted weights.
4. Freeze an independently reviewable prospective comparison specification. Its
   start/end and minimum source/timing evidence must be settled before observation;
   do not label a merely planned study as running or newly independent history.
   Preserve the existing seal and original allocation controls. Technical source
   failures are reported; adverse performance remains a result, not an implicit
   abort gate or automatic promotion rule.
5. Report the concrete upside/drawdown/exposure/cost evidence, remaining execution
   and prospective uncertainties, success measurements and rollback boundaries.
   Validate focused regressions, full candidate semantic parity, source hashes
   and a frozen-source reproduction. Journal the defect and inactive proposal.

The allocation proposal is reviewable only when the exact file and its semantic
diff pass. Live deployment remains a distinct human decision. Research activity
already has authority; do not add a redundant permission request for it.
