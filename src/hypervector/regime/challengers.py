"""Point-in-time, annotation-only statistical regime challengers."""

from __future__ import annotations

from importlib.util import find_spec

import numpy as np
import pandas as pd

from hypervector.regime.hypervelocity_eval import _datetime_bars

UNASSIGNED = "UNASSIGNED"


def expanding_volatility_terciles(
    bars: pd.DataFrame,
    *,
    volatility_window: int = 60,
    minimum_history: int = 240,
) -> pd.Series:
    """Return causal low/mid/high volatility annotations."""
    if volatility_window < 2:
        raise ValueError("volatility_window must be >= 2")
    if minimum_history < volatility_window:
        raise ValueError("minimum_history must be >= volatility_window")
    indexed = _validated_close_bars(bars)
    returns = np.log(indexed["close"].astype(float)).diff()
    volatility = returns.rolling(
        volatility_window,
        min_periods=volatility_window,
    ).std()
    lower = volatility.expanding(min_periods=minimum_history).quantile(1.0 / 3.0)
    upper = volatility.expanding(min_periods=minimum_history).quantile(2.0 / 3.0)
    lower = lower.shift(1)
    upper = upper.shift(1)
    states = pd.Series(UNASSIGNED, index=indexed.index, dtype=object)
    available = volatility.notna() & lower.notna() & upper.notna()
    states = states.mask(available & (volatility <= lower), "VOL_LOW")
    states = states.mask(available & (volatility >= upper), "VOL_HIGH")
    states = states.mask(
        available & (volatility > lower) & (volatility < upper), "VOL_MID"
    )
    states.name = "volatility_tercile"
    return states


def evaluate_regime_challengers(
    bars: pd.DataFrame,
    *,
    forward_horizon: int = 30,
    random_state: int = 42,
    n_splits: int = 3,
    wasserstein_window: int = 60,
    wasserstein_sample_cap: int = 1_000,
) -> dict[str, object]:
    """Evaluate statistical states without changing strategy execution."""
    indexed = _validated_close_bars(bars)
    terciles = expanding_volatility_terciles(indexed)
    arms: dict[str, object] = {
        "expanding_volatility_terciles": _annotation_report(
            indexed,
            terciles,
            forward_horizon,
            assigned_key="assigned_rows",
        ),
        "gmm": _safe_gmm_report(
            indexed,
            forward_horizon,
            random_state,
            n_splits,
        ),
        "wasserstein": _safe_wasserstein_report(
            indexed,
            forward_horizon,
            random_state,
            n_splits,
            wasserstein_window,
            wasserstein_sample_cap,
        ),
        "hmm": _optional_dependency_arm("hmmlearn", "filtered HMM states"),
        "ms_ar": _optional_dependency_arm("statsmodels", "MS-AR states"),
    }
    return {
        "schema_version": 1,
        "annotation_only": True,
        "may_filter": False,
        "may_size": False,
        "may_route": False,
        "total_bars": len(indexed),
        "forward_horizon_bars": forward_horizon,
        "random_state": random_state,
        "chronological_splits": n_splits,
        "arms": arms,
    }


def _validated_close_bars(bars: pd.DataFrame) -> pd.DataFrame:
    indexed = _datetime_bars(bars)
    if "close" not in indexed.columns:
        raise ValueError("challenger bars require close")
    close = indexed["close"].astype(float)
    if not np.isfinite(close.to_numpy()).all() or (close <= 0.0).any():
        raise ValueError("challenger close values must be finite and positive")
    return indexed


def _feature_frame(bars: pd.DataFrame) -> pd.DataFrame:
    returns = np.log(bars["close"].astype(float)).diff()
    return pd.DataFrame(
        {
            "return_1m": returns,
            "volatility_30m": returns.rolling(30, min_periods=30).std(),
            "trend_15m": returns.rolling(15, min_periods=15).sum(),
            "tail_30m": returns.abs().rolling(30, min_periods=30).max(),
        },
        index=bars.index,
    ).dropna()


