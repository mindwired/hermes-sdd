"""Human-facing slash, Hermes CLI, and standalone CLI commands."""

from __future__ import annotations

import argparse
import json
import os
import shlex
from typing import Any, Sequence

from .core import SDDService
from .doctor import format_doctor, run_doctor
from .ui_install import desktop_status, format_status, install_desktop, uninstall_desktop

_MODES = ("auto", "quick", "standard", "deep", "program")
_CONFIGURED_MODES = ("quick", "standard", "deep", "program")


def _status_text(result: dict[str, Any]) -> str:
    if not result.get("ok"):
        return f"SDD error: {result.get('message') or result}"
    project = result.get("project") or {}
    state = result.get("state") or {}
    health = result.get("health") or {}
    counts = result.get("task_counts") or {}
    next_wave = (result.get("next") or {}).get("wave") or []
    lines = [
        f"# {project.get('name') or 'SDD project'}",
        "",
        f"- Mode: `{project.get('mode') or 'unknown'}`",
        f"- State: `{state.get('status') or 'unknown'}`",
        f"- Active milestone: `{state.get('active_milestone') or 'none'}`",
        f"- Health: **{health.get('score', 'n/a')}**",
        f"- Tasks: {json.dumps(counts, sort_keys=True)}",
    ]
    action = result.get("action") or {}
    if action:
        lines.extend(["", f"## Recommended next action: `{action.get('kind', 'inspect')}`"])
        lines.append(str(action.get("reason") or ""))
        active_validation = result.get("active_validation") or {}
        for finding in active_validation.get("findings", []):
            lines.append(
                f"- `{finding.get('code')}` — {finding.get('message')} "
                f"({finding.get('target') or 'project'})"
            )
    if next_wave:
        lines.extend(["", "## Next safe wave"])
        lines.extend(f"- `{task.get('id')}` — {task.get('title')}" for task in next_wave)
    else:
        lines.extend(["", "No dependency-ready task is currently available."])
    return "\n".join(lines)


def _result_text(result: dict[str, Any]) -> str:
    if not result.get("ok"):
        return f"SDD error: {result.get('message') or json.dumps(result, ensure_ascii=False)}"
    return json.dumps(result, ensure_ascii=False, indent=2)


def _split_root(tokens: list[str]) -> tuple[list[str], str | None]:
    root = None
    cleaned: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token in {"--root", "-C"} and index + 1 < len(tokens):
            root = tokens[index + 1]
            index += 2
            continue
        cleaned.append(token)
        index += 1
    return cleaned, root


def _shell_tokens(raw_args: str) -> list[str]:
    """Parse slash-command arguments without treating Windows separators as escapes."""
    tokens = shlex.split(raw_args or "", posix=os.name != "nt")
    if os.name == "nt":
        tokens = [
            token[1:-1]
            if len(token) >= 2 and token[0] == token[-1] and token[0] in {'"', "'"}
            else token
            for token in tokens
        ]
    return tokens


