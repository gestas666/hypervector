# Typed native routing in the research account

The typed integration replaces the process-local diagnostic at the actual account
routing boundary. Frozen research source is `585b484747b33acd948bff5c38f090f896e58418`.
Confidence is high in the verified synthetic compatibility and low in any inference
about historical or future profitability. No live implementation was deployed.

It retains complete scheduled provider batches, source-age withholding, native
canonical availability, conditional opening-price proxies and their original
clocks. Native controllers receive the actual accepted position quantities,
opening times and original intent anchors. Native entry admission and ranks drive
account proposals; configured close prices drive account exits only after exact
reconciliation with the original modeled scope, price and cost. The original
account path remains available for paired controls.

Controller decisions and the exact positions used for routing publish only with a
successful account transition. A failed account commit leaves account, lifecycle,
risk and routing state unchanged. Missing sources, altered terms, skipped frames
and inconsistent action joins fail explicitly.

Validation includes 341 passing tests in both worktree and authenticated archive.
The focused 328-test coverage run measures 98.46% statement and 92.5% branch
coverage, 97.21% combined. The account coordinator and native journal state each
measure 100%. All 19 changed Python files meet the checked line and annotation
limits; formatting and lint checks pass.

All 96 one-hour synthetic account artifacts reproduce byte-for-byte from the
archive and match the preceding diagnostic's account results. All 2,880 native
cycles match its actions, occupied quantities and complete controller payloads.
Independent Decimal checks total 5,328, with maximum absolute error 5.4650e-13.
Four deliberately changed action/quantity/payload/clock records are rejected.
The 24 seven-slot account paths remain exactly unchanged; all 24 two-slot controls
retain native withholding where the earlier account admitted a replacement.

Separate complete two-day source tests cover HYPE's 8-hour soft exit without directional support,
24-hour supported hard exit, both modeled exit clocks and seven open terminal
positions with independent marked equity. A gapped HYPE stop exposed an omitted
`protective_stop` label in the initial adapter; the corrected implementation
preserves its precedence and deferred timestamp with or without an opposite exit.
The independent terminal reference also needed the actual entry order: XYZ enters
14 minutes before the last crypto bars, so its fees affect later sizing.

UNKNOWN at a HYPE soft boundary remains an explicit unsupported state in the
frozen research assessment. Both account paths reject it without partial mutation.
This is a retained limitation, not complete native/research holding-policy parity.
Conditional candle opens are not observed executable quotes. Full native transport,
historical receipt timing, changed-size execution and historical dynamic account
returns remain unqualified. Both prospective outcome seals remain intact.

The next investigation is historical source-gap handling. Authenticated native
account-window grids omit BTC 18, ETH 20, SOL 19 and HYPE 19 minute bars in each
first/last variant. XYZ has all 4,608 quarter bars per asset in the account window,
but lacks 1,152 quarters of nominal warmup. The initial grid probe rejected a
mutable legacy indicator hash; the successful probe uses the completed immutable
XYZ archive and leaves that mutable tree untouched.

Preserve all 48 days and every original source/cost/clock/allocation axis. Identify
recoverable source evidence or explicit unobservable intervals before assembling
historical account phases. Do not fill gaps silently, substitute completed fixed
lifecycles, or infer unchanged historical profit from the synthetic controls.
Source identity changes, unexplained account drift, lost evidence, premature exits
or failed independent/archive reconciliation would falsify the relevant claims.

Evidence and the append-only decision are in
[journal revision 2](../research-journal/v89-native-account-routing-20260909-v2.json).
The complete integration plan remains
[here](../plans/2026-09-09-v89-native-account-routing-integration.md).

The next historical assembly work is specified in the
[source-gap plan](../plans/2026-09-09-v89-historical-account-source-gaps.md).
