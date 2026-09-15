# V89 independent monitor, leverage visibility and accounting scope

The corrected monitor is installed at `ab5647461f7cf29fe1f5bcdf2427b99b97738c50` from candidate `f719ee56f6d30d5c979dd811be018d8002406b41`. Its executable is `target/release/tui-regime-detector-v89-monitor-20260915`, SHA256 `09066c5c1c1e869866a7e339643b1fce7ab59e02e04dbbd670de4651ba8a9006`.

## Observed defects and repairs

1. Medium-width portfolio tables omitted leverage; the smallest layout exposed it only for the selected asset. Portfolio and trade rows now show `LEV C/V`, meaning configured/venue leverage. BTC configured at 20x while flat displays `20x/-`; the captured SNDK position displays `10x/10x`. An open position with missing venue leverage displays `N/A` rather than borrowing the configuration. Terminal spacing preserves full symbols, costs and stop identities. This changes display behavior only.
2. The rolling analysis labeled compatible-profile historical totals `RUN`. The Rust parser now retains execution scope: `PROFILE` for compatible history, `RUN` for explicit current-run data, and `SCOPE N/A` for absent or unknown scope. The current-run performance card retains its existing entry-origin accounting contract.
3. An existing combined TUI owns the financial backend. The explicit independent monitor owns only a separate reporter and TUI. It rebuilds native execution evidence and shares the active reporter's venue valuation, archive and research-sync sections. Publication rejects stale or mismatched sources and missing sections. It makes no network requests or database writes.
4. The full CLI unnecessarily loaded `.env` before independent mode selection, and the shared TUI resolver supplied a manual operator inbox. Independent mode now skips credential loading and removes the inbox. Live/observe authority flags are rejected. Other launch modes retain their existing behavior.
5. Reporter failure could leave terminal modes disturbed. Independent-monitor cleanup restores saved terminal attributes, leaves the alternate screen, reaps its own children and reports failure.

## Validation

- Reproduced missing leverage and wrong execution scope with failing wire/render tests. Explicit missing-venue cases prevent configuration substitution. A further failing spacing regression came from inspecting actual terminal cells.
- Final Rust suite: **650 passed, 23 ignored**, zero failures. The 23 ignored cases require their named historical/local runtime fixtures; they are not claimed as passing. Final release build passed.
- Candidate and installed Python launcher/checkpoint/lifecycle suite: **114 passed** each. Separate earlier coverage measured 91% of the new monitor modules before the final operator-inbox removal; it is historical coverage evidence, not a final coverage percentage.
- Actual installed executable rendered portfolio/trade views at **100×28, 120×36, 160×40 and 190×52**, using dated native evidence. These eight captures validate rendering, not live freshness.
- Actual installed independent monitoring then attached to new run `bidirectional-live-1789497016143`. All nine panes and the setup inspector opened; four additional portfolio sizes displayed leverage. Exact compatible history reconciled **19 fills/projected 19, eight closes, one open lifecycle, net −$25.609303**. These historical totals are descriptive, not expected returns.
- Normal exit returned 0. A second actual run deliberately terminated only its verified owned reporter and returned 2 with an actionable error. Both runs restored the original terminal attributes, reaped the reporter and preserved user PIDs **29190/29191/30603/62016/62017**. Validation denied network, credential reads, signing, financial/database writes and signals to protected session PIDs.
- Installation preserved **5,482 other protected files**, the existing binary and the current user startup process identities. The reverse source patch passes `git apply --reverse --check`. No financial process was started, stopped, restarted or signalled by this work.

## Current live evidence

The user restarted the session during this work. The earlier backend PID 93674 is terminal; current backend PID **30603** is user-owned, with supervisor **29191**, reporter **62016** and original TUI **62017**. The new pre-start manifest SHA256 is `9f20a7a850c2625c977c59ba7d292a9d9c1a09e56b5f71e73d7759445ae76029`; its 1,922-file implementation identity is `1f8ae4e910c9061b5a5bddb70b09e989b1c03c6dfa13e8842d8233830a0d06c3`. The current checkpoint reporter has loaded the preceding history correction and reports 19/19 fills.

