"""A bounded paper daemon stops as soon as its final permitted bar is processed."""

from __future__ import annotations

from pathlib import Path

from paper_fix_fixtures import write_strict_export

from hypervector.data.sources import fixture_ohlcv
from hypervector.paper.runner import start_paper_daemon


def test_daemon_does_not_sleep_after_reaching_max_live_bars(tmp_path: Path) -> None:
    export = write_strict_export(tmp_path)
    warm = fixture_ohlcv(n_bars=20, drift=-1.0)
    live = fixture_ohlcv(n_bars=2, drift=-1.0)
    live["timestamp"] = warm["timestamp"].iloc[-1] + (
        live["timestamp"] - live["timestamp"].iloc[0]
    ) + (warm["timestamp"].iloc[1] - warm["timestamp"].iloc[0])
    sleeps: list[float] = []

    result = start_paper_daemon(
        export_dir=export,
        data_root=tmp_path / "data",
        warm_ohlcv=warm,
        poll_fn=lambda **_kwargs: live.copy(),
        max_live_bars=2,
        poll_interval_secs=5.0,
        sleep_fn=sleeps.append,
        install_signal_handlers=False,
        enable_funding_refresh=False,
        execution_mode="paper",
    )

    assert result.live_bars == 2
    assert result.stop_reason == "max_live_bars"
    # The cap was reached inside the batch: no idle poll interval before exit.
    assert sleeps == []
