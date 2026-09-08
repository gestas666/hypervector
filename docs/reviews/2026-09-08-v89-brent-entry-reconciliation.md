# Brent entry: native execution and cost reconciliation

The Brent entry and its full-size protective stop agree between the frozen
ledger and individually timestamped venue responses. Confidence is high for
this bounded reconciliation. The quote available before submission was 8.01
seconds old, so the measured reference-to-fill price difference cannot be
identified as instantaneous execution impact. One open trade does not establish
representative friction, profitability, or a reason to change the live strategy.

## Identity, exposure and protection

Nine unsigned observations used the documented
[Hyperliquid Info endpoint](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint)
and its [perpetual account queries](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint/perpetuals).
Responses were received at 06:44:41–06:44:44 UTC on September 8. The capture
loaded only the public wallet identity into its account mapping; it constructed
no signer or execution client. Raw response bytes, HTTP status, timestamps,
headers and SHA-256 identities are retained. Requests are sequential and do
not constitute an atomic venue snapshot.

| Measurement | Observed value |
| --- | ---: |
| Entry time | 2026-09-08 06:00:24.073 UTC / 02:00:24.073 EDT |
| Entry order / trade | 538998955084 / 409406508647902 |
| Entry / quantity | 97.884 / 5.11 |
| Entry order type / limit | Filled IOC / 98.015 |
| Margin mode / leverage | Isolated / 10x; native maximum 20x |
| Protective stop order | 538999050017 |
| Native stop trigger / size | 96.982 / 5.11, reduce-only sell, Stop Market |
| Venue fill to stop-open interval | 3,306 ms, same venue clock |
| Local order intent to acknowledgement | 1,413.685 ms |
| Local entry acknowledgement to stop acknowledgement | 3,197.682 ms |
| Frozen post-stop reconciliations | 176; none missing or mismatching the stop |
| Funding settlements in the entry window | Zero in both native response and ledger |

The requested unrounded stop was 96.9819790001104; the native resting order
reported 96.982. Stop checks cover 06:00:29.392487 through 06:43:54.604297 UTC.
They do not prove continuous presence between samples or the eventual exit
price. The native position was still open at the capture. The 3.306-second
interval describes the observed initial protection gap; no configured
protection-latency deadline was established by this audit.

## Price and fee evidence

| Measurement | Observed value |
| --- | ---: |
| Strategy reference | 97.819 |
| Last pre-intent bid / ask | 97.821 / 97.824 |
| Quote age at local intent | 8,010.353 ms |
| Reference to quoted midpoint | +0.357804 bps |
| Midpoint to quoted ask | +0.153344 bps |
| Quoted ask to fill residual | +6.133778 bps |
| Total reference to fill | +6.644926 bps |
| Actual fee | $0.043216 / 0.86399645 bps |
| Current fee-metadata projection | 0.864 bps |
| Actual fee minus current projection | −$0.000000177536 |
| Historical model entry fee / slippage | 0.9 bps / 2.5 bps |
| Observed slippage above model | +4.144926 bps / $0.2071862275 |

All three price components use the same strategy-reference denominator and
sum to the measured fill difference. The residual includes market movement
after the sampled quote; it is not a measured spread-only execution cost.
The fee projection uses the captured account rate, referral discount, growth
mode and deployer scale under the documented
[fee formula](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/fees).
It is a current metadata comparison, not historical metadata replay.

The requested $500 notional was sized at the strategy reference and rounded
down to the venue's two size decimals, yielding 5.11. Filled notional was
$500.18724 because the fill price exceeded the reference. This $0.18724
difference is explicitly retained rather than reporting the request as the
executed notional. Entry costs omit future exit fees, funding and slippage.

## Validation and remaining investigation

Source commit `0d7ed0d` contains the unsigned capture and offline acceptance
scripts in the isolated storage worktree. The existing price decomposition
helper is from `50f8e80`. The audit verifies complete ledger sequences and run
identity, the capture manifest, native response byte hashes, exact fill and
order fields, lot rounding, fees and all 176 stop checks. Twenty-one separately
corrupted fill/stop fields were rejected, including integer substitutions for
boolean flags. Ruff, source-size/function-size limits and diff whitespace
checks passed. No test contacted the venue; network access was confined to the
explicit unsigned evidence capture.

Artifacts under `data/logs/research/bidirectional_cohort/`:

- `v89_brent_entry_native_20260908_v1/`: frozen checkpoint, exact asset ledger
  prefix, nine native responses and capture manifest.
- `v89_brent_entry_acceptance_20260908_v1/`: reconciliation report and source
  integrity record.
- `v89_brent_entry_sources_0d7ed0d_20260908_v2.tar`: 141 verified project source
  files. The first archive attempt encountered the interactive `<stdin>` module;
  its partial archive is retained and excluded from acceptance.

The runner source reconciles venue state before polling provider candles and
routing intents. That ordering is consistent with quote aging, but the share
of the observed eight seconds attributable to each stage is not yet measured.
The highest-value next investigation is a timed offline cycle replay, grounded
in existing logs, to separate reconciliation, provider collection and submission
delays. No strategy, cost assumption, sizing, leverage, stop policy, or live
deployment changed. The reporting-storage proposal remains pending approval.

Falsifiers: changed source bytes, a mismatched native fill or stop, missing
protection in the frozen reconciliations, or a causal timing reconstruction
contradicting the quoted age invalidates the corresponding finding. Prospective
strategy outcomes remain separate and sealed until their predeclared block ends.