def handle_sdd(service: SDDService, raw_args: str) -> str:
    """Handle `/sdd` using small, predictable subcommands."""

    try:
        tokens, root = _split_root(_shell_tokens(raw_args))
        command = tokens.pop(0).lower() if tokens else "status"
        if command in {"status", "show"}:
            return _status_text(service.execute("status", root=root))
        if command == "init":
            mode = "auto"
            if tokens and tokens[0] in _MODES:
                mode = tokens.pop(0)
            goal = " ".join(tokens).strip()
            return _result_text(
                service.execute(
                    "init",
                    root=root,
                    payload={"goal": goal, "mode": mode, "name": None},
                )
            )
        if command == "next":
            milestone = tokens[0] if tokens else None
            return _result_text(service.execute("next", root=root, target=milestone))
        if command in {"validate", "check"}:
            return _result_text(service.execute("validate", root=root, payload={"record": True}))
        if command in {"pack", "context"}:
            task_id = tokens[0] if tokens else None
            result = service.execute("context_pack", root=root, target=task_id)
            return result.get("text") if result.get("ok") else _result_text(result)
        if command == "checkpoint":
            task_id = tokens[0] if tokens else None
            return _result_text(
                service.execute("context_checkpoint", root=root, payload={"task_id": task_id})
            )
        if command == "mode":
            if not tokens:
                return "Usage: /sdd mode <quick|standard|deep|program> [--root PATH]"
            return _result_text(
                service.execute("configure", root=root, payload={"mode": tokens[0]})
            )
        if command == "sources":
            return _result_text(service.execute("list_sources"))
        if command == "doctor":
            return format_doctor(run_doctor(root))
        if command == "ui":
            action = tokens.pop(0).lower() if tokens else "status"
            if action in {"status", "show"}:
                return format_status(desktop_status())
            if action in {"install", "sync"}:
                mode = "auto"
                force = False
                for token in tokens:
                    if token in {"auto", "link", "copy"}:
                        mode = token
                    elif token in {"--force", "force"}:
                        force = True
                return format_status(install_desktop(mode=mode, force=force))
            if action in {"remove", "uninstall"}:
                return format_status(uninstall_desktop())
            return "Usage: /sdd ui [status|install [auto|link|copy] [--force]|uninstall]"
        if command == "help":
            return (
                "`/sdd [status]`, `/sdd init [mode] <goal>`, `/sdd next [milestone]`, "
                "`/sdd validate`, `/sdd pack [task]`, `/sdd checkpoint [task]`, "
                "`/sdd mode <mode>`, `/sdd sources`, `/sdd doctor`, `/sdd ui ...`; "
                "add `--root PATH` when needed. If the chat composer does not suggest `/sdd`, "
                "type it directly; Desktop may omit plugin commands from its picker."
            )
        return f"Unknown SDD command: {command}. Run `/sdd help`."
    except Exception as exc:
        return f"SDD error: {type(exc).__name__}: {exc}"


