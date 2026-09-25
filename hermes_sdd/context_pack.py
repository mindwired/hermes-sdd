"""Deterministic, bounded context packing and hash checkpoints."""

from __future__ import annotations

import glob
import json
import fnmatch
import subprocess
import uuid
from pathlib import Path
from typing import Any

from .storage import (
    atomic_write_json,
    read_json,
    read_jsonl,
    sha256_file,
    utc_now,
    validate_id,
)


def estimate_tokens(text: str) -> int:
    # Deliberately conservative and tokenizer-independent.
    return max(1, (len(text) + 3) // 4)


def _git_snapshot(root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    commands = {
        "status": ["git", "status", "--short", "--untracked-files=normal"],
        "diff_stat": ["git", "diff", "--stat"],
    }
    for key, command in commands.items():
        try:
            completed = subprocess.run(
                command,
                cwd=root,
                check=False,
                capture_output=True,
                text=True,
                timeout=3,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if completed.returncode == 0 and completed.stdout.strip():
            result[key] = completed.stdout.strip()[:6000]
    return result


def _task_by_id(plan: dict[str, Any], task_id: str | None) -> dict[str, Any] | None:
    if not task_id:
        return None
    for task in plan.get("tasks", []):
        if task.get("id") == task_id:
            return task
    return None


def _section(title: str, value: Any) -> str:
    if value in (None, "", [], {}):
        return ""
    if isinstance(value, str):
        body = value.strip()
    else:
        body = json.dumps(value, ensure_ascii=False, indent=2)
    return f"## {title}\n\n{body}\n"


def _fit_sections(sections: list[tuple[int, str]], budget_chars: int) -> tuple[str, list[str]]:
    included: list[str] = []
    labels: list[str] = []
    remaining = max(1200, budget_chars)
    for _, section in sorted(sections, key=lambda item: item[0]):
        if not section:
            continue
        label = section.splitlines()[0].removeprefix("## ")
        if len(section) <= remaining:
            included.append(section)
            labels.append(label)
            remaining -= len(section)
            continue
        if remaining >= 500:
            clipped = (
                section[: max(0, remaining - 80)].rstrip() + "\n\n[section clipped to budget]\n"
            )
            included.append(clipped)
            labels.append(label + " (clipped)")
            remaining = 0
        break
    return "\n".join(included).rstrip() + "\n", labels


def _scope_files(root: Path, scopes: list[Any], *, limit: int = 2000) -> list[Path]:
    """Expand explicit task scopes into bounded, project-contained source files.

    Checkpoints need hashes for wildcard scopes such as ``src/api/**``; treating the
    glob as a literal path would silently miss edits. Symlinks that resolve outside
    the repository and Hermes/Git metadata are excluded. The cap protects an
    accidentally broad ``**`` scope from turning every checkpoint into a full-repo scan.
    """

    root = root.resolve()
    matched: set[Path] = set()
    for raw in scopes:
        pattern = str(raw or "").strip()
        if not pattern:
            continue
        has_magic = glob.has_magic(pattern)
        if has_magic:
            candidates = (Path(value) for value in glob.iglob(str(root / pattern), recursive=True))
        else:
            candidate = root / pattern
            if candidate.is_dir():
                candidates = candidate.rglob("*")
            else:
                candidates = iter((candidate,))
        for candidate in candidates:
            try:
                resolved = candidate.resolve()
                relative = resolved.relative_to(root)
            except (OSError, ValueError):
                continue
            if not resolved.is_file():
                continue
            if relative.parts and relative.parts[0] in {".git", ".sdd"}:
                continue
            matched.add(resolved)
            if len(matched) > limit:
                raise ValueError(
                    f"Task file scope matches more than {limit} project files; narrow the scope"
                )
    return sorted(matched)


def _excluded(path: Path, root: Path, patterns: list[Any]) -> bool:
    relative = path.resolve().relative_to(root.resolve()).as_posix()
    return any(
        fnmatch.fnmatch(relative, str(pattern).strip())
        or fnmatch.fnmatch(path.name, str(pattern).strip())
        for pattern in patterns
        if str(pattern).strip()
    )


def _authoritative_files(root: Path, task: dict[str, Any] | None = None) -> list[Path]:
    sdd = root / ".sdd"
    config = read_json(sdd / "config.json", {}) or {}
    exclusions = config.get("exclude_patterns", [])
    paths = [
        sdd / "project.json",
        sdd / "config.json",
        sdd / "state.json",
        sdd / "requirements.json",
        sdd / "roadmap.json",
        sdd / "architecture.md",
        sdd / "events.jsonl",
    ]
    paths.extend(sorted((sdd / "decisions").glob("*.json")) if (sdd / "decisions").exists() else [])
    if task:
        milestone_id = str(task.get("milestone_id") or str(task.get("id", "")).split("-T", 1)[0])
        milestone_dir = sdd / "milestones" / milestone_id
        paths.extend(
            [
                milestone_dir / "milestone.json",
                milestone_dir / "context.md",
                milestone_dir / "plan.json",
                milestone_dir / "evidence.jsonl",
                milestone_dir / "summary.md",
            ]
        )
        paths.extend(
            path
            for path in _scope_files(root, task.get("file_scope", []))
            if not _excluded(path, root, exclusions)
        )
    return sorted(
        {
            path
            for path in paths
            if path.exists() and path.is_file() and not _excluded(path, root, exclusions)
        }
    )


def create_checkpoint(
    root: Path, checkpoint_id: str | None, task: dict[str, Any] | None = None
) -> dict[str, Any]:
    checkpoint_id = validate_id(
        checkpoint_id
        or f"cp-{utc_now().replace('+00:00', 'Z').replace(':', '').replace('T', '-')}-{uuid.uuid4().hex[:8]}",
        "checkpoint id",
    )
    files: dict[str, dict[str, Any]] = {}
    for path in _authoritative_files(root, task):
        rel = path.relative_to(root).as_posix()
        files[rel] = {"sha256": sha256_file(path), "size": path.stat().st_size}
    snapshot = {
        "id": checkpoint_id,
        "created_at": utc_now(),
        "task_id": task.get("id") if task else None,
        "files": files,
    }
    atomic_write_json(root / ".sdd" / "checkpoints" / f"{checkpoint_id}.json", snapshot)
    return snapshot


def checkpoint_delta(
    root: Path, checkpoint_id: str, task: dict[str, Any] | None = None
) -> dict[str, Any]:
    checkpoint_id = validate_id(checkpoint_id, "checkpoint id")
    old = read_json(root / ".sdd" / "checkpoints" / f"{checkpoint_id}.json")
    if not old:
        raise ValueError(f"Unknown checkpoint: {checkpoint_id}")
    current: dict[str, dict[str, Any]] = {}
    for path in _authoritative_files(root, task):
        rel = path.relative_to(root).as_posix()
        current[rel] = {"sha256": sha256_file(path), "size": path.stat().st_size}
    old_files = old.get("files", {})
    added = sorted(set(current) - set(old_files))
    removed = sorted(set(old_files) - set(current))
    changed = sorted(
        path
        for path in set(current) & set(old_files)
        if current[path]["sha256"] != old_files[path].get("sha256")
    )
    unchanged = sorted((set(current) & set(old_files)) - set(changed))
    return {
        "checkpoint": checkpoint_id,
        "added": added,
        "changed": changed,
        "removed": removed,
        "unchanged_count": len(unchanged),
        "current_files": current,
    }


def build_context_pack(
    root: Path,
    *,
    milestone_id: str | None = None,
    task_id: str | None = None,
    budget_tokens: int = 12000,
    checkpoint_id: str | None = None,
    include_git: bool = True,
) -> dict[str, Any]:
    sdd = root / ".sdd"
    project = read_json(sdd / "project.json", {}) or {}
    config = read_json(sdd / "config.json", {}) or {}
    state = read_json(sdd / "state.json", {}) or {}
    requirements = read_json(sdd / "requirements.json", {"requirements": []}) or {
        "requirements": []
    }
    milestone_id = milestone_id or state.get("active_milestone")
    milestone: dict[str, Any] = {}
    plan: dict[str, Any] = {"tasks": []}
    context_text = ""
    if milestone_id:
        milestone_dir = sdd / "milestones" / validate_id(milestone_id, "milestone id")
        milestone = read_json(milestone_dir / "milestone.json", {}) or {}
        plan = read_json(milestone_dir / "plan.json", {"tasks": []}) or {"tasks": []}
        if (milestone_dir / "context.md").exists():
            context_text = (milestone_dir / "context.md").read_text(encoding="utf-8")[:16000]

    task = _task_by_id(plan, task_id)
    if task_id and task is None:
        raise ValueError(f"Task not found in milestone {milestone_id}: {task_id}")

    req_ids = set(milestone.get("requirement_ids", []))
    if task:
        req_ids.update(task.get("requirement_ids", []))
    selected_requirements = [
        req for req in requirements.get("requirements", []) if req.get("id") in req_ids
    ]

    decision_ids = set(milestone.get("decision_ids", []))
    if task:
        decision_ids.update(task.get("decision_ids", []))
    decisions: list[dict[str, Any]] = []
    for decision_id in sorted(decision_ids):
        decision = read_json(
            sdd / "decisions" / f"{validate_id(decision_id, 'decision id')}.json", {}
        )
        if decision:
            decisions.append(decision)

    dependency_tasks: list[dict[str, Any]] = []
    if task:
        dependencies = set(task.get("depends_on", []))
        dependency_tasks = [
            item for item in plan.get("tasks", []) if item.get("id") in dependencies
        ]

    recent_events = read_jsonl(sdd / "events.jsonl", limit=12)
    delta = checkpoint_delta(root, checkpoint_id, task) if checkpoint_id else None
    architecture = ""
    architecture_path = sdd / "architecture.md"
    if architecture_path.exists() and (
        not task or task.get("risk") in {"high", "critical"} or task.get("include_architecture")
    ):
        architecture = architecture_path.read_text(encoding="utf-8")[:16000]

    project_summary = {
        "name": project.get("name"),
        "goal": project.get("goal"),
        "summary": project.get("summary"),
        "mode": project.get("mode"),
        "success_criteria": project.get("success_criteria", []),
        "constraints": project.get("constraints", []),
        "non_goals": project.get("non_goals", []),
        "principles": project.get("principles", []),
    }
    task_payload = None
    if task:
        task_payload = {
            key: task.get(key)
            for key in (
                "id",
                "title",
                "objective",
                "status",
                "priority",
                "risk",
                "depends_on",
                "acceptance",
                "file_scope",
                "requirement_ids",
                "decision_ids",
                "agent_role",
                "notes",
            )
            if task.get(key) not in (None, "", [], {})
        }

    sections: list[tuple[int, str]] = [
        (
            10,
            _section(
                "Operating instruction",
                "Implement the requested outcome. Treat this pack as a compact index, not a substitute for reading the exact source files you modify. Preserve recorded constraints, produce evidence, and update SDD state when finished.",
            ),
        ),
        (20, _section("Project", project_summary)),
        (30, _section("Current state", state)),
        (40, _section("Milestone", milestone)),
        (50, _section("Selected task", task_payload)),
        (60, _section("Dependency results", dependency_tasks)),
        (70, _section("Relevant requirements", selected_requirements)),
        (80, _section("Relevant decisions", decisions)),
        (90, _section("Milestone context", context_text)),
        (100, _section("Architecture excerpt", architecture)),
        (110, _section("Changes since checkpoint", delta)),
        (120, _section("Recent SDD events", recent_events)),
        (
            130,
            _section(
                "Git working tree",
                _git_snapshot(root)
                if include_git and config.get("include_git_summary", True)
                else {},
            ),
        ),
    ]
    text, included = _fit_sections(sections, max(2000, budget_tokens * 4))
    omitted = [
        section.splitlines()[0].removeprefix("## ")
        for _, section in sorted(sections, key=lambda item: item[0])
        if section and section.splitlines()[0].removeprefix("## ") not in included
    ]
    return {
        "root": str(root),
        "milestone_id": milestone_id,
        "task_id": task_id,
        "budget_tokens": budget_tokens,
        "estimated_tokens": estimate_tokens(text),
        "sections": included,
        "omitted_sections": omitted,
        "coverage": {"included": len(included), "omitted": len(omitted)},
        "text": text,
    }
