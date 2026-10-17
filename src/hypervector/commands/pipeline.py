"""``pipeline run``, ``pipeline show`` and ``pipeline list``.

``pipeline run`` is one foreground process that calls the stage libraries
in-process and records, for every stage, the equivalent single command so any
stage can be re-run by hand. It never starts a daemon, never constructs a venue
client and cannot reach ``paper observe``, ``paper shadow``, ``live *``,
launchctl or any execution module.

Module-level imports are the standard library plus the CLI refusal type, so
``pipeline show`` and ``pipeline list`` never load an engine. Engines are
imported inside the stage that needs them, and only these entry points are used
(the stage allowlist):

- validate: the strategy registry, ``commands.exports.resolve_export``
- data: ``data.pipeline.load_research_history``
- search: ``sweep.autotune.run_autotune`` or ``commands.sweep.run_sweep``
- export: ``export.schema.validate_export_dir``, ``nautilus.load_export.load_strategy_loadout``
- nautilus: the ``nautilus run`` symbol predicate, ``nautilus.config_stub.phase2_check_report``
  (without the engine probe), ``nautilus.runner.run_phase2_backtest``
- model: ``commands.model.train_metalabel_bundle``
- paper: paper constants by default; ``paper.runner.start_paper_daemon`` (shadow)
  only with ``--paper-bars``
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
from contextlib import redirect_stdout
from dataclasses import dataclass
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import re
import shlex
import sys
import time
from typing import Any

from hypervector.commands.common import CommandRefused
from hypervector.config import DEFAULT_LOOKBACK, DEFAULT_SYMBOL, DEFAULT_TIMEFRAME

MANIFEST_SCHEMA = 1
MANIFEST = "pipeline.json"
RUNS_DIR = Path("runs") / "pipeline"
LATEST = "latest"
STAGES: tuple[str, ...] = (
    "validate",
    "data",
    "search",
    "export",
    "nautilus",
    "model",
    "paper",
)
PAPER_BARS_MIN = 1
PAPER_BARS_MAX = 1440
DEFAULT_CONVICTION = 0.5
EXPORT_PLACEHOLDER = "<export>"
EVIDENCE_NOTE = (
    "evidence traps not computed (ex-top-3, de-selection, both partitions, "
    "trigger count): untested research, not capital justification"
)
PARITY_NOTE = (
    "report-only: no threshold and never a gate; VectorBT and Nautilus model "
    "fills differently, so disagreement is expected"
)
NO_ORDERS_NOTE = (
    "paper stage is shadow with no_submit: it never places venue orders and "
    "never builds an execution client"
)
EXPORT_START_NOTE = (
    "started from an existing bundle: data and search skipped, window not pinned"
)
WINDOW_FIELDS: tuple[str, ...] = ("symbol", "timeframe", "lookback_days", "bars")
MODEL_METRICS: tuple[str, ...] = (
    "n_labels",
    "class_balance",
    "n_wf_folds",
    "oos_log_loss_mean",
    "oos_auc_mean",
    "oos_baseline_log_loss_mean",
    "beat_baseline",
)


# --- plan (stage 0) -----------------------------------------------------------------


@dataclass(frozen=True)
class Plan:
    """A validated request: every stage-0 check passed and nothing was written."""

    pipeline_id: str
    created_at: datetime
    data_root: Path
    out_dir: Path
    strategy: str
    role: str
    symbol: str
    timeframe: str
    lookback: int
    export_dir: Path | None
    nautilus_unsupported: str | None
    args: argparse.Namespace

    @property
    def manifest_path(self) -> Path:
        return self.out_dir / MANIFEST


def cmd_run(args: argparse.Namespace) -> int:
    """Validate, then print the plan (``--dry-run``) or run every stage in-process."""
    plan = validate_request(args)
    manifest = new_manifest(plan)
    if args.dry_run:
        manifest["status"] = "planned"
        manifest["dry_run"] = True
        _emit(manifest)
        return 0
    return PipelineRun(plan, manifest).run()


def validate_request(args: argparse.Namespace) -> Plan:
    """Stage 0: refuse (exit 2) before any work or write."""
    root = Path(args.data_root)
    paper_bars = args.paper_bars
    if paper_bars is not None and not PAPER_BARS_MIN <= paper_bars <= PAPER_BARS_MAX:
        raise CommandRefused(
            f"--paper-bars must be between {PAPER_BARS_MIN} and {PAPER_BARS_MAX}"
        )
    if paper_bars is not None and args.no_network:
        raise CommandRefused(
            "--paper-bars reads live mainnet candles; it cannot run with --no-network"
        )
    if args.force and args.no_network:
        raise CommandRefused("--refresh re-fetches history; --no-network forbids it")
    if not 0.0 <= float(args.conviction) <= 1.0:
        raise CommandRefused("--conviction is a fraction between 0 and 1")
    export_dir = None
    bundle: dict[str, Any] = {}
    if args.export is not None:
        if args.force:
            raise CommandRefused(
                "--refresh applies only to the data stage, which --export skips"
            )
        from hypervector.commands.exports import resolve_export

        export_dir = resolve_export(args.export, root)
        bundle = _bundle_identity(export_dir)
    role = _registered_role(args.strategy)
    if bundle.get("strategy") and bundle["strategy"] != args.strategy:
        raise CommandRefused(
            f"--strategy {args.strategy} does not match the bundle's strategy "
            f"{bundle['strategy']} ({export_dir})"
        )
    symbol = _pick("--symbol", args.symbol, bundle.get("symbol"), DEFAULT_SYMBOL)
    timeframe = _pick(
        "--timeframe", args.timeframe, bundle.get("timeframe"), DEFAULT_TIMEFRAME
    )
    lookback = (
        int(args.lookback)
        if args.lookback is not None
        else int(bundle.get("lookback_days") or DEFAULT_LOOKBACK)
    )
    if export_dir is None:
        _validate_search(args, role)
    created = datetime.now(UTC).replace(microsecond=0)
    pipeline_id = make_pipeline_id(created, args.strategy, symbol, timeframe)
    out_dir = (
        Path(args.out_dir).expanduser()
        if args.out_dir is not None
        else root / RUNS_DIR / pipeline_id
    ).resolve()
    if out_dir.exists():
        raise CommandRefused(f"output directory already exists: {out_dir}")
    return Plan(
        pipeline_id=pipeline_id,
        created_at=created,
        data_root=root,
        out_dir=out_dir,
        strategy=str(args.strategy),
        role=role,
        symbol=symbol,
        timeframe=timeframe,
        lookback=lookback,
        export_dir=export_dir,
        nautilus_unsupported=None
        if args.no_nautilus
        else _nautilus_unsupported(export_dir, symbol),
        args=args,
    )


def _registered_role(name: str) -> str:
    from hypervector.strategies import register_all_strategies
    from hypervector.strategies.registry import get_strategy

    register_all_strategies()
    try:
        return str(get_strategy(name).role)
    except KeyError as exc:
        raise CommandRefused(f"unknown strategy: {name}") from exc


def _validate_search(args: argparse.Namespace, role: str) -> None:
    if args.search == "sweep" and role not in ("uptrend", "downtrend"):
        raise CommandRefused(
            f"--search sweep needs an uptrend or downtrend strategy; "
            f"{args.strategy} has role={role!r} (use --search tune)"
        )
    if args.search == "tune":
        if int(args.n_trials) < 1:
            raise CommandRefused("--n-trials must be at least 1")
        from importlib.util import find_spec

        if args.sampler == "optuna" and find_spec("optuna") is None:
            raise CommandRefused(
                "--sampler optuna needs the optional 'optuna' package "
                "(install hypervector[optuna]) or use --sampler karpathy"
            )


def _pick(flag: str, given: str | None, bundle: object, default: str) -> str:
    """The flag value, else the bundle's, else the default; a conflict is refused."""
    if given is None:
        return str(bundle) if bundle not in (None, "") else default
    if bundle not in (None, "") and str(given).lower() != str(bundle).lower():
        raise CommandRefused(f"{flag} {given} conflicts with the bundle's {bundle}")
    return str(given)


