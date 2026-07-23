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
| Process started | 2026-07-22 | pid in `/tmp/hv4a-soak.pid` |
| Warm complete | | warm_bars ~43200 expected (~5 min CPU) |
| Live L2 fill seen | | first `l2_walk_v1` row with BBO |
| Soak stop | | reason + summary |

## Verdict

_Pending soak completion._