The newly eligible SNDK short from 16:00 UTC reconciles to .326 at 1531.7, entry notional $499.3342 within the $500 configured cap and fee $0.043142. Entry dispatch age was 6.166 seconds against a 30-second deadline. The venue stop is a covering .326 reduce-only buy at 1561.5, about 194.555 bps above entry within the configured 20–250 bps range. Venue fill to observed stop acknowledgement was 4.563246 seconds; this is an observation, not a diagnosed contract violation.

The new native SNDK session recovered the exact entry OID **545845583477**, stop OID **545845630697** and short size **.326** at **18:41:39 UTC**. The captured new-run prefix through **18:47:25 UTC** contains 99 rows and no new order intents/acknowledgements/stop submissions. The captured cohort reports zero faults. This confirms adoption in that prefix; later receipts may update the position or protection state.

## Operator command

Run in another terminal while the existing combined session remains open:

```bash
cd /Users/gestas/Prototypes/hypervector
.venv/bin/python -m hypervector cohort-tui --mode monitor --independent-monitor \
  --config configs/multi_asset_growth_first_5000_noncrypto_live_v89.toml \
  --tui-bin target/release/tui-regime-detector-v89-monitor-20260915 \
  --tui-bin-sha256 09066c5c1c1e869866a7e339643b1fce7ab59e02e04dbbd670de4651ba8a9006
```

Quitting this independent monitor stops only its reporter/TUI. The original combined window still owns the backend, and its running TUI binary was not replaced. The versioned installation preserves that startup's pinned old executable/hash. Independent mode requires a fresh reporter bound to the active profile/run; it intentionally refuses stale or mismatched reporting inputs.

## Decision and limits

**Recommendation / why now:** accept the reproduced leverage, scope and lifecycle reporting repairs because they affect the operator's view of exposure and results. Applicable to all seven assets and market regimes; there is no new strategy rule.

**Alternatives:** restarting the combined session reloads its display but also controls the financial backend. A raw TUI against an old checkpoint cannot activate corrected reporting. The independent mode costs one additional local reporter and consumes existing external observations without issuing its own requests.

**Expected upside:** accurate leverage and historical loss attribution, accessible strategy/regime panes and a separately disposable monitor. No forecast profitability increase is claimed.

**Validation remaining / next investigation:** monitor the recovered SNDK lifecycle's exit/protection and reconcile its eventual fees/funding/net result; compare new eligible actions with their provider, regime and receipt evidence. Do not weaken entry rules from a short inactive interval or one trade. Broader research remains active under the original mandate.

**Success / falsifiers:** exact backend/display leverage and scope agreement, fresh same-run complete reporting and preserved backend ownership. Mismatched fills/costs, missing panes, clipped exposure/protection, incorrect missing-data substitution, a process leak or any authority escape reopens this repair. High confidence applies to the tested source, inputs, terminal sizes and observed native prefix. It does not establish universal bug freedom or strategy expectancy.

**Rollback:** previous overwritten source bytes, the 20-file source patch and manifests are under `data/logs/research/bidirectional_cohort/v89_independent_monitor_20260915_v1/installation/`. Verify the reverse patch before applying it. Remove only files recorded as newly created, and retain the prior executable, whose SHA256 remains `eada0b1359d6ea16e84dfb3d35b46538f95b6dd04cc1945f1a64d0614b5c3d9e`. Source rollback does not control running processes. Do not close the original combined TUI as a monitor rollback action.

**Approval:** the existing corrective-update authorization covers this reporting installation. No live strategy, sizing, leverage setting, risk parameter or financial execution behavior changed.

All supporting artifacts, including failed regressions and successful installed receipts, are in `data/logs/research/bidirectional_cohort/v89_independent_monitor_20260915_v1/`.
