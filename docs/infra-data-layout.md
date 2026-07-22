# hypervector data layout (I2)

**Status:** Locked for Phase 1–3 prep (2026-07-22). **Implemented:** `hypervector.infra.ensure_data_layout` + CLI `infra-init`.

All runtime data lives under a configurable `--data-root` (default `./data`).  
The repo root `/data/` is **gitignored**. Do not commit market data, ledgers, or keys.

## Directory map

```text
data/
  cache/                 # Parquet OHLCV (+ future book features under cache/book/)
  runs/                  # SQLite research trials (hypervector.db)
  exports/               # Phase 1 → Phase 2 bundles <id>/meta|params|metrics
  logs/
    research/            # CLI / sweep logs
    nautilus/            # Phase 2/3 engine logs
  nautilus/
    backtest/            # Phase 2 catalogs / reports
  paper/
    ledger/              # Would-be fills / positions (paper only)
    decisions/           # Decision jsonl/parquet + fill model
    # optional: paper.db
  live/                  # Live only — never share files with paper/
```

## Rules

1. **Paper ≠ live storage** — separate roots; tag every row with `execution_mode`.
2. **Cache-first** research history; live paper decisions use **HL feed** after warm-up.
3. **Configs** stay tracked under `configs/` (costs, risk, exits, fee_model).
4. **Secrets** only via environment / `.env` (gitignored); not in exports.
5. **No** Postgres / Redis / k8s for MVP (design non-goal).

## CLI (once Task 2 lands)

```bash
uv run python -m hypervector infra-init --data-root data
```
