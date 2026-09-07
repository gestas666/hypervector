# V89 operator-run live launch package

The operator requested the live execution command and correction of missing TUI
panes/data. This records that request for the exact additive V89 configuration;
execution remains subject to the operator invoking both live-arm flags.
The approval timestamp is the time this request was recorded, not a verified
message-delivery timestamp. No live backend is started by preparing this package.

The separate live configuration preserves the frozen research configuration and
adds only the transition-approval reference. It retains BTC long, ETH long,
SOL short and HYPE long with their V88 contracts. It adds bidirectional
`xyz:SPCX` hourly band recovery, `xyz:SNDK` hourly 20/10 channels, and
`xyz:BRENTOIL` hourly 8/4 channels. Capacity is seven positions, one per asset.
Each new route uses 10x isolated leverage, 2% margin, a $500 notional cap,
ATR20 x2 stop anchors clamped to 20–250 bps, no fixed target, recipe exits,
and a 24-hour maximum hold. Fifteen-minute source bars form completed-hour
signals; entries retain the 30-second freshness contract.

High confidence in configuration equivalence is conditional on the automated
contract comparison. Profitability remains low confidence: the 48-day pooled
new-asset replay has 160 trades, 41.875% wins and $197.50 adverse-cost net;
net excluding the three largest wins is -$30.73. SNDK loses on the extension
window, BRENT loses under the full-fee scenario, and no pristine out-of-sample
or fully joint seven-asset portfolio result establishes a reliable live edge.
See the immutable frequency/noncrypto research review for source boundaries,
selection bias, stop/liquidation ambiguity and remaining startup ATR concerns.

The startup contract retains a verified prestart backup, exact previous-run
flat-boundary archive, approval fingerprint/hash validation, and fresh venue
position/order reconciliation. These are technical checks, not profit thresholds.
The legacy archive records a historical stopped boundary; it does not establish
current venue flatness. Read-only preflight and operator startup recheck that.

Rollback source remains at `backup/pre-v89-tui-update-20260907`; V88 configuration
is unchanged. A live rollback requires its own exact stopped/flat transition and
operator-run command. This document itself grants no order authority.