def build_cli_parser(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.description = "Manage adaptive spec-driven project state"
    parser.add_argument("--json", action="store_true", dest="global_json", help="Emit JSON")
    parser.add_argument("--root", "-C", dest="global_root", default=None, help="Project root")
    subparsers = parser.add_subparsers(dest="command")

    status = subparsers.add_parser("status", help="Show compact project status")
    status.add_argument("--json", action="store_true")
    status.add_argument("--root", "-C", default=None)

    init = subparsers.add_parser("init", help="Initialize .sdd state")
    init.add_argument("mode", nargs="?", choices=_MODES, default="auto")
    init.add_argument("goal", nargs="*")
    init.add_argument("--root", "-C", default=None)
    init.add_argument("--json", action="store_true")
    init.add_argument("--force", action="store_true")

    nxt = subparsers.add_parser("next", help="Show the next safe task wave")
    nxt.add_argument("milestone", nargs="?", default=None)
    nxt.add_argument("--limit", type=int, default=None)
    nxt.add_argument("--root", "-C", default=None)
    nxt.add_argument("--json", action="store_true")

    validate = subparsers.add_parser("validate", help="Validate state and traceability")
    validate.add_argument("--root", "-C", default=None)
    validate.add_argument("--json", action="store_true")
    validate.add_argument("--no-record", action="store_true")
    validate.add_argument("--detail", choices=("compact", "normal", "full"), default="normal")

    pack = subparsers.add_parser("pack", help="Build a bounded task context pack")
    pack.add_argument("task", nargs="?", default=None)
    pack.add_argument("--checkpoint", default=None)
    pack.add_argument("--budget", type=int, default=None)
    pack.add_argument("--root", "-C", default=None)
    pack.add_argument("--json", action="store_true")

    checkpoint = subparsers.add_parser("checkpoint", help="Create a context hash checkpoint")
    checkpoint.add_argument("task", nargs="?", default=None)
    checkpoint.add_argument("--root", "-C", default=None)
    checkpoint.add_argument("--json", action="store_true")

    mode = subparsers.add_parser("mode", help="Change adaptive rigor mode")
    mode.add_argument("mode", choices=_CONFIGURED_MODES)
    mode.add_argument("--root", "-C", default=None)
    mode.add_argument("--json", action="store_true")

    sources = subparsers.add_parser("sources", help="List Dashboard project sources")
    sources.add_argument("--json", action="store_true")

    doctor = subparsers.add_parser("doctor", help="Inspect installation compatibility")
    doctor.add_argument("--root", "-C", default=None)
    doctor.add_argument("--json", action="store_true")

    ui = subparsers.add_parser("ui", help="Manage the optional native Desktop adapter")
    ui_sub = ui.add_subparsers(dest="ui_action")
    ui_status = ui_sub.add_parser("status", help="Show Desktop adapter status")
    ui_status.add_argument("--json", action="store_true")
    ui_install = ui_sub.add_parser(
        "install", aliases=["sync"], help="Install or refresh Desktop adapter"
    )
    ui_install.add_argument("--mode", choices=("auto", "link", "copy"), default="auto")
    ui_install.add_argument("--force", action="store_true")
    ui_install.add_argument("--json", action="store_true")
    ui_remove = ui_sub.add_parser("uninstall", aliases=["remove"], help="Remove Desktop adapter")
    ui_remove.add_argument("--json", action="store_true")

    return parser


def _arg(args: argparse.Namespace, name: str, default: Any = None) -> Any:
    value = getattr(args, name, None)
    return default if value is None else value


def handle_cli(service: SDDService, args: argparse.Namespace) -> int:
    command = args.command or "status"
    root = _arg(args, "root") or _arg(args, "global_root")
    emit_json = bool(_arg(args, "json", False) or _arg(args, "global_json", False))

    if command == "status":
        result = service.execute("status", root=root)
        output = (
            json.dumps(result, ensure_ascii=False, indent=2) if emit_json else _status_text(result)
        )
    elif command == "init":
        result = service.execute(
            "init",
            root=root,
            payload={"goal": " ".join(args.goal), "mode": args.mode},
            options={"force": args.force},
        )
        output = _result_text(result)
    elif command == "next":
        options = {"limit": args.limit} if args.limit is not None else {}
        result = service.execute("next", root=root, target=args.milestone, options=options)
        output = _result_text(result)
    elif command == "validate":
        result = service.execute(
            "validate",
            root=root,
            payload={"record": not args.no_record},
            options={"detail": args.detail},
        )
        output = _result_text(result)
    elif command == "pack":
        payload = {"checkpoint_id": args.checkpoint} if args.checkpoint else {}
        options = {"budget_tokens": args.budget} if args.budget is not None else {}
        result = service.execute(
            "context_pack", root=root, target=args.task, payload=payload, options=options
        )
        output = _result_text(result) if emit_json else result.get("text", _result_text(result))
    elif command == "checkpoint":
        result = service.execute("context_checkpoint", root=root, payload={"task_id": args.task})
        output = _result_text(result)
    elif command == "mode":
        result = service.execute("configure", root=root, payload={"mode": args.mode})
        output = _result_text(result)
    elif command == "sources":
        result = service.execute("list_sources")
        output = _result_text(result)
    elif command == "doctor":
        result = run_doctor(root)
        output = (
            json.dumps(result, ensure_ascii=False, indent=2) if emit_json else format_doctor(result)
        )
    elif command == "ui":
        action = args.ui_action or "status"
        if action == "status":
            result = desktop_status()
        elif action in {"install", "sync"}:
            result = install_desktop(mode=args.mode, force=args.force)
        else:
            result = uninstall_desktop()
        output = format_status(result)
    else:
        result = {"ok": False, "message": f"Unknown command: {command}"}
        output = _result_text(result)

    print(output)
    return 0 if result.get("ok") else 1


def parse_and_run(
    service: SDDService,
    argv: Sequence[str] | None = None,
    *,
    prog: str = "hermes-sdd",
) -> int:
    parser = build_cli_parser(argparse.ArgumentParser(prog=prog))
    return handle_cli(service, parser.parse_args(list(argv) if argv is not None else None))


def register_commands(ctx: Any, service: SDDService) -> None:
    ctx.register_command(
        "sdd",
        lambda raw: handle_sdd(service, raw),
        description="Manage SDD project state, planning, context, and verification",
        args_hint="[status|init|next|validate|pack|mode|doctor|ui]",
    )
    ctx.register_command(
        "sdd-status",
        lambda raw: handle_sdd(service, f"status {raw}"),
        description="Show SDD project status",
    )
    ctx.register_command(
        "sdd-next",
        lambda raw: handle_sdd(service, f"next {raw}"),
        description="Show the next dependency-safe task wave",
    )
    ctx.register_command(
        "sdd-validate",
        lambda raw: handle_sdd(service, f"validate {raw}"),
        description="Validate SDD traceability and evidence",
    )

    def _setup(parser: argparse.ArgumentParser) -> None:
        build_cli_parser(parser)
        parser.set_defaults(func=lambda ns: handle_cli(service, ns))

    ctx.register_cli_command(
        "sdd",
        help="Adaptive spec-driven development",
        setup_fn=_setup,
        description="Inspect and manage .sdd project state",
    )