def _bundle_identity(path: Path) -> dict[str, Any]:
    """Strategy, market and window recorded in a bundle (read leniently)."""
    meta = _read_object(path / "meta.json")
    params = _read_object(path / "params.json")
    try:
        lookback = int(meta["lookback_days"]) if "lookback_days" in meta else None
    except (TypeError, ValueError):
        lookback = None
    return {
        "strategy": params.get("strategy") or meta.get("strategy"),
        "symbol": meta.get("symbol"),
        "timeframe": meta.get("timeframe"),
        "lookback_days": lookback,
    }


def _nautilus_unsupported(export_dir: Path | None, symbol: str) -> str | None:
    """Why ``nautilus run`` would refuse this bundle (the engine's resolver), else None."""
    from hypervector.commands.nautilus import _unsupported_symbol
    from hypervector.nautilus.errors import UnsupportedNautilusSymbol
    from hypervector.nautilus.venue_spec import resolve_venue_spec

    if export_dir is not None:
        refusal = _unsupported_symbol(export_dir)
        return None if refusal is None else str(refusal)
    try:
        resolve_venue_spec(symbol)
    except UnsupportedNautilusSymbol as exc:
        return f"{exc}; the search bundle will be {symbol}"
    return None


def make_pipeline_id(created: datetime, strategy: str, symbol: str, tf: str) -> str:
    """``pl-<UTC yyyymmddTHHMMSSZ>-<strategy>-<symbol>-<tf>``, filesystem safe."""
    stamp = created.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    parts = [_safe(part) for part in (strategy, symbol, tf)]
    return "-".join(["pl", stamp, *parts])


def _safe(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.]+", "_", str(text)).strip("_") or "x"


# --- manifest -----------------------------------------------------------------------


