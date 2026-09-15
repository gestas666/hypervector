# Provider exit-side display repair

Native routing sequence 607914, observed September 15 at 21:00:08 UTC, reports
an SPCX short-only recipe exit while the account holds a long. No order action
is appropriate. The Rust provider evaluation currently discards `exit_sides`
and several views show a generic `CLOSE_OPEN_POSITION` or `CLOSE`.

1. Preserve the exact native evaluation and reproduce its ambiguous display
   through the existing rendered TUI tests before changing implementation.
2. Retain recorded exit sides and reason in the display model. Use one formatter
   across setup, chart, router and provider-regime views. Missing or contradictory
   side evidence must remain explicitly unavailable. A signal is not an order.
3. Test short, long, both-side and legacy/malformed evidence, and narrow/wide
   terminal layouts. Run the Rust suite and inspect the release executable using
   frozen native evidence. Preserve the existing leverage display.
4. Install reviewed display-only source and a separately versioned binary with
   backup hashes, rollback evidence, review and research-journal provenance.

No strategy, routing, order, sizing, leverage or backend lifecycle change is
part of this repair. High confidence requires native/source agreement and
rendered tests; clipped labels, incorrect sides or changed execution behavior
falsify acceptance. Missing older evidence must not borrow a current side.