def _walk_forward_ranges(length: int, n_splits: int) -> list[tuple[int, int]]:
    if n_splits < 1:
        raise ValueError("n_splits must be positive")
    initial = max(60, length // 2)
    if initial >= length:
        raise ValueError("insufficient rows for chronological challenger splits")
    boundaries = np.linspace(initial, length, n_splits + 1, dtype=int)
    return [
        (int(boundaries[index]), int(boundaries[index + 1]))
        for index in range(n_splits)
        if boundaries[index + 1] > boundaries[index]
    ]


def _gmm_states(
    bars: pd.DataFrame,
    random_state: int,
    n_splits: int,
) -> tuple[pd.Series, list[dict[str, object]]]:
    from sklearn.mixture import GaussianMixture
    from sklearn.preprocessing import StandardScaler

    features = _feature_frame(bars)
    states = pd.Series(UNASSIGNED, index=features.index, dtype=object)
    folds: list[dict[str, object]] = []
    for start, end in _walk_forward_ranges(len(features), n_splits):
        train = features.iloc[:start]
        test = features.iloc[start:end]
        scaler = StandardScaler().fit(train)
        train_scaled = scaler.transform(train)
        model = GaussianMixture(
            n_components=3,
            covariance_type="full",
            n_init=3,
            reg_covar=1e-6,
            random_state=random_state,
        ).fit(train_scaled)
        order = np.argsort(model.means_[:, 1])
        names = _ordered_cluster_names(order, "GMM_VOL")
        predictions = model.predict(scaler.transform(test))
        states.loc[test.index] = [names[int(value)] for value in predictions]
        folds.append(_fold_record(features, start, end, bool(model.converged_)))
    return states, folds


def _safe_gmm_report(
    bars: pd.DataFrame,
    horizon: int,
    random_state: int,
    n_splits: int,
) -> dict[str, object]:
    try:
        states, folds = _gmm_states(bars, random_state, n_splits)
    except (ImportError, ValueError, np.linalg.LinAlgError) as error:
        return _failure_report(error)
    report = _annotation_report(
        bars,
        states,
        horizon,
        assigned_key="oos_assigned_rows",
    )
    report["folds"] = folds
    return report


def _wasserstein_windows(
    bars: pd.DataFrame,
    window: int,
) -> tuple[pd.DatetimeIndex, np.ndarray]:
    if window < 5:
        raise ValueError("wasserstein_window must be >= 5")
    returns = np.log(bars["close"].astype(float)).diff().to_numpy()
    if len(returns) < window:
        raise ValueError("insufficient rows for Wasserstein windows")
    windows = np.lib.stride_tricks.sliding_window_view(returns, window)
    valid = np.isfinite(windows).all(axis=1)
    index = bars.index[window - 1 :][valid]
    return pd.DatetimeIndex(index), np.sort(windows[valid], axis=1)


def _fit_wasserstein_medoids(
    windows: np.ndarray,
    random_state: int,
    sample_cap: int,
) -> np.ndarray:
    from scipy.spatial.distance import cdist

    if sample_cap < 30:
        raise ValueError("wasserstein_sample_cap must be >= 30")
    rng = np.random.default_rng(random_state)
    count = min(len(windows), sample_cap)
    sample_index = np.sort(rng.choice(len(windows), size=count, replace=False))
    sample = windows[sample_index]
    distances = cdist(sample, sample, metric="cityblock") / windows.shape[1]
    medoids = [int(np.argmin(distances.sum(axis=1)))]
    while len(medoids) < 3:
        nearest = distances[:, medoids].min(axis=1)
        medoids.append(int(np.argmax(nearest)))
    for _ in range(10):
        labels = distances[:, medoids].argmin(axis=1)
        updated = _updated_medoids(distances, labels, medoids)
        if updated == medoids:
            break
        medoids = updated
    return sample[medoids]


def _updated_medoids(
    distances: np.ndarray,
    labels: np.ndarray,
    current: list[int],
) -> list[int]:
    updated: list[int] = []
    for cluster, medoid in enumerate(current):
        members = np.flatnonzero(labels == cluster)
        if len(members) == 0:
            updated.append(medoid)
            continue
        within = distances[np.ix_(members, members)]
        updated.append(int(members[int(np.argmin(within.sum(axis=1)))]))
    return updated


def _wasserstein_states(
    bars: pd.DataFrame,
    random_state: int,
    n_splits: int,
    window: int,
    sample_cap: int,
) -> tuple[pd.Series, list[dict[str, object]]]:
    from scipy.spatial.distance import cdist

    index, windows = _wasserstein_windows(bars, window)
    states = pd.Series(UNASSIGNED, index=index, dtype=object)
    folds: list[dict[str, object]] = []
    for start, end in _walk_forward_ranges(len(windows), n_splits):
        prototypes = _fit_wasserstein_medoids(
            windows[:start],
            random_state,
            sample_cap,
        )
        order = np.argsort(prototypes.std(axis=1))
        names = _ordered_cluster_names(order, "WASSERSTEIN_VOL")
        distances = cdist(windows[start:end], prototypes, metric="cityblock") / window
        predictions = distances.argmin(axis=1)
        states.iloc[start:end] = [names[int(value)] for value in predictions]
        folds.append(_fold_record(pd.DataFrame(index=index), start, end, True))
    return states, folds


def _safe_wasserstein_report(
    bars: pd.DataFrame,
    horizon: int,
    random_state: int,
    n_splits: int,
    window: int,
    sample_cap: int,
) -> dict[str, object]:
    try:
        states, folds = _wasserstein_states(
            bars,
            random_state,
            n_splits,
            window,
            sample_cap,
        )
    except (ImportError, ValueError, np.linalg.LinAlgError) as error:
        return _failure_report(error)
    report = _annotation_report(
        bars,
        states,
        horizon,
        assigned_key="oos_assigned_rows",
    )
    report["folds"] = folds
    report["distance"] = "one_dimensional_empirical_wasserstein_1"
    return report


def _annotation_report(
    bars: pd.DataFrame,
    states: pd.Series,
    horizon: int,
    *,
    assigned_key: str,
) -> dict[str, object]:
    assigned = states.ne(UNASSIGNED)
    distribution = states.loc[assigned].value_counts()
    report: dict[str, object] = {
        "status": "completed",
        "point_in_time": True,
        assigned_key: int(assigned.sum()),
        "state_distribution": {
            str(state): int(count) for state, count in distribution.items()
        },
        "forward_returns": _forward_return_report(bars, states, horizon),
    }
    return report


def _forward_return_report(
    bars: pd.DataFrame,
    states: pd.Series,
    horizon: int,
) -> dict[str, object]:
    if horizon < 1:
        raise ValueError("forward_horizon must be positive")
    close = bars["close"].astype(float)
    forward = close.shift(-horizon) / close - 1.0
    aligned = pd.DataFrame({"state": states, "forward": forward.reindex(states.index)})
    aligned = aligned.loc[aligned["state"].ne(UNASSIGNED)].dropna()
    return {
        str(state): {
            "rows": int(len(group)),
            "mean_bps": float(group["forward"].mean() * 10_000.0),
            "median_bps": float(group["forward"].median() * 10_000.0),
            "positive_pct": float((group["forward"] > 0.0).mean() * 100.0),
        }
        for state, group in aligned.groupby("state")
    }


def _ordered_cluster_names(order: np.ndarray, prefix: str) -> dict[int, str]:
    return {
        int(component): f"{prefix}_{rank + 1}" for rank, component in enumerate(order)
    }


def _fold_record(
    frame: pd.DataFrame,
    start: int,
    end: int,
    converged: bool,
) -> dict[str, object]:
    return {
        "train_rows": start,
        "test_rows": end - start,
        "train_end_utc": frame.index[start - 1].isoformat(),
        "test_start_utc": frame.index[start].isoformat(),
        "test_end_utc": frame.index[end - 1].isoformat(),
        "converged": converged,
    }


def _optional_dependency_arm(package: str, method: str) -> dict[str, object]:
    available = find_spec(package) is not None
    return {
        "status": "not_implemented" if available else "unavailable",
        "point_in_time": True,
        "dependency": package,
        "dependency_available": available,
        "required_method": method,
        "reason": (
            "research implementation not enabled"
            if available
            else f"optional dependency {package} is not installed"
        ),
    }


def _failure_report(error: Exception) -> dict[str, object]:
    return {
        "status": "technical_failure",
        "point_in_time": True,
        "error": f"{type(error).__name__}: {error}",
    }
