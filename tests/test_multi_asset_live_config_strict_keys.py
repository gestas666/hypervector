"""The live profile loader refuses keys it would otherwise silently ignore."""

from pathlib import Path
import tomllib

import pytest

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.live.multi_asset_live_config_parsing import MultiAssetLiveConfigError

V91 = Path("tests/fixtures/profiles/multi_asset_growth_first_5000_adaptive_eight_asset_v91.toml")
V93 = Path("tests/fixtures/profiles/multi_asset_growth_first_5000_exit_v2_v93_proposal.toml")
DONCHIAN = "hourly_donchian_20_10_atr20_bidirectional_v1"


def _variant(tmp_path: Path, old: str, new: str, count: int = 1) -> Path:
    text = V93.read_text()
    assert text.count(old) >= count
    target = tmp_path / "variant.toml"
    target.write_text(text.replace(old, new, count))
    return target


def _first_provider_line(key: str) -> str:
    return next(
        line
        for line in V93.read_text().splitlines()
        if line.startswith("execution = ") and key in line
    )


def test_checked_in_v91_and_v93_keep_their_fingerprints() -> None:
    assert (
        load_multi_asset_live_config(V91, mode="observe").profile_fingerprint
        == "00ca7e008e8b2ec7cbeac4b9541cabf39a8576a23769b92a169e984616fe8d8c"
    )
    assert (
        load_multi_asset_live_config(V93, mode="observe").profile_fingerprint
        == "33131f1898d86dda4f5cab2b6091748144f6a81da29b9c9464a644b330dc3e05"
    )


def test_misspelled_adaptive_exit_policy_is_refused(tmp_path: Path) -> None:
    line = _first_provider_line("adaptive_exit_policy")
    path = _variant(
        tmp_path, line, line.replace("adaptive_exit_policy", "adaptive_exit_polcy")
    )
    with pytest.raises(MultiAssetLiveConfigError) as refused:
        load_multi_asset_live_config(path, mode="observe")
    message = str(refused.value)
    assert "adaptive_exit_polcy" in message and "execution" in message


def test_misspelled_stop_risk_budget_is_refused(tmp_path: Path) -> None:
    line = _first_provider_line("stop_risk_budget")
    path = _variant(
        tmp_path, line, line.replace("stop_risk_budget", "stop_risk_budjet")
    )
    with pytest.raises(MultiAssetLiveConfigError) as refused:
        load_multi_asset_live_config(path, mode="observe")
    assert "stop_risk_budjet" in str(refused.value)


def test_misspelled_stop_risk_budget_field_is_refused(tmp_path: Path) -> None:
    path = _variant(tmp_path, "maximum_loss_usd = 25.0", "maximum_loss_usdd = 25.0")
    with pytest.raises(ValueError, match="maximum_loss_usdd"):
        load_multi_asset_live_config(path, mode="observe")


@pytest.mark.parametrize(
    "old,new,table,key",
    [
        (
            'margin_mode = "isolated"\n',
            'margin_mode = "isolated"\nmaximum_position = 8\n',
            "top-level",
            "maximum_position",
        ),
        (
            "poll_seconds = 15.0\n",
            "poll_seconds = 15.0\npoll_second = 30.0\n",
            "[runtime]",
            "poll_second",
        ),
        (
            "entry_slippage_cap_fraction = 0.002\n",
            "entry_slipage_cap_fraction = 0.002\n",
            "[[assets]] BTC",
            "entry_slipage_cap_fraction",
        ),
        (
            f'strategy_id = "{DONCHIAN}"\n',
            f'strategy_id = "{DONCHIAN}"\nexecution_symbol = []\n',
            f"[[providers]] {DONCHIAN}",
            "execution_symbol",
        ),
    ],
)
def test_unknown_key_refusal_names_its_table_and_key(
    tmp_path: Path, old: str, new: str, table: str, key: str
) -> None:
    path = _variant(tmp_path, old, new)
    with pytest.raises(MultiAssetLiveConfigError) as refused:
        load_multi_asset_live_config(path, mode="observe")
    assert table in str(refused.value) and key in str(refused.value)


# The retained cohort profiles: the live V95 chain (V95, its V94 predecessor and
# the V95->V94 rollback). The two canaries other tests mutate as templates are
# test fixtures now.
RETAINED_COHORT_PROFILES = frozenset(
    {
        "multi_asset_growth_first_5000_review_fixes_v95.toml",
        "multi_asset_growth_first_5000_review_actions_v94.toml",
        "v95-to-v94-rollback-20260927-v1.toml",
    }
)
TEMPLATE_FIXTURE_PROFILES = frozenset(
    {
        "multi_asset_bidirectional_canary.toml",
        "multi_asset_bidirectional_complete_portfolio_canary_v25.toml",
    }
)
FIXTURE_PROFILES = Path("tests/fixtures/profiles")


def _load_every_cohort_profile(directory: Path) -> set[str]:
    loaded: set[str] = set()
    for path in sorted(directory.glob("*.toml")):
        with path.open("rb") as handle:
            raw = tomllib.load(handle)
        if not {"assets", "providers", "runtime"} <= set(raw):
            continue
        load_multi_asset_live_config(path, mode="observe")
        loaded.add(path.name)
    return loaded


def test_every_checked_in_cohort_profile_still_loads() -> None:
    """Strict-key refusal accepts every retained profile, including V95's chain."""
    assert RETAINED_COHORT_PROFILES <= _load_every_cohort_profile(Path("configs"))


def test_every_fixture_cohort_profile_still_loads() -> None:
    """Historical profiles kept as test fixtures stay valid under strict keys."""
    loaded = _load_every_cohort_profile(FIXTURE_PROFILES)
    assert {V91.name, V93.name} | TEMPLATE_FIXTURE_PROFILES <= loaded
