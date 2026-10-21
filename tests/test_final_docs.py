"""Regression tests that bind the README, SKILL, HANDOFF and guide contracts to code."""

from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from hypervector.cli import LEGACY_ALIASES, build_parser, main

REPO = Path(__file__).resolve().parents[1]
README = (REPO / "README.md").read_text(encoding="utf-8")
SKILL = (REPO / "skills" / "hypervector-cli" / "SKILL.md").read_text(encoding="utf-8")
HANDOFF = (REPO / "HANDOFF.md").read_text(encoding="utf-8")
TRANSITION_GUIDE = (
    REPO / "docs" / "guides" / "cohort-live-transition-and-rollback.md"
).read_text(encoding="utf-8")

WALLET_ENV = "HYPERVECTOR_HL_WALLET_ADDRESS"
KEY_ENV = "HYPERVECTOR_HL_API_PRIVATE_KEY"


def _section(text: str, heading: str) -> str:
    """The body of one ``## heading`` section."""
    start = text.index(f"## {heading}\n")
    end = text.find("\n## ", start + 1)
    return text[start : end if end != -1 else len(text)]


def _flat(text: str) -> str:
    """Collapse Markdown line wrapping so a phrase matches across lines."""
    return " ".join(text.split())


def _error_document(stderr: str) -> dict[str, object]:
    return json.loads(stderr.strip().splitlines()[-1])


