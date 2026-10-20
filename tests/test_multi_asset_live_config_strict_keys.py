"""The live profile loader refuses keys it would otherwise silently ignore."""

from pathlib import Path
import tomllib

import pytest

from hypervector.live.multi_asset_live_config import load_multi_asset_live_config
from hypervector.live.multi_asset_live_config_parsing import MultiAssetLiveConfigError

ADAPTIVE_EIGHT_ASSET = Path("tests/fixtures/profiles/adaptive_eight_asset.toml")
EXIT_POLICY_V2 = Path("tests/fixtures/profiles/exit_policy_v2.toml")
DONCHIAN = "hourly_donchian_20_10_atr20_bidirectional_v1"


def _variant(tmp_path: Path, old: str, new: str, count: int = 1) -> Path:
    text = EXIT_POLICY_V2.read_text()
    assert text.count(old) >= count
    target = tmp_path / "variant.toml"
    target.write_text(text.replace(old, new, count))
    return target


def _first_provider_line(key: str) -> str:
    return next(
        line
        for line in EXIT_POLICY_V2.read_text().splitlines()
        if line.startswith("execution = ") and key in line
    )


def test_fixture_profiles_keep_their_fingerprints() -> None:
    assert (
        load_multi_asset_live_config(
            ADAPTIVE_EIGHT_ASSET, mode="observe"
        ).profile_fingerprint
        == "217720aba4e61b7001471258522f03bb02cac8f42b660ba19a049981aa4d7ae6"
    )
    assert (
        load_multi_asset_live_config(
            EXIT_POLICY_V2, mode="observe"
        ).profile_fingerprint
        == "b470ca1199fd14913af8e7b1c0d022b1bd3f1a24a263a041b5ad84dc542278c9"
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


# The profile chain: profile A, its successor B and the authored B -> A rollback.
CHAIN_PROFILES = frozenset(
    {
        "profile_a.toml",
        "profile_b.toml",
        "rollback_b_to_a.toml",
    }
)
TEMPLATE_FIXTURE_PROFILES = frozenset(
    {
        "cohort_base.toml",
        "complete_portfolio.toml",
    }
)
FIXTURE_PROFILES = Path("tests/fixtures/profiles")
CHAIN = Path("tests/fixtures/cohort_chain")


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
    """Strict-key refusal accepts every checked-in profile and the profile chain."""
    _load_every_cohort_profile(Path("configs"))
    assert _load_every_cohort_profile(CHAIN) == CHAIN_PROFILES


def test_every_fixture_cohort_profile_still_loads() -> None:
    """Profiles kept as test fixtures stay valid under strict keys."""
    loaded = _load_every_cohort_profile(FIXTURE_PROFILES)
    assert {ADAPTIVE_EIGHT_ASSET.name, EXIT_POLICY_V2.name} | (
        TEMPLATE_FIXTURE_PROFILES
    ) <= loaded
