# Phase 4a paper soak notes

**Started:** 2026-07-22  
**Branch HEAD at start:** `09329f4`  
**Export:** `data/exports/downtrend_crown_stack_short_c4fd7067`  
**Data root:** `/tmp/hv4a-soak`  
**Stop file:** `/tmp/hv4a-soak.stop`  
**PID file:** `/tmp/hv4a-soak.pid`

## Config

- preferred_fill_model: `l2_walk_v1`
- max_book_age_ms: 3000
- metalabel: off
- poll_interval: 5s
- No venue orders (paper only)

## Honesty rules under test

1. Warm-up fills = `bar_close_slippage_v1` + `fill_fallback_reason=book_missing`  
2. Live fills may be `l2_walk_v1` when book fresh (BBO present)  
3. All `execution_mode=paper`; no files under `live/`  
4. No L2 REST storm during warm-up  

## Commands

```bash
# status
ps -p $(cat /tmp/hv4a-soak.pid) -o pid,etime,command

# stop
touch /tmp/hv4a-soak.stop

# logs
tail -f /tmp/hv4a-soak/stderr.log
```

## Results (fill in as soak progresses)

| Checkpoint | Time | Notes |
|------------|------|-------|
| Process started | 2026-07-22 | pid `35764` in `/tmp/hv4a-soak.pid` |
| Warm progress | ~6–7 min | decisions climbed to **1383** then flat → warm done, live polling |
| Warm honesty | mid-soak | **370** market fills, all `bar_close_slippage_v1` + `book_missing`; **0** live files; all `execution_mode=paper` |
| Live phase (~15 min) | 2026-07-22 | Still running; **rows flat at 1383** (flat book after warm close — no new market decisions until next signal) |
| Live L2 fill seen | pending | needs enter/exit on a post-warm live bar |
| Soak stop | | reason + summary |

## Warm-up sample (honest)

- `fill_model_id=bar_close_slippage_v1`, `fill_fallback_reason=book_missing`
- No BBO on historical fills (correct)
- No ConnectionReset / L2 spam in stderr (only PAPER MODE banner)

## Live phase note

After warm close at `2026-07-22T23:44`, position flat → no funding rows. 1m live bars may process with **no decision append** until strategy fires. That is expected, not a hang.

## Verdict

_Warm-up honesty: **PASS**. Live L2 fill: **pending signal**. Soak left running for longer observation. 4b design can start in parallel._
