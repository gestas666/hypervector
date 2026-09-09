# Source-bound provider exits and regime evidence

Research source `751549283f5c309181c5dd23dcd83e89b509c505` preserves the
position sides named by a provider recipe exit and binds completed decisions to
their exact selected and first candle observations. The affected offline suite
passes 1,148 tests in the worktree and again from the committed source archive.
Confidence is high within the tested synthetic/component scope, and low for
future returns. This is not a live deployment or a demonstrated profitability fix.

## Reproduced fault and correction

The prior portfolio completion object retained the recipe reason but had no side
scope. After introducing that field, two regression cases showed the unchanged
dispatcher closing an ETH long and SOL short even though the supplied recipe
targeted the other side. Both fail with an unexpected closed account position.
Dispatch now supplies the recipe only when it applies to the owned position side.
The legacy explicitly unscoped synthetic API remains compatible; source binding
supplies an explicit immutable side set, including an empty set when no exit was
emitted. The full provider payload also remains in pending decision evidence.

The new binder consumes the original provider batch, independently of admitted
entries. A stale ETH entry does not expire its recipe exit. The real HYPE
alignment translator produces a short-side evaluation with no permitted short
entry but with long-position exit authority; the bound completion schedules the
existing long's opposite-strategy exit. An ineligible hold row that merely names
a short side does not become an opposite signal.

Provider batches now retain the exact selected and first completed candle, not
only receipt timestamps and the source variant. The completion join rejects
different source identities, clocks, variants, duplicate or mutable outputs,
wrong strategy/symbol attribution, malformed boundaries and invented native
canonical availability. It preserves complete provider/canonical payloads and
explicitly marks an absent provider evaluation unavailable. No entry deadline,
sizing, leverage, holding limit, cost or original regime formula was changed.

## Regime limitations

The production structural direction is a string accepting long, short or neutral;
a missing evaluation side does not establish missing structural direction. Neutral
structure and unavailable structure remain distinct. The projection retains
provider primary, 1m, 5m and 15m fields separately, including `None` or `UNKNOWN`,
without fabricating canonical observations for the native 15m XYZ source.

The frozen historical HYPE support helper uses its original 5m-based weighting;
it is not interchangeable with the production elapsed-time helper. Its rejection
of `UNKNOWN` remains explicit and tested. Complete historical provider/regime
parity, unavailable-evidence policy compatibility, source-backed calendar assembly
and the full frozen 24-cell evaluator remain unqualified. Neither prospective
experiment's signals, trades, account values or returns were evaluated.

## Verification and next action

Forty-four new tests cover the completion and exit-scope behavior. Across four
changed research modules, unit coverage is 320/320 statements and 116/116 branches.
The broader worktree run reported twelve unclosed-SQLite ResourceWarnings during
source tests; these are unresolved. The archive run passes without reported
warnings. All eight changed files pass Ruff, formatting, function/file size,
annotation and public-docstring checks.

Archive SHA256 is `b8253ecd26b079bda9df271386aa154ed9219696fedacedb3eb66a29c1d61844`,
31,048,115 bytes. All 5,352 Git blobs match; four critical imports resolve inside
the archive and eight source hashes remain exact after testing. Reproduction uses
the same Python/dependency environment and the registered external test inputs.

At September 9 07:05:29 UTC both public collectors were alive, with no reported
collector error; all fifteen seven-asset and eleven SNDK/Brent source pins match.
No matching local trading backend or TUI was found. Both live-profile copies match
the prior hash. This process/configuration observation does not refresh the venue
account. No live code, process, order, profile, TUI or authority was changed.

Next, assemble these completed decisions with source-bound entries and native
funding into complete calendar bars, then compare full historical provider/regime
output with the original models. A dropped or wrong-side exit, substituted source
or clock, invented regime value, changed historical formula or failed independent
replay invalidates the corresponding component qualification. Keep the September
22 and September 23 prospective outcome seals intact.

Evidence: the original repository's
`data/logs/research/bidirectional_cohort/v89_provider_completion_binding_20260909_v1/`.