def new_manifest(plan: Plan) -> dict[str, Any]:
    """The initial manifest: the request, every stage with its command, the notes."""
    args = plan.args
    export_ref = (
        _export_ref(plan.export_dir, plan.data_root)
        if plan.export_dir
        else EXPORT_PLACEHOLDER
    )
    stages = []
    for name in STAGES:
        entry = _stage_entry(name, _stage_argv(plan, name, export_ref))
        reason = _planned_skip(plan, name)
        if reason is not None:
            entry.update(status="skipped", reason=reason[0])
            if reason[1]:
                entry["detail"] = reason[1]
        stages.append(entry)
    stages[0].update(
        status="ok",
        exit_code=0,
        metrics={"checks": _checks(plan)},
        started_at=_iso(plan.created_at),
        ended_at=_iso(plan.created_at),
    )
    notes = [EVIDENCE_NOTE, PARITY_NOTE, NO_ORDERS_NOTE]
    if plan.export_dir is not None:
        notes.append(EXPORT_START_NOTE)
    return {
        "schema": MANIFEST_SCHEMA,
        "pipeline_id": plan.pipeline_id,
        "created_at_utc": _iso(plan.created_at),
        "data_root": str(plan.data_root.resolve()),
        "out_dir": str(plan.out_dir),
        "manifest_path": str(plan.manifest_path),
        "request": {
            "strategy": plan.strategy,
            "role": plan.role,
            "symbol": plan.symbol,
            "timeframe": plan.timeframe,
            "lookback_days": plan.lookback,
            "strict_hl_only": bool(args.strict_hl_only),
            "refresh": bool(args.force),
            "no_network": bool(args.no_network),
            "fee_model": args.fee_model,
            "search": args.search,
            "sampler": args.sampler,
            "n_trials": args.n_trials,
            "export": args.export,
            "no_nautilus": bool(args.no_nautilus),
            "conviction": float(args.conviction),
            "train_model": bool(args.train_model),
            "paper_bars": args.paper_bars,
            "out_dir": str(plan.out_dir),
        },
        "window": None,
        "export_dir": str(plan.export_dir) if plan.export_dir else None,
        "candidate_id": plan.export_dir.name if plan.export_dir else None,
        "stages": stages,
        "parity": None,
        "status": "running",
        "next": [],
        "notes": notes,
    }


def _stage_entry(name: str, argv: list[str]) -> dict[str, Any]:
    return {
        "stage": name,
        "status": "not_started",
        "reason": None,
        "argv": argv,
        "started_at": None,
        "ended_at": None,
        "exit_code": None,
        "artifacts": {},
        "metrics": {},
    }


def _planned_skip(plan: Plan, name: str) -> tuple[str, str | None] | None:
    args = plan.args
    if name in ("data", "search") and plan.export_dir is not None:
        return "started_from_export", None
    if name == "nautilus" and args.no_nautilus:
        return "no_nautilus_flag", None
    if name == "nautilus" and plan.nautilus_unsupported:
        return "unsupported_symbol", plan.nautilus_unsupported
    if name == "model" and not args.train_model:
        return "not_requested", None
    return None


def _checks(plan: Plan) -> list[str]:
    args = plan.args
    checks = [f"strategy {plan.strategy} is registered (role={plan.role})"]
    if plan.export_dir is not None:
        checks.append(f"--export resolved to {plan.export_dir}")
    elif args.search == "sweep":
        checks.append(f"sweep track {plan.role} matches the strategy role")
    else:
        checks.append(f"sampler {args.sampler} is available")
    checks.append(f"output directory {plan.out_dir} does not exist")
    if args.paper_bars is not None:
        checks.append(f"--paper-bars {args.paper_bars} is within 1..1440")
    return checks


