"""Purged + embargoed CV and chronological walk-forward windows for trade labels."""

from __future__ import annotations

from collections.abc import Iterator

import numpy as np


def purged_kfold_split(
    entry_ts_ms: np.ndarray,
    outcome_ts_ms: np.ndarray,
    n_splits: int,
    embargo_minutes: int,
) -> Iterator[tuple[np.ndarray, np.ndarray]]:
    """Yield (train_idx, test_idx) for chronological purged folds."""
    n = len(entry_ts_ms)
    if n == 0:
        return
    if len(outcome_ts_ms) != n:
        raise ValueError("entry_ts_ms and outcome_ts_ms must have same length")
    if n_splits < 2:
        raise ValueError("n_splits must be >= 2")

    order = np.argsort(entry_ts_ms, kind="stable")
    sorted_entry = entry_ts_ms[order]
    sorted_outcome = outcome_ts_ms[order]
    fold_edges = np.linspace(0, n, n_splits + 1, dtype=int)
    embargo_ms = int(embargo_minutes) * 60_000

    for k in range(n_splits):
        test_lo, test_hi = int(fold_edges[k]), int(fold_edges[k + 1])
        if test_lo >= test_hi:
            continue
        test_sorted = np.arange(test_lo, test_hi)
        test_entry_min = int(sorted_entry[test_lo:test_hi].min())
        test_outcome_max = int(sorted_outcome[test_lo:test_hi].max())

        train_mask = np.ones(n, dtype=bool)
        train_mask[test_lo:test_hi] = False
        # Purge train samples whose label interval overlaps test window
        for i in range(n):
            if not train_mask[i]:
                continue
            e = int(sorted_entry[i])
            o = int(sorted_outcome[i])
            # overlap if [e,o] intersects [test_entry_min, test_outcome_max]
            if e <= test_outcome_max and o >= test_entry_min:
                train_mask[i] = False
            # embargo around test
            if (
                abs(e - test_entry_min) < embargo_ms
                or abs(e - test_outcome_max) < embargo_ms
            ):
                train_mask[i] = False
            if o > test_entry_min - embargo_ms and e < test_outcome_max + embargo_ms:
                # already covered; keep simple extra embargo on entry near test
                if test_entry_min - embargo_ms <= e <= test_outcome_max + embargo_ms:
                    train_mask[i] = False

        train_sorted = np.flatnonzero(train_mask)
        if train_sorted.size == 0 or test_sorted.size == 0:
            continue
        yield order[train_sorted], order[test_sorted]


def walk_forward_windows(
    entry_ts_ms: np.ndarray,
    *,
    train_ms: int,
    test_ms: int,
    step_ms: int | None = None,
    min_train_samples: int = 50,
    min_test_samples: int = 10,
) -> list[tuple[np.ndarray, np.ndarray]]:
    """Expanding-style chronological windows on sorted entry times.

    Returns list of (train_idx, test_idx) into the original sample array.
    First test starts after train_ms from the earliest entry.
    """
    n = len(entry_ts_ms)
    if n == 0:
        return []
    order = np.argsort(entry_ts_ms, kind="stable")
    ts = entry_ts_ms[order].astype(np.int64)
    t0 = int(ts[0])
    t_end = int(ts[-1])
    step = int(step_ms if step_ms is not None else test_ms)
    windows: list[tuple[np.ndarray, np.ndarray]] = []

    test_start = t0 + int(train_ms)
    while test_start < t_end:
        test_end = test_start + int(test_ms)
        train_mask = ts < test_start
        test_mask = (ts >= test_start) & (ts < test_end)
        tr = order[np.flatnonzero(train_mask)]
        te = order[np.flatnonzero(test_mask)]
        if tr.size >= min_train_samples and te.size >= min_test_samples:
            windows.append((tr, te))
        test_start += step
        if test_end >= t_end:
            break
    return windows
