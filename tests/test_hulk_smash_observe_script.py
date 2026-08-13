from pathlib import Path


def test_hulk_observer_script_has_no_authenticated_execution_surface() -> None:
    source = Path("scripts/hulk_smash_observe.py").read_text(encoding="utf-8")

    assert "create_read_only_btc_reader" in source
    assert "load_wallet_env_if_present" in source
    assert "create_armed_btc_adapter" not in source
    assert "--enabled" not in source
    assert "--i-accept-live-risk" not in source
    assert ".submit_entry(" not in source
    assert ".place_protective_stop(" not in source
    assert "runner.run(max_polls=args.max_polls)\n        return 0" in source