def _forbid_daemon(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(**_kwargs: object) -> None:
        raise AssertionError("live run reached the daemon after a refusal")

    monkeypatch.setattr("hypervector.live.runner.start_live_daemon", refuse)


# --------------------------------------------------------------------------- #
# live run: refusals exit 2 and --export REF resolves like every other command
# --------------------------------------------------------------------------- #


def test_live_run_unresolvable_latest_refuses_with_exit_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _forbid_daemon(monkeypatch)
    rc = main(
        [
            "--data-root",
            str(tmp_path / "data"),
            "live",
            "run",
            "--export",
            "latest",
            "--enabled",
            "--i-accept-live-risk",
        ]
    )
    error = _error_document(capsys.readouterr().err)
    assert rc == 2
    assert error["error_type"] == "CommandRefused"
    assert error["command"] == "live run"
    assert "'latest'" in str(error["error"]) and "looked for" in str(error["error"])


def test_live_run_missing_directory_refuses_with_exit_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _forbid_daemon(monkeypatch)
    missing = tmp_path / "no_such_bundle"
    rc = main(
        ["--data-root", str(tmp_path / "data"), "live", "run", "--export", str(missing)]
    )
    assert rc == 2
    assert _error_document(capsys.readouterr().err)["error_type"] == "CommandRefused"


@pytest.mark.parametrize(
    ("flags", "needle"),
    [
        ([], "--i-accept-live-risk"),
        (["--enabled"], "--i-accept-live-risk"),
        (["--i-accept-live-risk"], "--enabled"),
    ],
)
def test_live_run_missing_authority_refuses_with_exit_2(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    flags: list[str],
    needle: str,
) -> None:
    _forbid_daemon(monkeypatch)
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    rc = main(
        [
            "--data-root",
            str(tmp_path / "data"),
            "live",
            "run",
            "--export",
            str(bundle),
            *flags,
        ]
    )
    error = _error_document(capsys.readouterr().err)
    assert rc == 2
    assert error["error_type"] == "CommandRefused"
    assert needle in str(error["error"])
    assert not (tmp_path / "data").exists()  # refused before any side effect


def test_live_run_missing_credentials_refuses_with_exit_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _forbid_daemon(monkeypatch)
    monkeypatch.delenv(WALLET_ENV, raising=False)
    monkeypatch.delenv(KEY_ENV, raising=False)
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    rc = main(
        [
            "--data-root",
            str(tmp_path / "data"),
            "live",
            "run",
            "--export",
            str(bundle),
            "--enabled",
            "--i-accept-live-risk",
        ]
    )
    error = _error_document(capsys.readouterr().err)
    assert rc == 2
    assert error["error_type"] == "CommandRefused"
    assert WALLET_ENV in str(error["error"])


@pytest.mark.parametrize("reference", ["candidate-1", "latest"])
def test_live_run_resolves_candidate_id_and_latest(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    reference: str,
) -> None:
    from hypervector.commands import exports

    data_root = tmp_path / "data"
    bundle = data_root / "exports" / "candidate-1"
    bundle.mkdir(parents=True)
    monkeypatch.setattr(exports, "latest_export", lambda _root: bundle)
    monkeypatch.setenv(WALLET_ENV, "0xabc")
    monkeypatch.setenv(KEY_ENV, "not-a-real-key")
    seen: dict[str, object] = {}

    def fake_daemon(**kwargs: object) -> SimpleNamespace:
        seen.update(kwargs)
        return SimpleNamespace(
            execution_mode="live",
            run_id="run-1",
            export_dir=kwargs["export_dir"],
            decisions_path=tmp_path / "decisions.jsonl",
            warm_bars=0,
            live_bars=0,
            bars_processed=0,
            fills_count=0,
            places_count=0,
            catchup_bars=0,
            stop_reason="max_live_bars",
            cancel_attempted=False,
            cancel_ok=None,
            cancel_error=None,
        )

    monkeypatch.setattr("hypervector.live.runner.start_live_daemon", fake_daemon)
    rc = main(
        [
            "--data-root",
            str(data_root),
            "live",
            "run",
            "--export",
            reference,
            "--enabled",
            "--i-accept-live-risk",
            "--max-live-bars",
            "0",
        ]
    )
    out = capsys.readouterr()
    assert rc == 0, out.err
    assert seen["export_dir"] == bundle.resolve()
    assert json.loads(out.out)["export_dir"] == str(bundle.resolve())
    assert "not-a-real-key" not in out.out + out.err


def test_skill_documents_live_run_references_and_refusal_code() -> None:
    bullet = SKILL[SKILL.index("- **`live run`**") :]
    bullet = _flat(bullet[: bullet.index("\n- **")])
    assert "`latest`" in bullet and "candidate id" in bullet
    assert "exit 2" in bullet


# --------------------------------------------------------------------------- #
# README stdout contract: book-record prints one document; two non-JSON outputs
# --------------------------------------------------------------------------- #


def _stdout_contract() -> str:
    section = _section(README, "Output contract and exit codes")
    return section[section.index("- **stdout.**") : section.index("- **stderr.**")]


def test_book_record_prints_one_summary_document(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_recorder(root: Path, **kwargs: object) -> dict[str, object]:
        return {"ok": True, "snapshots": 2, "stop_reason": "max_snapshots"}

    monkeypatch.setattr("hypervector.data.book_record.run_book_recorder", fake_recorder)
    rc = main(
        [
            "--data-root",
            str(tmp_path / "data"),
            "data",
            "book-record",
            "--symbol",
            "BTC",
            "--max-snapshots",
            "2",
        ]
    )
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["snapshots"] == 2
    contract = _stdout_contract()
    streaming = contract.split("stream JSON lines instead:", 1)[1].split("\n\n", 1)[0]
    assert "`data hip3-roster`" in streaming
    assert "book-record" not in streaming
    assert "`data book-record` writes its snapshots to `cache/book/*.jsonl`" in _flat(
        contract
    )


def test_print_launchd_writes_plist_xml_and_readme_says_so(
    tmp_path: Path,
    capsysbinary: pytest.CaptureFixture[bytes],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)  # the supervisor chdirs; restore afterwards
    rc = main(["live", "supervisor", "print-launchd", "--kind", "watch"])
    assert rc == 0
    assert capsysbinary.readouterr().out.startswith(b"<?xml")
    contract = _stdout_contract()
    assert "`live supervisor print-launchd`" in contract
    assert "plist XML" in contract


def test_drain_archive_prints_plain_text_and_readme_says_so(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from contextlib import nullcontext

    from hypervector.operations import cohort_transition_drain_archive as drain

    target = tmp_path / "archive" / "transition_drain_x.json"
    monkeypatch.setattr(
        drain, "archive_completed_transition_drain", lambda **_kwargs: target
    )
    args = drain.build_parser().parse_args(
        ["--state", str(tmp_path / "transition_drain.json"), "--expected-run-id", "r"]
    )
    drain.run_archive(args, lock_fn=lambda _path: nullcontext(_path))
    line = capsys.readouterr().out
    assert line.startswith("transition drain dry-run: source=")
    with pytest.raises(json.JSONDecodeError):
        json.loads(line)
    contract = _stdout_contract()
    assert "`live drain-archive`" in contract
    assert "Every command prints JSON." not in README


# --------------------------------------------------------------------------- #
# Error output: import-cohort reports failures on stderr, before creating a DB
# --------------------------------------------------------------------------- #


def test_import_cohort_failure_goes_to_stderr_and_creates_no_database(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from hypervector.operations import multi_asset_bidirectional_research_import as imp

    database = tmp_path / "research" / "market.duckdb"
    rc = imp.main(
        ["--ledger-root", str(tmp_path / "nope"), "--database", str(database)]
    )
    captured = capsys.readouterr()
    assert rc == 1
    assert captured.out == ""
    error = json.loads(captured.err)
    assert error["ok"] is False
    assert "cohort ledger root is missing" in error["error"]
    assert not database.exists()


def test_readme_error_contract_names_the_reduced_handler_document() -> None:
    section = _section(README, "Output contract and exit codes")
    errors = _flat(
        section[section.index("- **Errors**") : section.index("- **Artifacts.**")]
    )
    assert '{"ok": false, "error": "..."}' in errors
    assert "exit code is the contract" in errors


# --------------------------------------------------------------------------- #
# Leverage: one altcoin rule across sizing, Nautilus and the README
# --------------------------------------------------------------------------- #


def test_altcoin_leverage_ceiling_is_shared_by_sizing_and_nautilus() -> None:
    from hypervector.nautilus import venue_spec
    from hypervector.sweep import sizing

    assert sizing.ALTCOIN_MAX_LEVERAGE == venue_spec.ALTCOIN_MAX_LEVERAGE == 15.0
    assert sizing.venue_leverage_cap("XRP") == sizing.DEFAULT_ALT_LEVERAGE_CAP == 10.0
    # Venue metadata may lift a non-charter perp to the ceiling, never above it.
    assert sizing.venue_leverage_cap("XRP", 20) == 15.0
    assert sizing.venue_leverage_cap("XRP", 12) == 12.0
    assert sizing.venue_leverage_cap("XRP", 3) == 3.0
    meta = {"instrument": {"szDecimals": 0, "maxLeverage": 20}}
    assert venue_spec.resolve_venue_spec("XRP", meta).venue_max_leverage == 15.0
    with pytest.raises(ValueError, match="venue cap of 15x"):
        sizing.validate_leverage(20.0, symbol="XRP", venue_max_leverage=20)


def test_readme_states_the_altcoin_default_and_ceiling() -> None:
    leverage = README[README.index("- **Leverage**") :]
    leverage = _flat(leverage[: leverage.index("\n- **")])
    assert "10x" in leverage and "15x" in leverage
    assert "maxLeverage" in leverage


# --------------------------------------------------------------------------- #
# SKILL: --allow-partial is scoped to the commands that declare it
# --------------------------------------------------------------------------- #


def _accepts(argv: list[str], flag: str) -> bool:
    _known, extra = build_parser().parse_known_args(argv)
    return flag not in extra


def test_skill_scopes_allow_partial_to_the_commands_that_take_it() -> None:
    window = ["--symbol", "BTC", "--start", "2026-01-01T00:00:00Z"]
    window += ["--end", "2026-01-02T00:00:00Z"]
    takes = {
        kind
        for kind in ("candle", "trade", "book", "price", "liquidation")
        if _accepts(["archive", f"{kind}-fetch", *window, "--allow-partial"], "--allow-partial")
    }
    assert takes == {"trade", "book", "liquidation"}
    bullet = SKILL[SKILL.index("- **Window bounds.**") :]
    bullet = _flat(bullet[: bullet.index("\n- **")])
    for kind in sorted(takes):
        assert f"`{kind}-fetch`" in bullet
    assert "`candle-fetch` and `price-fetch` have no partial option" in bullet


# --------------------------------------------------------------------------- #
# README legacy table: every listed old name parses, and every alias is listed
# --------------------------------------------------------------------------- #


def _legacy_table_names() -> set[str]:
    section = _section(README, "Legacy names")
    table = section[: section.index("Old flag spellings")]
    names: set[str] = set()
    for row in table.splitlines():
        if not row.startswith("| `"):
            continue
        old_cell = row.split("|")[1]
        names.update(re.findall(r"`([^`]+)`", old_cell))
    return names


def _listed_legacy_names() -> set[str]:
    from hypervector.commands.registry import DEFAULT_ACTION

    kinds = ("candle", "trade", "book", "price", "liquidation")
    listed: set[str] = set()
    for name in _legacy_table_names():
        if name.endswith(" <options>"):
            assert name.removesuffix(" <options>") in DEFAULT_ACTION, name
            continue
        if "<kind>" in name:
            listed.update(name.replace("<kind>", kind) for kind in kinds)
            continue
        listed.add(name)
    return listed


@pytest.mark.xfail(
    strict=True,
    reason=(
        "README still lists aliases of commands removed with the old strategies "
        "(paper shadow, regime align, tune regime); the docs rewrite pass drops them"
    ),
)
def test_readme_legacy_names_all_parse() -> None:
    unknown = sorted(_listed_legacy_names() - set(LEGACY_ALIASES))
    assert unknown == [], f"README legacy names that do not parse: {unknown}"


def test_readme_legacy_table_covers_every_alias() -> None:
    missing = sorted(set(LEGACY_ALIASES) - _listed_legacy_names())
    assert missing == [], f"legacy aliases missing from the README table: {missing}"


# --------------------------------------------------------------------------- #
# HANDOFF: the cache flags are named only on commands that accept them
# --------------------------------------------------------------------------- #


def test_handoff_scopes_the_cache_flags_to_commands_that_take_them() -> None:
    sentence = HANDOFF[HANDOFF.index("- **Data and fees.**") :]
    sentence = _flat(sentence[: sentence.index("\n- **")])
    takes_pin = ["data history", "backtest run", "tune strategy", "regime eval"]
    for command in takes_pin:
        assert _accepts([*command.split(), "--pin-cache"], "--pin-cache"), command
    refuses_pin = {
        "pipeline run": ["--strategy", "test_sma_cross_long"],
        "nautilus run": ["--export", "x"],
        "paper run": ["--export", "x"],
        "model train": ["--export", "x"],
    }
    for command, extra in refuses_pin.items():
        argv = [*command.split(), *extra]
        assert not _accepts([*argv, "--pin-cache"], "--pin-cache"), command
        assert not _accepts([*argv, "--max-cache-age-hours", "1"], "--max-cache-age-hours")
        assert f"`{command}`" in sentence, command
    assert "`paper run` and `model train` take neither" in sentence
    assert _accepts(["pipeline", "run", "--strategy", "s", "--no-network"], "--no-network")
    assert _accepts(["nautilus", "run", "--export", "x", "--no-network"], "--no-network")


# --------------------------------------------------------------------------- #
# Exit-code table: the service-specific codes of supervisor status and monitor
# --------------------------------------------------------------------------- #


def _other_exit_row() -> str:
    section = _section(README, "Output contract and exit codes")
    return next(line for line in section.splitlines() if line.startswith("| other |"))


def test_supervisor_status_exits_1_when_unhealthy_and_readme_says_so(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from dataclasses import dataclass, field

    from hypervector_supervision import cohort_backend_supervisor as supervisor

    @dataclass(frozen=True)
    class Report:
        problems: list[str] = field(default_factory=lambda: ["checkpoint_stale"])

        @property
        def healthy(self) -> bool:
            return not self.problems

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(supervisor, "evaluate_health", lambda *_a, **_k: Report())
    rc = main(["live", "supervisor", "status"])
    assert rc == 1
    assert json.loads(capsys.readouterr().out)["healthy"] is False
    row = _other_exit_row()
    assert "`live supervisor status` 0 = healthy, 1 = unhealthy" in row


def test_live_monitor_maps_missing_inputs_to_2_and_readme_says_so(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = main(
        [
            "--data-root",
            str(tmp_path / "data"),
            "live",
            "monitor",
            "--config",
            str(tmp_path / "missing.toml"),
            "--source-checkpoint",
            str(tmp_path / "missing.json"),
        ]
    )
    assert rc == 2
    assert "live monitor refused" in capsys.readouterr().err
    row = _other_exit_row()
    assert "`live monitor` 2 =" in row
    assert "OSError" in row


# --------------------------------------------------------------------------- #
# Transition guide step 8: paste the printed bundle path; full log line format
# --------------------------------------------------------------------------- #


def test_transition_guide_matches_the_prestart_backup_log_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from hypervector.operations.cohort_live_construction import _announce_backup

    printed = Path("data/backups/bidirectional_cohort/prestart_20261017T000000Z_abc")
    _announce_backup(
        SimpleNamespace(
            path=printed,
            manifest_sha256="m" * 64,
            implementation_file_count=3,
            implementation_sha256="i" * 64,
            strategy_changed=True,
        )
    )
    line = capsys.readouterr().out.strip()
    fields = re.findall(r"(\w+)=", line)
    example = next(
        row
        for row in TRANSITION_GUIDE.splitlines()
        if row.startswith("pre-start backup verified:")
    )
    assert re.findall(r"(\w+)=", example) == fields
    verify_rows = [
        row
        for row in TRANSITION_GUIDE.splitlines()
        if "live backup-verify --bundle" in row and row.lstrip().startswith("$HV")
    ]
    assert any("pre-start log line" in row for row in verify_rows)  # step 8
    for row in verify_rows:
        argument = row.split("--bundle", 1)[1].strip()
        # The log prints the full path; the placeholder must not add a prefix.
        assert argument.startswith("<"), row
        assert "prestart_<" not in argument, row