def write_manifest(path: Path, manifest: Mapping[str, Any]) -> None:
    """Replace ``path`` atomically: write a sibling temp file, fsync, rename."""
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with open(temp, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(manifest, indent=2, default=str) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def _emit(manifest: Mapping[str, Any]) -> None:
    print(json.dumps(manifest, indent=2, default=str))


# --- stage commands -------------------------------------------------------------------


def _cli(root: Path, *words: object) -> list[str]:
    """Canonical argv for one command, with the data root when it is not ./data."""
    prefix = [] if Path(root) == Path("data") else ["--data-root", str(root)]
    return ["hypervector", *prefix, *(str(word) for word in words)]


def _stage_argv(plan: Plan, stage: str, export_ref: str) -> list[str]:
    """The single command that does the same work as ``stage``."""
    args = plan.args
    if stage == "validate":
        return _cli(plan.data_root, "pipeline", "run", *_pipeline_flags(plan))
    if stage == "paper":
        model = plan.out_dir / "model" if args.train_model else None
        return _paper_argv(plan, export_ref, model=model)
    window = ("--lookback-days", plan.lookback)
    market = ("--symbol", plan.symbol, "--timeframe", plan.timeframe, *window)
    hl_only = ("--strict-hl-only",) if args.strict_hl_only else ()
    refresh = ("--refresh",) if args.force else ()
    fees = ("--fee-model", args.fee_model)
    bundle = ("--export", export_ref)
    if args.search == "sweep":
        track = ("backtest", "sweep", "--track", plan.role)
        search = (*track, "--strategy", plan.strategy, *market, *fees, *hl_only)
        search += _conviction(args)
    else:
        tune = ("tune", "strategy", "--strategy", plan.strategy, *market, *fees)
        search = (*tune, "--n-trials", args.n_trials, "--sampler", args.sampler)
        search += hl_only
    words: dict[str, tuple[object, ...]] = {
        "data": ("data", "history", *market, *hl_only, *refresh),
        "search": search,
        "export": ("export", "validate", *bundle),
        "nautilus": ("nautilus", "run", *bundle, *window)
        + (*_conviction(args), "--no-network"),
        "model": (
            "model",
            "train",
            *bundle,
            *window,
            "--out-dir",
            plan.out_dir / "model",
        ),
    }
    return _cli(plan.data_root, *words[stage])


def _conviction(args: argparse.Namespace) -> tuple[object, ...]:
    """``--conviction C`` only when it differs from every stage's default."""
    if float(args.conviction) == DEFAULT_CONVICTION:
        return ()
    return ("--conviction", args.conviction)


def _paper_argv(plan: Plan, export_ref: str, *, model: Path | None) -> list[str]:
    args = plan.args
    words: list[object] = ["paper", "run", "--export", export_ref, "--mode", "shadow"]
    if args.paper_bars is not None:
        words += ["--max-live-bars", args.paper_bars]
    words += _conviction(args)
    if model is not None:
        words += ["--metalabel-bundle", model, "--metalabel-mode", "observe"]
    return _cli(plan.data_root, *words)


def _pipeline_flags(plan: Plan) -> list[object]:
    """This request as ``pipeline run`` flags, ending with ``--dry-run`` (the plan)."""
    args = plan.args
    flags: list[object] = ["--strategy", plan.strategy]
    if plan.export_dir is not None:
        flags += ["--export", plan.export_dir]
    else:
        flags += ["--symbol", plan.symbol, "--timeframe", plan.timeframe]
        flags += ["--lookback-days", plan.lookback, "--search", args.search]
        flags += ["--fee-model", args.fee_model]
        if args.search == "tune":
            flags += ["--sampler", args.sampler, "--n-trials", args.n_trials]
    switches = {
        "--strict-hl-only": args.strict_hl_only and plan.export_dir is None,
        "--refresh": args.force,
        "--no-network": args.no_network,
        "--no-nautilus": args.no_nautilus,
        "--train-model": args.train_model,
    }
    flags += [flag for flag, enabled in switches.items() if enabled]
    flags += _conviction(args)
    if args.paper_bars is not None:
        flags += ["--paper-bars", args.paper_bars]
    if args.out_dir is not None:
        flags += ["--out-dir", plan.out_dir]
    return [*flags, "--dry-run"]


def _export_ref(export_dir: Path, data_root: Path) -> str:
    """A candidate id when the bundle lives under ``<root>/exports``, else its path."""
    if export_dir.parent == (Path(data_root) / "exports").resolve():
        return export_dir.name
    return str(export_dir)


# --- run ---------------------------------------------------------------------------


class StageSkipped(Exception):
    """Raised inside a stage that decides at run time not to do its work."""

    def __init__(self, reason: str, detail: str | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.detail = detail


class PipelineRun:
    """Execute the planned stages in order, writing the manifest after each one."""

    def __init__(self, plan: Plan, manifest: dict[str, Any]) -> None:
        self.plan = plan
        self.args = plan.args
        self.root = plan.data_root
        self.manifest = manifest
        self.export_dir: Path | None = plan.export_dir
        self.export_report: dict[str, Any] = {}
        self.loadout: Any = None
        self.model_dir: Path | None = None

    def run(self) -> int:
        """0 when every requested stage completed; 1 on the first technical failure."""
        self.plan.out_dir.mkdir(parents=True, exist_ok=False)
        self._write()
        steps: Sequence[tuple[str, Callable[[dict[str, Any]], None]]] = (
            ("data", self._data),
            ("search", self._search),
            ("export", self._export),
            ("nautilus", self._nautilus),
            ("model", self._model),
            ("paper", self._paper),
        )
        for name, step in steps:
            entry = self._entry(name)
            if entry["status"] == "skipped":
                _progress(f"{name}: skipped ({entry['reason']})")
                continue
            if not self._execute(entry, step):
                return 1
        self.manifest["status"] = "ok"
        self._write()
        _emit(self.manifest)
        return 0

    def _execute(
        self, entry: dict[str, Any], step: Callable[[dict[str, Any]], None]
    ) -> bool:
        name = entry["stage"]
        _progress(f"{name}: started")
        entry["started_at"] = _iso(datetime.now(UTC))
        began = time.monotonic()
        try:
            with redirect_stdout(sys.stderr):
                step(entry)
        except StageSkipped as skip:
            entry.update(status="skipped", reason=skip.reason)
            if skip.detail:
                entry["detail"] = skip.detail
        except KeyboardInterrupt:
            self._fail(entry, "interrupted", "KeyboardInterrupt", 130)
            raise
        # A library calling sys.exit inside a stage did not complete it: record a
        # technical failure instead of leaving the manifest "running".
        except (Exception, SystemExit) as exc:  # noqa: BLE001 - technical (exit 1)
            self._fail(entry, f"{type(exc).__name__}: {exc}", type(exc).__name__, 1)
            _progress(f"{name}: failed ({type(exc).__name__}: {exc})")
            print(
                json.dumps(
                    {
                        "ok": False,
                        "command": "pipeline run",
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                        "stage": name,
                        "manifest": str(self.plan.manifest_path),
                    },
                    default=str,
                ),
                file=sys.stderr,
            )
            _emit(self.manifest)
            if os.environ.get("HYPERVECTOR_DEBUG") == "1":
                raise
            return False
        else:
            entry.update(status="ok", exit_code=0)
        entry["ended_at"] = _iso(datetime.now(UTC))
        entry["metrics"]["seconds"] = round(time.monotonic() - began, 3)
        self._write()
        _progress(f"{name}: {entry['status']}")
        return True

    def _fail(
        self, entry: dict[str, Any], reason: str, error_type: str, code: int
    ) -> None:
        entry.update(
            status="failed",
            reason=reason,
            error_type=error_type,
            exit_code=code,
            ended_at=_iso(datetime.now(UTC)),
        )
        self.manifest["status"] = "failed"
        self._write()

    def _entry(self, name: str) -> dict[str, Any]:
        return next(e for e in self.manifest["stages"] if e["stage"] == name)

    def _write(self) -> None:
        write_manifest(self.plan.manifest_path, self.manifest)

    def _set_export(self, path: Path) -> None:
        self.export_dir = Path(path).resolve()
        ref = _export_ref(self.export_dir, self.root)
        self.manifest["export_dir"] = str(self.export_dir)
        self.manifest["candidate_id"] = self.export_dir.name
        for entry in self.manifest["stages"]:
            entry["argv"] = [
                ref if word == EXPORT_PLACEHOLDER else word for word in entry["argv"]
            ]

    # --- stage 1: data ----------------------------------------------------------

    def _data(self, entry: dict[str, Any]) -> None:
        """Pin the research window; the only stage that may refresh or fetch."""
        from hypervector.commands.market import _bar_window
        from hypervector.data.pipeline import cache_key, load_research_history

        plan, args = self.plan, self.args
        frame, provenance = load_research_history(
            self.root,
            symbol=plan.symbol,
            timeframe=plan.timeframe,
            lookback_days=plan.lookback,
            strict_hl_only=bool(args.strict_hl_only),
            force_refresh=bool(args.force),
            allow_network=not args.no_network,
        )
        if len(frame) == 0:
            raise RuntimeError(
                f"no history bars for {plan.symbol} {plan.timeframe} "
                f"lookback={plan.lookback}d"
            )
        start, end = _bar_window(frame)
        key = cache_key(plan.symbol, plan.timeframe, plan.lookback)
        cache_path = _cache_path(self.root, key)
        prov = provenance if isinstance(provenance, dict) else {}
        window = {
            "symbol": plan.symbol,
            "timeframe": plan.timeframe,
            "lookback_days": plan.lookback,
            "start": start,
            "end": end,
            "bars": int(len(frame)),
            "sources": prov.get("sources"),
            "cache_key": key,
            "cache_path": str(cache_path.resolve()),
        }
        self.manifest["window"] = window
        entry["artifacts"] = {"dataset": dict(window)}
        entry["metrics"] = {
            "bars": int(len(frame)),
            "fractions": prov.get("fractions"),
            "gaps": prov.get("gaps"),
            "network": not args.no_network,
            "refresh": bool(args.force),
        }

    # --- stage 2: search --------------------------------------------------------

    def _search(self, entry: dict[str, Any]) -> None:
        """Tune or sweep on the pinned cache key; weak results continue."""
        if self.args.search == "sweep":
            self._sweep(entry)
        else:
            self._tune(entry)

    def _tune(self, entry: dict[str, Any]) -> None:
        from hypervector.sweep.autotune import run_autotune

        plan, args = self.plan, self.args
        result = run_autotune(
            data_root=self.root,
            symbol=plan.symbol,
            timeframe=plan.timeframe,
            lookback_days=plan.lookback,
            strategy_name=plan.strategy,
            n_trials=int(args.n_trials),
            fee_model=args.fee_model,
            sampler=args.sampler,
            strict_hl_only=bool(args.strict_hl_only),
            force_refresh=False,
            export_best=True,
        )
        if result.export_dir is None:
            raise RuntimeError("the tune search exported no strategy bundle")
        self._set_export(Path(result.export_dir))
        entry["artifacts"] = {
            "board": str(result.board_path),
            "export": str(self.export_dir),
        }
        entry["metrics"] = {
            "sampler_used": result.sampler_used,
            "trials": result.n_trials,
            "best": result.best_metrics,
            "best_params": result.best_params,
            "best_exit_cfg": result.best_exit_cfg,
        }

    def _sweep(self, entry: dict[str, Any]) -> None:
        from hypervector.commands.registry import build_parser
        from hypervector.commands.sweep import run_sweep

        namespace = _parse_canonical(build_parser(), entry["argv"])
        namespace.no_network = True  # the data stage pinned the window
        result = run_sweep(namespace, self.plan.role)
        export = result.get("export_dir")
        if not export:
            raise RuntimeError(
                f"sweep run {result.get('run_id')} stored no exportable trial"
            )
        self._set_export(Path(export))
        entry["artifacts"] = {
            "board": result["artifacts"]["board"],
            "export": str(self.export_dir),
            "run_id": result["run_id"],
        }
        entry["metrics"] = {
            key: result.get(key)
            for key in ("run_id", "track", "trials", "ok_trials", "failed_trials")
        }
        entry["metrics"]["best"] = result.get("best")

    # --- stage 3: export --------------------------------------------------------

    def _export(self, entry: dict[str, Any]) -> None:
        """Strict validation and loadout parse; an invalid bundle is a failure."""
        from hypervector.export.schema import validate_export_dir
        from hypervector.nautilus.load_export import load_strategy_loadout

        path = self._require_export()
        report = validate_export_dir(path, strict=True)
        self.loadout = load_strategy_loadout(path, strict=True)
        self.export_report = report
        meta = report.get("meta") or {}
        entry["artifacts"] = {"export": str(path)}
        entry["metrics"] = {
            "strict_valid": True,
            "candidate_id": path.name,
            "strategy": report.get("strategy"),
            "symbol": report.get("symbol"),
            "timeframe": report.get("timeframe"),
            "track": report.get("track"),
            "lookback_days": meta.get("lookback_days"),
            "export_metrics": report.get("metrics"),
        }

    # --- stage 4: nautilus ------------------------------------------------------

    def _nautilus(self, entry: dict[str, Any]) -> None:
        """Offline event replay on the pinned window plus a report-only parity block."""
        path = self._require_export()
        unsupported = _nautilus_unsupported(path, self.plan.symbol)
        if unsupported:
            raise StageSkipped("unsupported_symbol", unsupported)
        from hypervector.nautilus.config_stub import phase2_check_report
        from hypervector.nautilus.runner import run_phase2_backtest

        # No engine probe: it imports Nautilus's Hyperliquid execution-client
        # module and builds an exec client config, which this pipeline never needs.
        check = phase2_check_report(
            path, data_root=self.root, strict=True, probe_nautilus=False
        )
        result = run_phase2_backtest(
            export_dir=path,
            data_root=self.root,
            conviction=float(self.args.conviction),
            lookback_days=self.plan.lookback,
            allow_network=False,
        )
        payload = _read_object(Path(result.report_path))
        entry["artifacts"] = {
            "export": str(path),
            "validation": str(result.report_path),
        }
        entry["metrics"] = {
            "check_ok": bool(check.get("ok", False)),
            "pnl": result.pnl,
            "orders": result.orders_count,
            "bars": payload.get("bars"),
            "lookback_days": self.plan.lookback,
            "network": False,
            "run_id": payload.get("run_id"),
        }
        self.manifest["parity"] = parity_block(
            pinned=self.manifest.get("window"),
            export_report=self.export_report,
            nautilus={
                "pnl": result.pnl,
                "orders": result.orders_count,
                "trades": payload.get("trade_count", payload.get("trades")),
                "window": {
                    "symbol": getattr(self.loadout, "symbol", self.plan.symbol),
                    "timeframe": getattr(
                        self.loadout, "timeframe", self.plan.timeframe
                    ),
                    "lookback_days": self.plan.lookback,
                    "bars": payload.get("bars"),
                },
            },
        )

    # --- stage 5: model ---------------------------------------------------------

    def _model(self, entry: dict[str, Any]) -> None:
        """Walk-forward metalabel training into ``<out-dir>/model``; never installed."""
        from hypervector.commands.model import train_metalabel_bundle
        from hypervector.data.pipeline import cache_key
        from hypervector.ml.walk_forward import InsufficientLabelsError

        path = self._require_export()
        if self.args.no_network:
            # Training loads history cache-first but fetches on a miss; with
            # --no-network a miss must fail here instead of reaching the network.
            key = cache_key(
                self.loadout.symbol, self.loadout.timeframe, self.plan.lookback
            )
            cached = _cache_path(self.root, key)
            if not cached.is_file():
                raise FileNotFoundError(
                    f"offline history cache missing for model training: {cached}"
                )
        try:
            report = train_metalabel_bundle(
                export_dir=path,
                data_root=self.root,
                out_dir=self.plan.out_dir / "model",
                lookback_days=self.plan.lookback,
            )
        except InsufficientLabelsError as exc:
            # Too few entries is a measured result (trade count), not a technical
            # failure: no implicit gate, so record it and hand off without a model.
            entry["metrics"] = {"n_labels": exc.n_labels, "installed": False}
            raise StageSkipped("insufficient_labels", str(exc)) from exc
        self.model_dir = Path(report.get("bundle_dir") or self.plan.out_dir / "model")
        entry["artifacts"] = {"export": str(path), "model": str(self.model_dir)}
        entry["metrics"] = {key: report.get(key) for key in MODEL_METRICS}
        entry["metrics"]["installed"] = False

    # --- stage 6: paper ---------------------------------------------------------

    def _paper(self, entry: dict[str, Any]) -> None:
        """Hand off to paper (default) or run a bounded foreground shadow session."""
        path = self._require_export()
        entry["argv"] = _paper_argv(
            self.plan, _export_ref(path, self.root), model=self.model_dir
        )
        if self.args.paper_bars is None:
            self._paper_handoff(entry, path)
        else:
            self._paper_session(entry, path)
        handoff = shlex.join(_without_bars(entry["argv"]))
        self.manifest["next"].insert(0, handoff)

    def _paper_handoff(self, entry: dict[str, Any], path: Path) -> None:
        from hypervector.paper.fill_models import (
            DEFAULT_MAX_BOOK_AGE_MS,
            FILL_MODEL_L2_WALK_V1,
        )
        from hypervector.paper.order_intent import NETWORK_MAINNET
        from hypervector.strategies.hypervelocity_contract import (
            is_hypervelocity_strategy,
        )

        loadout = self.loadout
        identity = {
            "execution_mode": "shadow",
            "no_submit": True,
            "sandbox_enabled": False,
            "network": NETWORK_MAINNET,
            "export_dir": str(path),
            "candidate_id": path.name,
            "export_run_id": loadout.run_id,
            "strategy_name": loadout.strategy_name,
            "symbol": loadout.symbol,
            "timeframe": loadout.timeframe,
            "role": loadout.role,
            "exit_mode": loadout.exit_mode,
            "init_cash": loadout.init_cash,
            "conviction": float(self.args.conviction),
            "lookback_days": (loadout.meta or {}).get("lookback_days"),
            "preferred_fill_model": FILL_MODEL_L2_WALK_V1,
            "max_book_age_ms": DEFAULT_MAX_BOOK_AGE_MS,
            "metalabel_mode": "observe" if self.model_dir else "off",
            "metalabel_bundle": str(self.model_dir) if self.model_dir else None,
            "hypervelocity": is_hypervelocity_strategy(loadout.strategy_name),
        }
        entry["artifacts"] = {
            "export": str(path),
            "model": str(self.model_dir) if self.model_dir else None,
            "paper": None,
        }
        entry["metrics"] = {"mode": "handoff", "identity": identity}

    def _paper_session(self, entry: dict[str, Any], path: Path) -> None:
        from hypervector.commands.paper import (
            _metalabel_root,
            _paper_options,
            _runtime_guard,
        )
        from hypervector.commands.registry import build_parser
        from hypervector.paper import runner as paper_runner
        from hypervector.strategies.hypervelocity_contract import (
            is_hypervelocity_strategy,
        )

        namespace = _parse_canonical(build_parser(), entry["argv"])
        strategy = self.loadout.strategy_name
        options = _paper_options(namespace, path, strategy)
        if options["execution_mode"] != "shadow" or options["sandbox_enabled"]:
            raise RuntimeError("the pipeline paper session must be shadow, no submit")
        if options["max_live_bars"] != self.args.paper_bars:
            raise RuntimeError(
                "the pipeline paper session must stop after --paper-bars "
                f"{self.args.paper_bars} live bars; got {options['max_live_bars']!r}"
            )
        hypervelocity_shadow = is_hypervelocity_strategy(strategy)
        with (
            _runtime_guard(namespace, hypervelocity_shadow),
            _metalabel_root(self.model_dir),
        ):
            result = paper_runner.start_paper_daemon(**options)
        entry["artifacts"] = {
            "export": str(path),
            "model": str(self.model_dir) if self.model_dir else None,
            "paper": str(result.decisions_path),
        }
        entry["metrics"] = {
            "mode": "foreground_shadow",
            "execution_mode": result.execution_mode,
            "no_submit": True,
            "run_id": result.run_id,
            "warm_bars": result.warm_bars,
            "live_bars": result.live_bars,
            "bars_processed": result.bars_processed,
            "fills_count": result.fills_count,
            "stop_reason": result.stop_reason,
            "hypervelocity_runtime_lock": hypervelocity_shadow,
        }
        self.manifest["next"].append(
            shlex.join(
                _cli(self.root, "paper", "report", "--decisions", result.decisions_path)
            )
        )

    def _require_export(self) -> Path:
        if self.export_dir is None:
            raise RuntimeError("no strategy bundle: the search stage did not run")
        return self.export_dir


def _parse_canonical(parser: argparse.ArgumentParser, argv: list[str]) -> Any:
    """Parse a recorded stage command, so the stage runs exactly what it records."""
    try:
        return parser.parse_args(argv[1:])
    except SystemExit as exc:
        raise RuntimeError(f"could not parse stage command {shlex.join(argv)}") from exc


def _without_bars(argv: list[str]) -> list[str]:
    """The open-ended paper hand-off: drop the pipeline's bounded bar count."""
    if "--max-live-bars" not in argv:
        return argv
    index = argv.index("--max-live-bars")
    return argv[:index] + argv[index + 2 :]


def parity_block(
    *,
    pinned: Mapping[str, Any] | None,
    export_report: Mapping[str, Any],
    nautilus: Mapping[str, Any],
) -> dict[str, Any]:
    """VectorBT (export metrics) next to Nautilus; report-only, never a gate.

    ``window_mismatch`` is true when the Nautilus bars window differs from the
    pinned window (or, when the run started from a bundle, from the window the
    bundle records) on any field both sides report.
    """
    meta = export_report.get("meta") or {}
    metrics = export_report.get("metrics") or {}
    provenance = meta.get("data_provenance") or {}
    vectorbt = {
        "source": "export metrics",
        "net_pnl": metrics.get("net_pnl"),
        "trades": metrics.get("trade_count"),
        "window": {
            "symbol": meta.get("symbol"),
            "timeframe": meta.get("timeframe"),
            "lookback_days": meta.get("lookback_days"),
            "bars": provenance.get("bar_count")
            if isinstance(provenance, Mapping)
            else None,
        },
    }
    reference = dict(pinned) if pinned else dict(vectorbt["window"])
    window = nautilus.get("window") or {}
    compared = [
        field
        for field in WINDOW_FIELDS
        if reference.get(field) is not None and window.get(field) is not None
    ]
    mismatched = [
        field
        for field in compared
        if _window_value(field, reference[field]) != _window_value(field, window[field])
    ]
    return {
        "report_only": True,
        "note": PARITY_NOTE,
        "vectorbt": vectorbt,
        "nautilus": dict(nautilus),
        "reference_window": "pinned" if pinned else "export",
        "window_mismatch": bool(mismatched) if compared else None,
        "window_mismatch_fields": mismatched,
        "compared_fields": compared,
    }


def _window_value(field: str, value: object) -> object:
    if field == "symbol":
        return str(value).strip().upper()
    if field in ("lookback_days", "bars"):
        try:
            return int(value)  # type: ignore[call-overload]
        except (TypeError, ValueError):
            return value
    return str(value)


# --- show / list (stdlib only) --------------------------------------------------------


def cmd_show(args: argparse.Namespace) -> int:
    """Print one manifest (read-only; never creates directories)."""
    path = resolve_manifest(args.ref, args.data_root)
    manifest = load_manifest(path)
    print(json.dumps(manifest, indent=2, default=str))
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    """Pipeline runs under ``<root>/runs/pipeline``, newest first (read-only)."""
    runs = Path(args.data_root) / RUNS_DIR
    entries = list_pipelines(
        args.data_root,
        strategy=args.strategy,
        symbol=args.symbol,
        timeframe=args.timeframe,
    )
    report = {
        "ok": True,
        "runs_dir": str(runs.resolve()),
        "count": len(entries),
        "invalid_count": sum(not entry["valid"] for entry in entries),
        "pipelines": entries,
    }
    print(json.dumps(report, indent=2, default=str))
    return 0


def resolve_manifest(ref: str | Path | None, data_root: Path | str) -> Path:
    """Resolve ``pipeline show REF``: a directory, ``latest`` or a pipeline id.

    Anything else is a refusal (exit 2) naming every place that was searched.
    """
    runs = Path(data_root) / RUNS_DIR
    text = str(ref).strip() if ref is not None else LATEST
    text = text or LATEST
    direct = Path(text).expanduser()
    if direct.is_dir() and (direct / MANIFEST).is_file():
        return (direct / MANIFEST).resolve()
    if direct.is_file() and direct.name == MANIFEST:
        return direct.resolve()
    looked = [f"{MANIFEST} in directory {direct.resolve()}"]
    if text == LATEST:
        newest = latest_manifest(runs)
        if newest is not None:
            return newest.resolve()
        looked.append(f"'latest' under {runs} (newest readable manifest)")
    elif Path(text).name == text and text not in (".", ".."):
        candidate = runs / text / MANIFEST
        if candidate.is_file():
            return candidate.resolve()
        looked.append(f"pipeline id {candidate.parent}")
    raise CommandRefused(
        f"pipeline reference {text!r} not found; looked for " + "; ".join(looked)
    )


def load_manifest(path: Path) -> dict[str, Any]:
    """Read one manifest; an unreadable or non-object file is a technical error."""
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"pipeline manifest is not valid JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"pipeline manifest is not a JSON object: {path}")
    return value


def latest_manifest(runs: Path) -> Path | None:
    """The newest readable manifest under ``runs`` (created time, then mtime, then name)."""
    best: tuple[float, str, Path] | None = None
    for path in _manifest_paths(runs):
        try:
            manifest = load_manifest(path)
        except (OSError, ValueError):
            continue
        key = (_recency(path, manifest), path.parent.name, path)
        if best is None or key[:2] > best[:2]:
            best = key
    return best[2] if best else None


def list_pipelines(
    data_root: Path | str,
    *,
    strategy: str | None = None,
    symbol: str | None = None,
    timeframe: str | None = None,
) -> list[dict[str, Any]]:
    """One summary per run directory; unreadable manifests are flagged, never hidden."""
    rows: list[tuple[float, str, dict[str, Any]]] = []
    wanted = (("strategy", strategy), ("symbol", symbol), ("timeframe", timeframe))
    for path in _manifest_paths(Path(data_root) / RUNS_DIR):
        entry, manifest = _summary(path)
        if all(value is None or entry.get(key) == value for key, value in wanted):
            rows.append((_recency(path, manifest), path.parent.name, entry))
    rows.sort(key=lambda row: (row[0], row[1]), reverse=True)
    return [entry for _, _, entry in rows]


def _summary(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        manifest = load_manifest(path)
    except (OSError, ValueError) as exc:
        return {
            "pipeline_id": path.parent.name,
            "manifest_path": str(path.resolve()),
            "valid": False,
            "errors": [str(exc)],
        }, {}
    request = manifest.get("request")
    request = request if isinstance(request, dict) else {}
    stages = manifest.get("stages")
    return {
        "pipeline_id": manifest.get("pipeline_id", path.parent.name),
        "created_at_utc": manifest.get("created_at_utc"),
        "status": manifest.get("status"),
        "strategy": request.get("strategy"),
        "symbol": request.get("symbol"),
        "timeframe": request.get("timeframe"),
        "search": None if request.get("export") else request.get("search"),
        "candidate_id": manifest.get("candidate_id"),
        "export_dir": manifest.get("export_dir"),
        "out_dir": manifest.get("out_dir", str(path.parent.resolve())),
        "manifest_path": str(path.resolve()),
        "stages": {
            str(stage.get("stage")): stage.get("status")
            for stage in stages
            if isinstance(stage, dict)
        }
        if isinstance(stages, list)
        else {},
        "valid": True,
        "errors": [],
    }, manifest


def _manifest_paths(runs: Path) -> list[Path]:
    if not runs.is_dir():
        return []
    return sorted(
        entry / MANIFEST
        for entry in runs.iterdir()
        if entry.is_dir() and (entry / MANIFEST).is_file()
    )


def _recency(path: Path, manifest: Mapping[str, Any]) -> float:
    created = manifest.get("created_at_utc")
    if isinstance(created, str) and created.strip():
        try:
            parsed = datetime.fromisoformat(created.strip().replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            return parsed.timestamp()
        except ValueError:
            pass
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


# --- helpers ------------------------------------------------------------------------


def _cache_path(root: Path, key: str) -> Path:
    """Where the history cache stores ``key`` (the cache's own path rule)."""
    from hypervector.data.cache import ParquetCache

    return ParquetCache(Path(root) / "cache").path_for(key)


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _progress(message: str) -> None:
    print(f"[pipeline] {message}", file=sys.stderr, flush=True)
