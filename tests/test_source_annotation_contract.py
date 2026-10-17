"""A collection-only source profile must not secretly run inference."""

from dataclasses import fields
import json
from pathlib import Path

import pytest

from hypervector.paper.session import PaperSession
from hypervector.strategies.hypervelocity_profile import load_hypervelocity_profile
from hypervector.strategies.source_follow_profile import (
    SourceFollowHypervelocityProfile,
)
from test_paper_session import _write_strict_export
from test_source_follow_paper_session import _TrendDownClassifier
from hypervector.regime.source_follow_runtime import SourceFollowRuntime
from hypervector.regime.source_follow_session import SourceFollowSessionSignal


def _profile(root: Path) -> SourceFollowHypervelocityProfile:
    base = load_hypervelocity_profile("configs/hypervelocity_faithful.toml")
    settings = {field.name: getattr(base, field.name) for field in fields(base)}
    return SourceFollowHypervelocityProfile(
        **settings,
        base_profile_sha256="a" * 64,
        source_revision="fixture",
        source_backend_root=root,
        minimum_confidence=0.7,
        minimum_range_bps=0.0,
        maximum_range_bps=100.0,
        decision_delay_seconds=60.0,
        entry_pulse_seconds=60.0,
        maximum_hold_seconds=86_400.0,
        entry_session_utc="always",
    )


def test_collection_profile_loads_no_model_and_reports_no_probability(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Journal identity and actual inference behavior must agree."""
    from hypervector.ml.metalabel import Metalabeler

    monkeypatch.setattr(
        Metalabeler,
        "from_root",
        lambda *_a, **_k: pytest.fail(
            "inference attempted for collection-only profile"
        ),
    )
    export = _write_strict_export(tmp_path, strategy="hypervelocity_1m_scalper_long")
    session = PaperSession(
        export_dir=export,
        data_root=tmp_path,
        hypervelocity_profile=_profile(tmp_path),
        source_follow_signal=SourceFollowSessionSignal(
            SourceFollowRuntime(_TrendDownClassifier())
        ),
    )
    conviction = session.conviction_provider.resolve()
    assert conviction.metalabel_p is None
    assert conviction.metalabel_bundle_id is None
    assert conviction.allow_entry is True
    session.ensure_session_identity()
    identity = json.loads(session.decisions_path.read_text().splitlines()[-1])
    assert identity["metalabel_policy"]["inference_active"] is False
    assert identity["metalabel_bundle_id"] is None
