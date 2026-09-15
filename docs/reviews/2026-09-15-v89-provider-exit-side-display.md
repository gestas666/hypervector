# Provider exit-side display: installed validation

The monitor now retains the provider's recorded exit sides instead of displaying
a generic `CLOSE_OPEN_POSITION`. The native SPCX evaluation at **21:00 UTC on
September 15** targeted **short positions** while the account held a **long**.
The backend correctly took no action. High confidence applies to this bounded
diagnosis and the tested display repair; it is not evidence of strategy edge.

Candidate: `64b9bbff18b8f8d530dd47f0b8f279d352e079d3`.
Installed source: `66e6fc84c1c8ff35cc77333fcec33f3160c1103a`.
Executable: `target/release/tui-regime-detector-v89-monitor-20260915-exits`.
SHA256: `52df3fbb38a0a91f8e4577bebb7884da537dc8c3c8fd35411751684d7866bc84`.

## Evidence and diagnosis

Native routing sequence **607914**, observed **21:00:08.503781 UTC**, contains
seven hourly provider evaluations, no routed actions and no withheld intents.
Its SPCX record has `decision_action=close_open_position`,
`exit_sides=["short"]`, `exit_reason=hourly_price_recipe_exit`, and reference
price **143.31**. The frozen account snapshot retains the SPCX long of **3.47**,
entry OID **546010609566**, and the explicit provider-exit policy **honor**.
This was not an ignored exit for the held side.

The indexed routing payload matches the exact native ledger bytes at offset
**4380897856**, length **14430**, SHA256
`d260c365a5d1ca5f7a4276d336dce5508c290f8c86923282628469f8c7d26915`.
Five additional selected native rows were authenticated against their indexed
payloads for a frozen terminal input through **21:06:35 UTC**. They are a
selected rendering input, not a full event replay or current-freshness claim.

The provider evaluation's serialized round trip is exact. The deployed pure
exit-decision function returns no exit for the recorded long and returns the
recorded recipe exit for a hypothetical short. The original Rust display model
omitted `exit_sides`; rendered regression tests reproduced the resulting generic
close label before implementation changed.

## Repair and validation

- The display model retains exit sides and exit reason. One formatter supplies
  setup/router, chart and provider-regime labels. It distinguishes `EXIT LONG`,
  `EXIT SHORT`, both-side exits, and `EXIT SIDE N/A` for absent or contradictory
  side evidence. An explicitly side-named legacy action remains usable.
- Entry and exit signals can coexist in the backend contract. The formatter
  retains both, including compact regime-matrix labels such as
  `ENTER L/EXIT S`. Entry eligibility is labeled separately from exit evidence.
- The setup inspector labels the recipe as a provider signal. It does not claim
  an order was placed or a lifecycle closed; those remain receipt-backed facts.
- Installed Rust suite: **655 passed, 23 ignored, zero failures**. The ignored
  tests require their named historical/local fixtures and are not passing claims.
  The pure provider-exit controller suite additionally passed **11 tests**.
- The final release build succeeded. Both the final candidate executable and
  the installed executable rendered the frozen native portfolio, selected SPCX
  setup and router at **100×28, 120×36 and 190×52**. Each run retained 12 view/
  navigation captures plus startup, exited normally, and ran with network and
  project-file writes denied to the TUI. `LEV C/V` and **10x/10x** remained visible.
- Initial terminal automation expected SPCX to be visible before selecting its
  row in the narrow viewport. That harness assertion failed; selecting the row
  first corrected the harness. The failed capture and original script remain.

The installation preserved **5,514 other files**, both earlier executable
versions, and user-session PIDs **29190/29191/30603/62016/62017** with matching
birth and ownership. No financial process was started, stopped, restarted or
signalled. No strategy, route, risk, leverage, sizing or order behavior changed.

## Operator command and rollback

Open the updated monitor in another terminal while leaving the original
combined session open:

```bash
cd /Users/gestas/Prototypes/hypervector
.venv/bin/python -m hypervector cohort-tui --mode monitor --independent-monitor \
  --config configs/multi_asset_growth_first_5000_noncrypto_live_v89.toml \
  --tui-bin target/release/tui-regime-detector-v89-monitor-20260915-exits \
  --tui-bin-sha256 52df3fbb38a0a91f8e4577bebb7884da537dc8c3c8fd35411751684d7866bc84
```

The running original TUI still uses its original executable. The independently
launched version owns only its reporter/display; fresh same-run reporting remains
required. Older records without explicit exit-side evidence remain unavailable.

Backups, source patch, installation hashes and native artifacts are under
`data/logs/research/bidirectional_cohort/v89_exit_side_display_20260915_v1/`.
The reverse source patch passed `git apply --reverse --check`. A display rollback
can select the preserved previous monitor executable and its prior checksum;
source rollback must use the recorded patch/backups and preserve unrelated work.
Neither rollback requires closing the original combined session.

## Decision

**Recommendation / why now:** retain the display repair because a current native
signal reproduced the ambiguity. It applies across assets and regimes; no new
strategy rule is proposed. Leaving the generic close label was the simpler
alternative, but it concealed the direction needed to interpret management.

**Expected upside:** more accurate monitoring and operator interpretation.
No trading-return improvement is inferred from this display change.

**Failure triggers and limits:** a wrong or clipped exit side, lost simultaneous
signal, fabricated legacy side, lost leverage, or changed execution behavior
reopens the repair. Tests and captures cover the stated inputs and layouts,
not all possible terminals or future schemas.

**Approval:** existing corrective-update authorization covers this reporting
installation. No additional financial action is requested.

**Next investigation:** use the existing native transition watcher for a new
entry, exit, protection change or fault. The SPCX short-only signal is explained;
do not reopen it as an ignored long exit. Prospective outcome seals remain closed.
