# hypervector CLI command matrix

Invocation: `uv run python -m hypervector --data-root <root> <cmd> …`

| Command | Mutates | Network | Secrets | Typical use |
|---------|---------|---------|---------|-------------|
| `infra-init` | creates dirs under data-root | no | no | bootstrap layout |
| `status` | no | no | no (presence via other cmds) | inventory + honesty |
| `paper-check` | no | no | presence bool only | paper surface flags |
| `live-check` | no | no | presence bool only | live readiness / start_gate |
| `paper-report` | no | no | no | summarize paper JSONL |
| `live-report` | no | no | no | summarize live JSONL |
| `history` | cache parquet | yes (unless cache hit) | no | fetch OHLCV |
| `regime` | optional export | may fetch | no | regime metrics JSON |
| `sweep-up` / `sweep-down` | runs DB | may fetch | no | research grid |
| `report` | no | no | no | rank trials |
| `export` | writes exports/ | no | no | best trial bundle |
| `export-validate` | no | no | no | schema check |
| `phase2-check` | no | no | no | loadout + nautilus probe |
| `phase2-run` | backtest artifacts | optional | no | historical engine |
| `paper-run` | paper decisions/ledger | HL bars | presence for some feeds | shadow/paper daemon |
| `live-run` | live decisions; **may place** | yes | **required to place** | armed mainnet daemon |

## paper-run essentials

| Flag | Default | Notes |
|------|---------|-------|
| `--path` | required | Phase 1.5 export dir |
| `--mode` | `shadow` | `shadow` \| `paper` |
| `--max-live-bars` | none | smoke cap |
| `--poll-interval` | 5 | seconds |
| `--preferred-fill-model` | `l2_walk_v1` | falls back bar_close |
| `--max-book-age-ms` | 3000 | stale book |
| `--metalabel` / `--no-metalabel` | off | optional |

## live-run essentials

| Flag | Required | Notes |
|------|----------|-------|
| `--path` | yes | export dir |
| `--enabled` | yes to start | policy enabled |
| `--i-accept-live-risk` | yes to start | arm |
| `--max-notional-usd` | default 50 | hard cap |

Env (presence only in checks):

- `HYPERVECTOR_HL_WALLET_ADDRESS`
- `HYPERVECTOR_HL_API_PRIVATE_KEY`

## TUI flags

| Flag | Default |
|------|---------|
| `--data-root` | `data` |
| `--refresh-ms` | `1000` |
| `--tape` | `auto` (`paper`\|`live`\|`auto`) |

TUI subprocess allowlist: `status`, `paper-check`, `live-check`, `paper-report`, `live-report`, `regime`.
