"""Authoritative service layer for adaptive spec-driven development."""

from __future__ import annotations

import json
import re
import uuid
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any, Iterable

from .context_pack import build_context_pack, checkpoint_delta, create_checkpoint
from .registry import SourceRegistry
from .render import render_all, render_decision_index
from .storage import (
    append_jsonl,
    atomic_write_json,
    atomic_write_text,
    ensure_no_symlinks,
    project_lock,
    project_transaction,
    read_json,
    read_jsonl,
    resolve_root,
    utc_now,
    validate_id,
)

_MODES = {"auto", "quick", "standard", "deep", "program"}
_TASK_STATES = {"pending", "in_progress", "blocked", "done", "skipped"}
_RISKS = {"low", "medium", "high", "critical"}
_MILESTONE_STATES = {
    "planned",
    "ready",
    "in_progress",
    "blocked",
    "done",
    "verified",
    "overridden",
    "cancelled",
}
_REQUIREMENT_PRIORITIES = {"must", "should", "could", "wont"}
_REQUIREMENT_STATES = {"active", "satisfied", "deferred", "cancelled"}
_DECISION_STATES = {"proposed", "accepted", "superseded", "rejected"}
_DECISION_ID_RE = re.compile(r"^ADR-\d{4,}$")


def _list(value: Any) -> list[Any]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("Expected a list")
    return value


def _string_list(value: Any, label: str) -> list[str]:
    values = [] if value is None else value
    if not isinstance(values, list):
        raise ValueError(f"{label} must be a list of non-empty strings")
    if any(not isinstance(item, str) or not item.strip() for item in values):
        raise ValueError(f"{label} must contain non-empty strings")
    return [item.strip() for item in values]


def _decision_list(value: Any, label: str = "decision ids") -> list[str]:
    values = [] if value is None else value
    if not isinstance(values, list):
        raise ValueError(f"{label} must be a list of ADR identifiers")
    return [_decision_id(item) for item in values]


def _decision_id(value: Any) -> str:
    decision_id = validate_id(value, "decision id")
    if not _DECISION_ID_RE.fullmatch(decision_id):
        raise ValueError("Decision id must use the ADR-0001 format")
    return decision_id


def _exit_criterion_records(
    milestone_id: str,
    criteria: list[str],
    existing: Any = None,
) -> list[dict[str, str]]:
    """Reconcile active criterion text while retaining retired IDs as history."""
    rows = [] if existing is None else existing
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError("exit_criteria_records must be a list of criterion objects")
    by_text: dict[str, deque[dict[str, str]]] = defaultdict(deque)
    retired: list[dict[str, str]] = []
    used_ids: set[str] = set()
    for row in rows:
        criterion_id = validate_id(row.get("id"), "exit criterion id")
        text = row.get("text")
        status = row.get("status", "active")
        if (
            not isinstance(text, str)
            or not text.strip()
            or not isinstance(status, str)
            or status not in {"active", "retired"}
        ):
            raise ValueError(
                "Each exit criterion requires non-empty text and active/retired status"
            )
        if (
            not re.fullmatch(rf"{re.escape(milestone_id)}-EC\d{{3,}}", criterion_id)
            or criterion_id in used_ids
        ):
            raise ValueError(f"Invalid or duplicate exit criterion id: {criterion_id}")
        used_ids.add(criterion_id)
        normalized = {"id": criterion_id, "text": text.strip(), "status": status}
        if status == "active":
            by_text[normalized["text"]].append(normalized)
        else:
            retired.append(normalized)

    active: list[dict[str, str]] = []
    for text in criteria:
        matching = by_text[text].popleft() if by_text[text] else None
        if matching is not None:
            active.append(matching)
            continue
        criterion_id = _next_numeric_id(used_ids, f"{milestone_id}-EC", width=3)
        used_ids.add(criterion_id)
        active.append({"id": criterion_id, "text": text, "status": "active"})

    for queue in by_text.values():
        retired.extend({**row, "status": "retired"} for row in queue)
    return [*active, *retired]


def _validate_exit_criterion_records(
    milestone_id: str, records: Any, schema_version: Any
) -> list[dict[str, str]]:
    if type(schema_version) is not int or schema_version != 1 or not isinstance(records, list):
        raise ValueError("Structured exit criteria require schema version 1 and a record list")
    normalized: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    for item in records:
        if not isinstance(item, dict):
            raise ValueError("exit_criteria_records must contain criterion objects")
        criterion_id = validate_id(str(item.get("id") or ""), "exit criterion id")
        text = item.get("text")
        status = item.get("status", "active")
        if (
            not isinstance(text, str)
            or not text.strip()
            or not isinstance(status, str)
            or status not in {"active", "retired"}
            or not re.fullmatch(rf"{re.escape(milestone_id)}-EC\d{{3,}}", criterion_id)
            or criterion_id in seen_ids
        ):
            raise ValueError("Invalid or duplicate structured exit criterion")
        seen_ids.add(criterion_id)
        normalized.append({"id": criterion_id, "text": text.strip(), "status": status})
    return normalized


def _compact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _compact(item) for key, item in value.items() if item not in (None, "", [], {})
        }
    if isinstance(value, list):
        return [_compact(item) for item in value]
    return value


def _next_numeric_id(existing: Iterable[str], prefix: str, width: int = 3) -> str:
    pattern = re.compile(rf"^{re.escape(prefix)}(\d+)$")
    numbers = [int(match.group(1)) for value in existing if (match := pattern.match(str(value)))]
    return f"{prefix}{max(numbers, default=0) + 1:0{width}d}"


def complexity_mode(signals: dict[str, Any] | None) -> tuple[str, int]:
    signals = signals or {}
    dimensions = ("novelty", "ambiguity", "surface_area", "risk", "duration", "coordination")
    score = 0
    for key in dimensions:
        try:
            score += max(0, min(3, int(signals.get(key, 1))))
        except (TypeError, ValueError):
            score += 1
    if score <= 4:
        return "quick", score
    if score <= 8:
        return "standard", score
    if score <= 13:
        return "deep", score
    return "program", score


def _path_overlap(left: str, right: str) -> bool:
    left = left.strip().strip("/")
    right = right.strip().strip("/")
    if not left or not right:
        return True
    if any(char in left for char in "*?[") or any(char in right for char in "*?["):
        left_base = re.split(r"[\*\?\[]", left, maxsplit=1)[0].rstrip("/")
        right_base = re.split(r"[\*\?\[]", right, maxsplit=1)[0].rstrip("/")
        if not left_base or not right_base:
            return True
        left, right = left_base, right_base
    return left == right or left.startswith(right + "/") or right.startswith(left + "/")


def _tasks_conflict(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_scope = _list(left.get("file_scope"))
    right_scope = _list(right.get("file_scope"))
    if not left_scope or not right_scope:
        return True
    return any(_path_overlap(str(a), str(b)) for a in left_scope for b in right_scope)


def _validate_dag(tasks: list[dict[str, Any]]) -> list[str]:
    ids = {str(task.get("id")) for task in tasks}
    errors: list[str] = []
    graph: dict[str, list[str]] = defaultdict(list)
    indegree: dict[str, int] = {task_id: 0 for task_id in ids}
    for task in tasks:
        task_id = str(task.get("id"))
        for dep in _list(task.get("depends_on")):
            dep = str(dep)
            if dep not in ids:
                errors.append(f"{task_id} depends on unknown task {dep}")
                continue
            graph[dep].append(task_id)
            indegree[task_id] += 1
    queue = deque(task_id for task_id, degree in indegree.items() if degree == 0)
    seen = 0
    while queue:
        node = queue.popleft()
        seen += 1
        for child in graph[node]:
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)
    if seen != len(ids):
        errors.append("Task dependency graph contains a cycle")
    return errors


class SDDService:
    schema_version = 1

    def __init__(self, registry: SourceRegistry | None = None) -> None:
        self._registry = registry

    @property
    def registry(self) -> SourceRegistry:
        """Create the optional visual-source registry only when first used."""
        if self._registry is None:
            self._registry = SourceRegistry()
        return self._registry

    def _root(self, root: str | None, *, create: bool = False) -> Path:
        return resolve_root(root, create=create)

    @staticmethod
    def _sdd(root: Path) -> Path:
        return root / ".sdd"

    def _require(self, root: Path) -> Path:
        sdd = self._sdd(root)
        if sdd.is_symlink():
            raise ValueError(f"Refusing symlinked SDD directory: {sdd}")
        if not sdd.is_dir() or not (sdd / "project.json").is_file():
            raise ValueError(f"No SDD project at {root}; run operation=init first")
        ensure_no_symlinks(sdd)
        for filename in (
            "project.json",
            "config.json",
            "state.json",
            "requirements.json",
            "roadmap.json",
            "architecture.md",
            "events.jsonl",
        ):
            if not (sdd / filename).is_file():
                raise ValueError(f"Missing required SDD file: {sdd / filename}")
        for name in ("milestones", "decisions", "checkpoints", ".locks", "cache"):
            if (sdd / name).is_symlink():
                raise ValueError(f"Refusing symlinked SDD subdirectory: {sdd / name}")
        return sdd

    @staticmethod
    def _read_required_json_path(path: Path) -> dict[str, Any]:
        if not path.is_file():
            raise ValueError(f"Missing required SDD file: {path}")
        value = read_json(path)
        if not isinstance(value, dict):
            raise ValueError(f"Malformed SDD JSON object at {path}: expected a JSON object")
        return value

    @classmethod
    def _read_project(cls, sdd: Path) -> dict[str, Any]:
        project = cls._read_required_json(sdd, "project.json")
        if not project.get("name") or not project.get("mode") or not project.get("status"):
            raise ValueError(
                f"Malformed SDD project.json at {sdd / 'project.json'}: required fields missing"
            )
        return project

    @classmethod
    def _read_required_json(cls, sdd: Path, filename: str) -> dict[str, Any]:
        return cls._read_required_json_path(sdd / filename)

    @staticmethod
    def _require_list_field(document: dict[str, Any], key: str, label: str) -> list[Any]:
        value = document.get(key, [])
        if not isinstance(value, list):
            raise ValueError(f"{label} must be a list")
        return value

    @classmethod
    def _require_object_list(
        cls, document: dict[str, Any], key: str, label: str
    ) -> list[dict[str, Any]]:
        values = cls._require_list_field(document, key, label)
        if any(not isinstance(item, dict) for item in values):
            raise ValueError(f"{label} must contain objects")
        return values

    @staticmethod
    def _event(sdd: Path, kind: str, **data: Any) -> None:
        append_jsonl(sdd / "events.jsonl", {"at": utc_now(), "kind": kind, **_compact(data)})

    def init(
        self, root: str | None, payload: dict[str, Any], options: dict[str, Any]
    ) -> dict[str, Any]:
        project_root = self._root(root, create=True)
        sdd = self._sdd(project_root)
        backup_path = None
        if sdd.is_symlink() and not options.get("force"):
            raise ValueError(
                f"Refusing symlinked SDD directory: {sdd}; use force only to replace the link"
            )
        if sdd.exists() and not options.get("force") and not (sdd / "project.json").is_file():
            raise ValueError(
                f"SDD state at {sdd} is incomplete or malformed; use force to replace it"
            )
        if (sdd / "project.json").is_file() and not options.get("force"):
            return {"ok": True, "created": False, "status": self.status(str(project_root), {}, {})}

        requested_mode = str(payload.get("mode") or "auto").lower()
        if requested_mode not in _MODES:
            raise ValueError(f"Invalid mode {requested_mode!r}; choose one of {sorted(_MODES)}")
        resolved_mode, score = complexity_mode(payload.get("signals"))
        mode = resolved_mode if requested_mode == "auto" else requested_mode
        now = utc_now()
        project = {
            "schema_version": self.schema_version,
            "name": payload.get("name") or project_root.name,
            "goal": payload.get("goal") or "",
            "summary": payload.get("summary") or "",
            "mode": mode,
            "complexity_score": score,
            "success_criteria": _string_list(payload.get("success_criteria"), "success criteria"),
            "constraints": _string_list(payload.get("constraints"), "constraints"),
            "non_goals": _string_list(payload.get("non_goals"), "non-goals"),
            "principles": _string_list(payload.get("principles"), "principles"),
            "status": "active",
            "created_at": now,
            "updated_at": now,
        }
        evidence_policy = payload.get("require_evidence", "risk_based")
        if evidence_policy not in {"never", "risk_based", "always"}:
            raise ValueError("require_evidence must be never, risk_based, or always")
        config = {
            "schema_version": self.schema_version,
            "mode": mode,
            "max_parallel": max(1, min(12, int(payload.get("max_parallel") or 4))),
            "context_budget_tokens": max(
                2000, min(80000, int(payload.get("context_budget_tokens") or 12000))
            ),
            "require_evidence": evidence_policy,
            "strict": bool(payload.get("strict", False)),
            "include_git_summary": bool(payload.get("include_git_summary", True)),
            "exclude_patterns": _string_list(
                payload.get("exclude_patterns", [".env", ".env.*", "**/.env", "**/.env.*"]),
                "exclude patterns",
            ),
            "max_artifact_chars": max(8000, int(payload.get("max_artifact_chars") or 50000)),
        }
        state = {
            "schema_version": self.schema_version,
            "status": "planning" if mode != "quick" else "active",
            "active_milestone": None,
            "current_tasks": [],
            "last_checkpoint": None,
            "updated_at": now,
        }
        previous_sdd = None
        if (sdd.exists() or sdd.is_symlink()) and options.get("force"):
            stamp = utc_now().replace("+00:00", "Z").replace(":", "").replace("T", "-")
            backup = project_root / f".sdd.backup-{stamp}-{uuid.uuid4().hex[:6]}"
            sdd.rename(backup)
            backup_path = str(backup)
            previous_sdd = backup
        sdd.mkdir(parents=True, exist_ok=True)
        try:
            for directory in (
                "milestones",
                "decisions",
                "checkpoints",
                "research",
                ".locks",
                "cache",
            ):
                (sdd / directory).mkdir(parents=True, exist_ok=True)
            atomic_write_text(sdd / ".gitignore", ".locks/\ncache/\n")
            atomic_write_json(sdd / "project.json", project)
            atomic_write_json(sdd / "config.json", config)
            atomic_write_json(sdd / "state.json", state)
            atomic_write_json(sdd / "requirements.json", {"schema_version": 1, "requirements": []})
            atomic_write_json(sdd / "roadmap.json", {"schema_version": 1, "milestones": []})
            atomic_write_text(sdd / "architecture.md", "# Architecture\n\nNot established yet.\n")
            atomic_write_text(sdd / "events.jsonl", "")
            self._event(sdd, "project_initialized", mode=mode, complexity_score=score)
            render_all(project_root)
            render_decision_index(project_root)
        except Exception:
            if sdd.exists():
                import shutil

                shutil.rmtree(sdd)
            if previous_sdd is not None and previous_sdd.exists():
                previous_sdd.rename(sdd)
                backup_path = None
            raise
        source = None
        source_warning = None
        try:
            source = self.registry.register(str(project_root), str(project.get("name")))
        except Exception as exc:
            # The registry is a disposable UI projection. Canonical project state
            # must remain usable when its SQLite database is unavailable.
            source_warning = f"Source registry unavailable: {type(exc).__name__}: {exc}"
        return {
            "ok": True,
            "created": True,
            "root": str(project_root),
            "mode": mode,
            "complexity_score": score,
            "source": source,
            "source_warning": source_warning,
            "backup": backup_path,
            "next": "Capture goals/requirements, then create a milestone and plan only the first meaningful slice.",
        }

    def configure(
        self, root: str | None, payload: dict[str, Any], _: dict[str, Any]
    ) -> dict[str, Any]:
        project_root = self._root(root)
        sdd = self._require(project_root)
        allowed = {
            "mode",
            "max_parallel",
            "context_budget_tokens",
            "require_evidence",
            "strict",
            "include_git_summary",
            "max_artifact_chars",
            "exclude_patterns",
        }
        updates = {key: value for key, value in payload.items() if key in allowed}
        if "mode" in updates and updates["mode"] not in _MODES - {"auto"}:
            raise ValueError("Configured mode must be quick, standard, deep, or program")
        if "max_parallel" in updates:
            updates["max_parallel"] = max(1, min(12, int(updates["max_parallel"])))
        if "context_budget_tokens" in updates:
            updates["context_budget_tokens"] = max(
                2000, min(80000, int(updates["context_budget_tokens"]))
            )
        if "require_evidence" in updates and updates["require_evidence"] not in {
            "never",
            "risk_based",
            "always",
        }:
            raise ValueError("require_evidence must be never, risk_based, or always")
        if "exclude_patterns" in updates:
            updates["exclude_patterns"] = _string_list(
                updates["exclude_patterns"], "exclude patterns"
            )
        with project_lock(sdd), project_transaction(sdd):
            config = self._read_required_json(sdd, "config.json")
            config.update(updates)
            config["updated_at"] = utc_now()
            atomic_write_json(sdd / "config.json", config)
            if "mode" in updates:
                project = self._read_project(sdd)
                project["mode"] = updates["mode"]
                project["updated_at"] = utc_now()
                atomic_write_json(sdd / "project.json", project)
            self._event(sdd, "configuration_updated", updates=updates)
            render_all(project_root)
        return {"ok": True, "config": config}

    def upsert_spec(
        self, root: str | None, payload: dict[str, Any], _: dict[str, Any]
    ) -> dict[str, Any]:
        project_root = self._root(root)
        sdd = self._require(project_root)
        with project_lock(sdd), project_transaction(sdd):
            project = self._read_project(sdd)
            for key in (
                "name",
                "goal",
                "summary",
                "success_criteria",
                "constraints",
                "non_goals",
                "principles",
                "status",
            ):
                if key in payload:
                    project[key] = (
                        _string_list(payload[key], key.replace("_", " "))
                        if key in {"success_criteria", "constraints", "non_goals", "principles"}
                        else payload[key]
                    )
            project["updated_at"] = utc_now()
            atomic_write_json(sdd / "project.json", project)

            requirements_doc = self._read_required_json(sdd, "requirements.json")
            requirement_rows = self._require_object_list(
                requirements_doc, "requirements", "requirements"
            )
            raw_requirements = payload.get("requirements", [])
            if not isinstance(raw_requirements, list):
                raise ValueError("requirements must be a list")
            if any(not isinstance(item, dict) for item in raw_requirements):
                raise ValueError("requirements must contain objects")
            existing = {item.get("id"): item for item in requirement_rows}
            existing_ids = [key for key in existing if key]
            changed: list[str] = []
            for raw in raw_requirements:
                req_id = raw.get("id") or _next_numeric_id(existing_ids, "REQ-", 3)
                req_id = validate_id(req_id, "requirement id")
                item = existing.get(req_id, {"id": req_id, "created_at": utc_now()})
                priority = raw.get("priority", item.get("priority", "must"))
                status = raw.get("status", item.get("status", "active"))
                if priority not in _REQUIREMENT_PRIORITIES:
                    raise ValueError(f"Invalid requirement priority: {priority}")
                if status not in _REQUIREMENT_STATES:
                    raise ValueError(f"Invalid requirement status: {status}")
                item.update(
                    {
                        "title": raw["title"] if "title" in raw else item.get("title") or req_id,
                        "statement": raw["statement"]
                        if "statement" in raw
                        else item.get("statement", ""),
                        "priority": priority,
                        "acceptance": _string_list(
                            raw.get("acceptance", item.get("acceptance", [])),
                            "requirement acceptance",
                        ),
                        "status": status,
                        "source": raw["source"] if "source" in raw else item.get("source", "user"),
                        "updated_at": utc_now(),
                    }
                )
                existing[req_id] = item
                existing_ids.append(req_id)
                changed.append(req_id)
            requirements_doc["requirements"] = sorted(
                existing.values(), key=lambda item: item.get("id", "")
            )
            atomic_write_json(sdd / "requirements.json", requirements_doc)

            if "architecture" in payload:
                architecture = str(payload.get("architecture") or "").strip()
                atomic_write_text(sdd / "architecture.md", architecture.rstrip() + "\n")
            self._event(
                sdd,
                "spec_updated",
                requirements=changed,
                project_fields=[key for key in payload if key != "requirements"],
            )
            render_all(project_root)
        return {"ok": True, "requirements_updated": changed, "project": _compact(project)}

    def create_milestone(
        self, root: str | None, payload: dict[str, Any], options: dict[str, Any]
    ) -> dict[str, Any]:
        project_root = self._root(root)
        sdd = self._require(project_root)
        with project_lock(sdd), project_transaction(sdd):
            roadmap = self._read_required_json(sdd, "roadmap.json")
            milestones = self._require_object_list(roadmap, "milestones", "milestones")
            milestone_id = validate_id(
                payload.get("id")
                or _next_numeric_id([m.get("id", "") for m in milestones], "M", 3),
                "milestone id",
            )
            if any(item.get("id") == milestone_id for item in milestones):
                raise ValueError(f"Milestone already exists: {milestone_id}")
            milestone_status = payload.get("status") or "planned"
            if milestone_status not in _MILESTONE_STATES:
                raise ValueError(f"Invalid milestone status: {milestone_status}")
            risk = payload.get("risk", "medium")
            if risk not in _RISKS:
                raise ValueError(f"Invalid milestone risk: {risk}")
            milestone = {
                "id": milestone_id,
                "title": payload.get("title") or milestone_id,
                "objective": payload.get("objective") or "",
                "status": milestone_status,
                "risk": risk,
                "requirement_ids": _string_list(payload.get("requirement_ids"), "requirement ids"),
                "decision_ids": _decision_list(payload.get("decision_ids")),
                "exit_criteria": _string_list(payload.get("exit_criteria"), "exit criteria"),
                "interfaces_stable": bool(payload.get("interfaces_stable", False)),
                "created_at": utc_now(),
                "updated_at": utc_now(),
            }
            milestone["exit_criteria_records"] = _exit_criterion_records(
                milestone_id, milestone["exit_criteria"]
            )
            milestone["exit_criteria_schema_version"] = 1
            milestones.append(milestone)
            roadmap["milestones"] = milestones
            atomic_write_json(sdd / "roadmap.json", roadmap)
            milestone_dir = sdd / "milestones" / milestone_id
            milestone_dir.mkdir(parents=True, exist_ok=True)
            atomic_write_json(milestone_dir / "milestone.json", milestone)
            atomic_write_json(
                milestone_dir / "plan.json",
                {"schema_version": 1, "milestone_id": milestone_id, "revision": 0, "tasks": []},
            )
            atomic_write_text(
                milestone_dir / "context.md",
                str(payload.get("context") or "# Milestone context\n\nNot recorded yet.\n").rstrip()
                + "\n",
            )
            atomic_write_text(milestone_dir / "evidence.jsonl", "")
            atomic_write_text(
                milestone_dir / "summary.md", "# Milestone summary\n\nNot completed yet.\n"
            )
            project = self._read_project(sdd)
            if project.get("status") in {"complete", "overridden"}:
                project["status"] = "active"
                project["updated_at"] = utc_now()
                atomic_write_json(sdd / "project.json", project)
            state = self._read_required_json(sdd, "state.json")
            if options.get("activate") is True or not state.get("active_milestone"):
                state["active_milestone"] = milestone_id
                state["status"] = "planning"
                state["updated_at"] = utc_now()
                atomic_write_json(sdd / "state.json", state)
            self._event(sdd, "milestone_created", milestone_id=milestone_id)
            render_all(project_root)
        return {"ok": True, "milestone": milestone}

    def update_milestone(
        self, root: str | None, target: str | None, payload: dict[str, Any], options: dict[str, Any]
    ) -> dict[str, Any]:
        project_root = self._root(root)
        sdd = self._require(project_root)
        scalar_fields = {"title", "objective", "status", "risk", "interfaces_stable"}
        list_fields = {"requirement_ids", "decision_ids", "exit_criteria"}
        with project_lock(sdd), project_transaction(sdd):
            milestone_id, milestone_dir, milestone, _ = self._milestone(
                sdd, target or payload.get("milestone_id")
            )
            for key in scalar_fields:
                if key in payload:
                    value = payload[key]
                    if key == "risk" and value not in _RISKS:
                        raise ValueError(f"Invalid milestone risk: {value}")
                    if key == "status" and value not in _MILESTONE_STATES:
                        raise ValueError(f"Invalid milestone status: {value}")
                    milestone[key] = bool(value) if key == "interfaces_stable" else value
            legacy_exit_criteria = _string_list(milestone.get("exit_criteria"), "exit criteria")
            legacy_exit_criteria_records = milestone.get("exit_criteria_records")
            legacy_schema_version = milestone.get("exit_criteria_schema_version")
            explicit_criterion_records = "exit_criteria_records" in payload
            if explicit_criterion_records:
                if "exit_criteria" in payload:
                    raise ValueError("Update exit_criteria or exit_criteria_records, not both")
                existing_records = milestone.get("exit_criteria_records")
                normalized_records = _validate_exit_criterion_records(
                    milestone_id,
                    payload["exit_criteria_records"],
                    payload.get("exit_criteria_schema_version", 1),
                )
                existing_criterion_ids = {
                    item.get("id")
                    for item in (existing_records if isinstance(existing_records, list) else [])
                    if isinstance(item, dict)
                }
                submitted_criterion_records = {item["id"]: item for item in normalized_records}
                if existing_criterion_ids - set(submitted_criterion_records):
                    raise ValueError(
                        "Structured criterion updates cannot remove existing criterion IDs; "
                        "mark removed criteria retired"
                    )
                if any(
                    item.get("status") == "retired"
                    and submitted_criterion_records[item["id"]].get("status") != "retired"
                    for item in (existing_records if isinstance(existing_records, list) else [])
                    if isinstance(item, dict) and item.get("id") in submitted_criterion_records
                ):
                    raise ValueError("Retired exit criterion IDs cannot be reactivated")
                if any(
                    submitted_criterion_records[criterion_id].get("text") != item.get("text")
                    for item in (existing_records if isinstance(existing_records, list) else [])
                    if isinstance(item, dict)
                    and (criterion_id := item.get("id")) in submitted_criterion_records
                ):
                    raise ValueError(
                        "Exit criterion text is immutable; assign a new ID to changed text"
                    )
                milestone["exit_criteria_records"] = normalized_records
                milestone["exit_criteria"] = [
                    item["text"] for item in normalized_records if item["status"] == "active"
                ]
                milestone["exit_criteria_schema_version"] = 1
            for key in list_fields:
                if key in payload:
                    if key == "decision_ids":
                        milestone[key] = _decision_list(payload[key])
                    elif key == "requirement_ids":
                        milestone[key] = _string_list(payload[key], "requirement ids")
                    elif key == "exit_criteria":
                        milestone[key] = _string_list(payload[key], "exit criteria")
            if "exit_criteria" in payload:
                legacy_records = legacy_exit_criteria_records
                if legacy_schema_version is None and legacy_records is None:
                    legacy_records = [
                        {
                            "id": f"{milestone_id}-EC{index:03d}",
                            "text": text,
                            "status": "active",
                        }
                        for index, text in enumerate(legacy_exit_criteria, start=1)
                    ]
                milestone["exit_criteria_records"] = _exit_criterion_records(
                    milestone_id,
                    milestone["exit_criteria"],
                    legacy_records,
                )
                milestone["exit_criteria_schema_version"] = 1
            elif "exit_criteria_records" not in milestone:
                milestone["exit_criteria_records"] = _exit_criterion_records(
                    milestone_id,
                    _string_list(milestone.get("exit_criteria"), "exit criteria"),
                )
                milestone["exit_criteria_schema_version"] = 1
            else:
                milestone["exit_criteria_records"] = _validate_exit_criterion_records(
                    milestone_id,
                    milestone["exit_criteria_records"],
                    milestone.get("exit_criteria_schema_version"),
                )
            retired_criteria_ids = {
                item["id"]
                for item in milestone["exit_criteria_records"]
                if item["status"] == "retired"
            }
            if retired_criteria_ids:
                current_plan = self._read_required_json_path(milestone_dir / "plan.json")
                linked_tasks = [
                    str(task.get("id"))
                    for task in self._require_object_list(current_plan, "tasks", "plan tasks")
                    if retired_criteria_ids
                    & set(_string_list(task.get("exit_criteria_ids"), "task exit criterion ids"))
                ]
                if linked_tasks:
                    raise ValueError(
                        "Exit criteria cannot be retired while linked to tasks: "
                        + ", ".join(linked_tasks)
                    )
            milestone["updated_at"] = utc_now()
            atomic_write_json(milestone_dir / "milestone.json", milestone)
            if "context" in payload:
                atomic_write_text(
                    milestone_dir / "context.md", str(payload.get("context") or "").rstrip() + "\n"
                )
            self._sync_roadmap_milestone(sdd, milestone)
            if options.get("activate"):
                state = self._read_required_json(sdd, "state.json")
                state["active_milestone"] = milestone_id
                state["status"] = (
                    "planning"
                    if milestone.get("status") == "planned"
                    else milestone.get("status", "active")
                )
                state["updated_at"] = utc_now()
                atomic_write_json(sdd / "state.json", state)
            self._event(sdd, "milestone_updated", milestone_id=milestone_id, fields=sorted(payload))
            render_all(project_root)
        return {"ok": True, "milestone": milestone}

    def _milestone(
        self, sdd: Path, milestone_id: str | None
    ) -> tuple[str, Path, dict[str, Any], dict[str, Any]]:
        state = self._read_required_json(sdd, "state.json")
        milestone_id = validate_id(
            milestone_id or state.get("active_milestone") or "", "milestone id"
        )
        milestone_dir = sdd / "milestones" / milestone_id
        milestone = self._read_required_json_path(milestone_dir / "milestone.json")
        plan = self._read_required_json_path(milestone_dir / "plan.json")
        self._require_object_list(plan, "tasks", "plan tasks")
        return milestone_id, milestone_dir, milestone, plan

    def set_plan(
        self, root: str | None, payload: dict[str, Any], options: dict[str, Any]
    ) -> dict[str, Any]:
        project_root = self._root(root)
        sdd = self._require(project_root)
        raw_tasks = payload.get("tasks")
        if not isinstance(raw_tasks, list):
            raise ValueError("set_plan requires payload.tasks to be a list")
        if not raw_tasks:
            raise ValueError("set_plan requires payload.tasks")
        with project_lock(sdd), project_transaction(sdd):
            milestone_id, milestone_dir, milestone, old_plan = self._milestone(
                sdd, payload.get("milestone_id")
            )
            old_tasks = self._require_object_list(old_plan, "tasks", "plan tasks")
            if any(task.get("status") == "in_progress" for task in old_tasks) and not options.get(
                "force"
            ):
                raise ValueError(
                    "Cannot replace a plan while tasks are in progress; reconcile them or use options.force"
                )
            existing_by_id = {task.get("id"): task for task in old_tasks}
            tasks: list[dict[str, Any]] = []
            ids: list[str] = []
            for index, raw in enumerate(raw_tasks, start=1):
                if not isinstance(raw, dict):
                    raise ValueError(f"Task {index} is not an object")
                task_id = validate_id(raw.get("id") or f"{milestone_id}-T{index:03d}", "task id")
                if task_id in ids:
                    raise ValueError(f"Duplicate task id: {task_id}")
                ids.append(task_id)
                previous = existing_by_id.get(task_id, {})
                status = raw["status"] if "status" in raw else previous.get("status", "pending")
                if status not in _TASK_STATES:
                    raise ValueError(f"Invalid status for {task_id}: {status}")
                if (
                    status != "pending"
                    and task_id not in existing_by_id
                    and not options.get("reconcile")
                ):
                    raise ValueError(
                        f"Task {task_id} has status {status}; set_plan only creates pending tasks "
                        "unless options.reconcile is used"
                    )
                risk = raw["risk"] if "risk" in raw else previous.get("risk", "medium")
                if risk not in _RISKS:
                    raise ValueError(f"Invalid task risk: {risk}")
                task = {
                    "id": task_id,
                    "milestone_id": milestone_id,
                    "title": raw["title"] if "title" in raw else previous.get("title") or task_id,
                    "objective": raw["objective"]
                    if "objective" in raw
                    else previous.get("objective", ""),
                    "status": status,
                    "priority": raw["priority"]
                    if "priority" in raw
                    else previous.get("priority", "normal"),
                    "risk": risk,
                    "kind": raw["kind"]
                    if "kind" in raw
                    else previous.get("kind", "implementation"),
                    "depends_on": _string_list(
                        raw.get("depends_on", previous.get("depends_on", [])), "task dependencies"
                    ),
                    "acceptance": _string_list(
                        raw.get("acceptance", previous.get("acceptance", [])), "task acceptance"
                    ),
                    "exit_criteria_ids": _string_list(
                        raw.get("exit_criteria_ids", previous.get("exit_criteria_ids", [])),
                        "task exit criterion ids",
                    ),
                    "file_scope": _string_list(
                        raw.get("file_scope", previous.get("file_scope", [])), "task file scope"
                    ),
                    "requirement_ids": _string_list(
                        raw.get("requirement_ids", previous.get("requirement_ids", [])),
                        "task requirement ids",
                    ),
                    "decision_ids": _decision_list(
                        raw.get("decision_ids", previous.get("decision_ids", []))
                    ),
                    "agent_role": raw["agent_role"]
                    if "agent_role" in raw
                    else previous.get("agent_role", "builder"),
                    "notes": raw["notes"] if "notes" in raw else previous.get("notes", ""),
                    "summary": raw["summary"] if "summary" in raw else previous.get("summary", ""),
                    "evidence_ids": previous.get("evidence_ids", []),
                    "created_at": previous.get("created_at") or utc_now(),
                    "updated_at": utc_now(),
                }
                tasks.append(task)
            dag_errors = _validate_dag(tasks)
            if dag_errors:
                raise ValueError("; ".join(dag_errors))
            plan = {
                "schema_version": 1,
                "milestone_id": milestone_id,
                "revision": int(old_plan.get("revision") or 0) + 1,
                "strategy": payload.get("strategy") or "dependency_and_conflict_safe",
                "planning_notes": payload.get("planning_notes") or "",
                "tasks": tasks,
                "updated_at": utc_now(),
            }
            atomic_write_json(milestone_dir / "plan.json", plan)
            if "context" in payload:
                atomic_write_text(
                    milestone_dir / "context.md", str(payload.get("context") or "").rstrip() + "\n"
                )
            milestone["status"] = "ready"
            milestone["updated_at"] = utc_now()
            atomic_write_json(milestone_dir / "milestone.json", milestone)
            self._sync_roadmap_milestone(sdd, milestone)
            state = self._read_required_json(sdd, "state.json")
            state.update(
                {"active_milestone": milestone_id, "status": "ready", "updated_at": utc_now()}
            )
            atomic_write_json(sdd / "state.json", state)
            self._event(
                sdd,
                "plan_saved",
                milestone_id=milestone_id,
                task_count=len(tasks),
                revision=plan["revision"],
            )
            render_all(project_root)
        return {
            "ok": True,
            "milestone_id": milestone_id,
            "revision": plan["revision"],
            "task_count": len(tasks),
            "next": self.next(str(project_root), milestone_id, {}, {"limit": 4}),
        }

    @staticmethod
    def _sync_roadmap_milestone(sdd: Path, milestone: dict[str, Any]) -> None:
        roadmap = SDDService._read_required_json(sdd, "roadmap.json")
        rows = SDDService._require_object_list(roadmap, "milestones", "milestones")
        rows = [milestone if item.get("id") == milestone.get("id") else item for item in rows]
        if not any(item.get("id") == milestone.get("id") for item in rows):
            rows.append(milestone)
        roadmap["milestones"] = rows
        atomic_write_json(sdd / "roadmap.json", roadmap)

    @staticmethod
    def _ready_tasks(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        done = {task.get("id") for task in tasks if task.get("status") in {"done", "skipped"}}
        return [
            task
            for task in tasks
            if task.get("status") == "pending"
            and all(dep in done for dep in _list(task.get("depends_on")))
        ]

    def next(
        self, root: str | None, target: str | None, payload: dict[str, Any], options: dict[str, Any]
    ) -> dict[str, Any]:
        project_root = self._root(root)
        sdd = self._require(project_root)
        milestone_id, _, milestone, plan = self._milestone(
            sdd, payload.get("milestone_id") or target
        )
        all_tasks = plan.get("tasks", [])
        ready = sorted(
            self._ready_tasks(all_tasks),
            key=lambda task: (task.get("priority") != "high", task.get("id")),
        )
        active = [task for task in all_tasks if task.get("status") == "in_progress"]
        config = self._read_required_json(sdd, "config.json")
        limit = max(1, min(int(options.get("limit") or config.get("max_parallel") or 4), 12))
        allow_parallel = bool(options.get("allow_parallel", True))
        if not milestone.get("interfaces_stable") and any(
            task.get("kind") == "implementation" for task in ready + active
        ):
            allow_parallel = False

        eligible: list[dict[str, Any]] = []
        for task in ready:
            if any(_tasks_conflict(task, running) for running in active):
                continue
            if task.get("risk") == "critical" and active:
                continue
            if any(running.get("risk") == "critical" for running in active):
                continue
            if active and not allow_parallel:
                continue
            eligible.append(task)

        wave: list[dict[str, Any]] = []
        for task in eligible:
            if len(wave) >= limit:
                break
            if (task.get("risk") == "critical" and wave) or any(
                selected.get("risk") == "critical" for selected in wave
            ):
                continue
            if not allow_parallel and wave:
                break
            if any(_tasks_conflict(task, selected) for selected in wave):
                continue
            wave.append(task)
        if not wave and eligible:
            wave = [eligible[0]]
        reason = "dependency and file-scope safe"
        if ready and not allow_parallel:
            reason = "parallel disabled until interfaces are stable"
        elif ready and not eligible and active:
            reason = "ready tasks conflict with or must wait for active work"
        elif not ready and any(task.get("status") == "blocked" for task in all_tasks):
            reason = "no dependency-ready task; blocked tasks require recovery"
        elif (
            not ready
            and all_tasks
            and all(task.get("status") in {"done", "skipped"} for task in all_tasks)
        ):
            reason = "milestone tasks are terminal; verify and finalize the milestone"
        elif not ready and all_tasks:
            reason = "no dependency-ready task; validate the plan and dependency graph"
        return {
            "ok": True,
            "milestone_id": milestone_id,
            "plan_revision": plan.get("revision", 0),
            "ready_count": len(ready),
            "eligible_count": len(eligible),
            "active_count": len(active),
            "wave": [_compact(task) for task in wave],
            "parallel": len(wave) > 1,
            "reason": reason,
        }

    def _find_task(self, plan: dict[str, Any], task_id: str) -> dict[str, Any]:
        for task in plan.get("tasks", []):
            if task.get("id") == task_id:
                return task
        raise ValueError(f"Unknown task: {task_id}")

    def _locate_task(
        self, sdd: Path, task_id: str
    ) -> tuple[str, Path, dict[str, Any], dict[str, Any], dict[str, Any]]:
        roadmap = self._read_required_json(sdd, "roadmap.json")
        milestones = self._require_object_list(roadmap, "milestones", "milestones")
        for item in milestones:
            milestone_id = str(item.get("id") or "")
            if not milestone_id:
                continue
            try:
                resolved_id, milestone_dir, milestone, plan = self._milestone(sdd, milestone_id)
                task = self._find_task(plan, task_id)
                return resolved_id, milestone_dir, milestone, plan, task
            except ValueError:
                continue
        raise ValueError(f"Unknown task: {task_id}")

    def update_task(
        self, root: str | None, target: str | None, payload: dict[str, Any], options: dict[str, Any]
    ) -> dict[str, Any]:
        """Update one task without replacing or retransmitting the whole milestone plan."""

        project_root = self._root(root)
        sdd = self._require(project_root)
        task_id = validate_id(target or payload.get("task_id") or "", "task id")
        scalar_fields = {
            "title",
            "objective",
            "priority",
            "risk",
            "kind",
            "agent_role",
            "notes",
            "summary",
        }
        list_fields = {
            "depends_on",
            "acceptance",
            "file_scope",
            "requirement_ids",
            "decision_ids",
            "exit_criteria_ids",
        }
        with project_lock(sdd), project_transaction(sdd):
            if payload.get("milestone_id"):
                milestone_id, milestone_dir, _, plan = self._milestone(
                    sdd, payload.get("milestone_id")
                )
                task = self._find_task(plan, task_id)
            else:
                milestone_id, milestone_dir, _, plan, task = self._locate_task(sdd, task_id)
            expected_revision = options.get("expected_revision")
            if expected_revision is not None and int(expected_revision) != int(
                plan.get("revision") or 0
            ):
                raise ValueError(
                    f"Plan revision changed: expected {expected_revision}, current {plan.get('revision', 0)}"
                )
            if "status" in payload:
                raise ValueError("Use operation=transition to change task status")
            if (
                "depends_on" in payload
                and task.get("status") != "pending"
                and not options.get("force")
            ):
                raise ValueError(
                    "Dependencies can change only while a task is pending unless options.force is set"
                )
            candidate = dict(task)
            for key in scalar_fields:
                if key in payload:
                    value = payload[key]
                    if key == "risk" and value not in _RISKS:
                        raise ValueError(f"Invalid task risk: {value}")
                    candidate[key] = value
            for key in list_fields:
                if key in payload:
                    if key == "decision_ids":
                        candidate[key] = _decision_list(payload[key])
                    elif key == "exit_criteria_ids":
                        candidate[key] = _string_list(payload[key], "task exit criterion ids")
                    else:
                        candidate[key] = _string_list(payload[key], f"task {key}")
            if (
                "file_scope" in payload
                and task.get("status") == "in_progress"
                and not options.get("force")
            ):
                active = [
                    item
                    for item in plan.get("tasks", [])
                    if item.get("status") == "in_progress" and item.get("id") != task_id
                ]
                conflicts = [item.get("id") for item in active if _tasks_conflict(candidate, item)]
                if conflicts:
                    raise ValueError(
                        f"Updated scope for {task_id} conflicts with active tasks: {', '.join(map(str, conflicts))}"
                    )
            candidate["updated_at"] = utc_now()
            updated_tasks = [
                candidate if item.get("id") == task_id else item for item in plan.get("tasks", [])
            ]
            dag_errors = _validate_dag(updated_tasks)
            if dag_errors:
                raise ValueError("; ".join(dag_errors))
            plan["tasks"] = updated_tasks
            plan["revision"] = int(plan.get("revision") or 0) + 1
            plan["updated_at"] = utc_now()
            atomic_write_json(milestone_dir / "plan.json", plan)
            self._event(
                sdd,
                "task_updated",
                task_id=task_id,
                milestone_id=milestone_id,
                fields=sorted(key for key in payload if key != "task_id"),
                plan_revision=plan["revision"],
            )
            render_all(project_root)
        return {"ok": True, "task": _compact(candidate), "plan_revision": plan["revision"]}

    def transition(
        self, root: str | None, target: str | None, payload: dict[str, Any], options: dict[str, Any]
    ) -> dict[str, Any]:
        project_root = self._root(root)
        sdd = self._require(project_root)
        task_id = validate_id(target or payload.get("task_id") or "", "task id")
        new_status = str(payload.get("status") or "").lower()
        if new_status not in _TASK_STATES:
            raise ValueError(f"Invalid task status: {new_status}")
        allowed = {
            "pending": {"in_progress", "blocked", "skipped"},
            "in_progress": {"done", "blocked", "pending"},
            "blocked": {"pending", "in_progress", "skipped"},
            "done": {"in_progress"},
            "skipped": {"pending"},
        }
        with project_lock(sdd), project_transaction(sdd):
            if payload.get("milestone_id"):
                milestone_id, milestone_dir, milestone, plan = self._milestone(
                    sdd, payload.get("milestone_id")
                )
                task = self._find_task(plan, task_id)
            else:
                milestone_id, milestone_dir, milestone, plan, task = self._locate_task(sdd, task_id)
            expected_revision = options.get("expected_revision")
            if expected_revision is not None and int(expected_revision) != int(
                plan.get("revision") or 0
            ):
                raise ValueError(
                    f"Plan revision changed: expected {expected_revision}, current {plan.get('revision', 0)}"
                )
            old_status = task.get("status", "pending")
            if new_status != old_status and new_status not in allowed.get(old_status, set()):
                raise ValueError(f"Invalid transition {old_status} -> {new_status} for {task_id}")
            if payload.get("evidence"):
                if not isinstance(payload["evidence"], dict):
                    raise ValueError("Evidence must be an object")
                self._validate_evidence_payload(task, payload["evidence"], task_id=task_id)
            state = self._read_required_json(sdd, "state.json")
            if (
                new_status == "in_progress"
                and old_status != "in_progress"
                and not options.get("force")
            ):
                if state.get("active_milestone") and state.get("active_milestone") != milestone_id:
                    raise ValueError(
                        f"Cannot start {task_id}; active milestone is {state.get('active_milestone')}, not {milestone_id}"
                    )
                done = {
                    item.get("id")
                    for item in plan.get("tasks", [])
                    if item.get("status") in {"done", "skipped"}
                }
                unmet = [dep for dep in _list(task.get("depends_on")) if dep not in done]
                if unmet:
                    raise ValueError(
                        f"Cannot start {task_id}; incomplete dependencies: {', '.join(map(str, unmet))}"
                    )
                active = [
                    item
                    for item in plan.get("tasks", [])
                    if item.get("status") == "in_progress" and item.get("id") != task_id
                ]
                if (
                    active
                    and not milestone.get("interfaces_stable")
                    and (
                        task.get("kind") == "implementation"
                        or any(item.get("kind") == "implementation" for item in active)
                    )
                ):
                    raise ValueError(
                        f"Cannot start {task_id}; implementation interfaces are unstable"
                    )
                if task.get("risk") == "critical" and active:
                    raise ValueError(
                        f"Cannot start critical task {task_id} while other tasks are active"
                    )
                if any(item.get("risk") == "critical" for item in active):
                    raise ValueError(f"Cannot start {task_id} while a critical task is active")
                conflicts = [item.get("id") for item in active if _tasks_conflict(task, item)]
                if conflicts:
                    raise ValueError(
                        f"Cannot start {task_id}; file scope conflicts with active tasks: {', '.join(map(str, conflicts))}"
                    )
            task["status"] = new_status
            task["updated_at"] = utc_now()
            if payload.get("summary") is not None:
                task["summary"] = str(payload.get("summary") or "")
            if payload.get("notes") is not None:
                task["notes"] = str(payload.get("notes") or "")
            if payload.get("blocked_reason") is not None:
                task["blocked_reason"] = str(payload.get("blocked_reason") or "")
            plan["revision"] = int(plan.get("revision") or 0) + 1
            plan["updated_at"] = utc_now()
            atomic_write_json(milestone_dir / "plan.json", plan)
            current = {
                item.get("id")
                for item in plan.get("tasks", [])
                if item.get("status") == "in_progress" and item.get("id")
            }
            state["current_tasks"] = sorted(current)
            state["updated_at"] = utc_now()
            if payload.get("evidence"):
                if payload["evidence"].get("task_id") not in (None, task_id):
                    raise ValueError(
                        f"Evidence task_id {payload['evidence'].get('task_id')} does not match target {task_id}"
                    )
                evidence = self._record_evidence_locked(
                    project_root, sdd, milestone_dir, task, payload["evidence"]
                )
                plan["revision"] += 1
                plan["updated_at"] = utc_now()
                atomic_write_json(milestone_dir / "plan.json", plan)
            else:
                evidence = None
            terminal_states = {item.get("status") for item in plan.get("tasks", [])}
            if terminal_states and terminal_states <= {"done", "skipped"}:
                milestone["status"] = "done"
                state["status"] = "verifying"
            elif current:
                milestone["status"] = "in_progress"
                state["status"] = "executing"
            elif any(
                item.get("status") == "blocked" for item in plan.get("tasks", [])
            ) and not self._ready_tasks(plan.get("tasks", [])):
                milestone["status"] = "blocked"
                state["status"] = "blocked"
            else:
                milestone["status"] = "ready"
                state["status"] = "ready"
            atomic_write_json(sdd / "state.json", state)
            milestone["updated_at"] = utc_now()
            atomic_write_json(milestone_dir / "milestone.json", milestone)
            self._sync_roadmap_milestone(sdd, milestone)
            self._event(
                sdd,
                "task_transition",
                task_id=task_id,
                from_status=old_status,
                to_status=new_status,
                summary=task.get("summary"),
                plan_revision=plan["revision"],
            )
            render_all(project_root)
        return {
            "ok": True,
            "task": _compact(task),
            "evidence": evidence,
            "milestone_status": milestone.get("status"),
            "plan_revision": plan["revision"],
        }

    def _record_evidence_locked(
        self,
        project_root: Path,
        sdd: Path,
        milestone_dir: Path,
        task: dict[str, Any] | None,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        self._validate_evidence_payload(task, payload, task_id=task.get("id") if task else None)
        if payload.get("exit_criteria_ids"):
            milestone = self._read_required_json_path(milestone_dir / "milestone.json")
            criteria = milestone.get("exit_criteria_records")
            if not isinstance(criteria, list):
                raise ValueError(
                    "Exit-criterion evidence requires structured milestone exit_criteria_records"
                )
            active_ids = {
                item.get("id")
                for item in criteria
                if isinstance(item, dict) and item.get("status") == "active"
            }
            requested = set(
                _string_list(payload.get("exit_criteria_ids"), "evidence exit criterion ids")
            )
            unknown = requested - active_ids
            if unknown:
                raise ValueError(
                    "Evidence can only link active exit criteria: " + ", ".join(sorted(unknown))
                )
            task_criteria = set(
                _string_list((task or {}).get("exit_criteria_ids"), "task exit criterion ids")
            )
            if not task or not requested <= task_criteria:
                raise ValueError("Evidence exit criteria must also be linked to the target task")
        existing = read_jsonl(milestone_dir / "evidence.jsonl")
        evidence_id = payload.get("id") or _next_numeric_id(
            [item.get("id", "") for item in existing], "E", 6
        )
        evidence_id = validate_id(evidence_id, "evidence id")
        result_text = str(payload.get("result") or "").strip()
        if not any(
            (result_text, payload.get("command"), payload.get("artifact"), payload.get("details"))
        ):
            raise ValueError("Evidence requires a result, command, artifact, or details")
        passed = payload["passed"] if "passed" in payload else None
        evidence = {
            "id": evidence_id,
            "at": utc_now(),
            "task_id": payload.get("task_id") or (task.get("id") if task else None),
            "type": payload.get("type") or "test",
            "result": result_text,
            "passed": passed,
            "command": payload.get("command") or "",
            "artifact": payload.get("artifact") or "",
            "exit_criteria_ids": _string_list(
                payload.get("exit_criteria_ids"), "evidence exit criterion ids"
            ),
            "requirement_ids": _list(
                payload.get("requirement_ids") or (task.get("requirement_ids", []) if task else [])
            ),
            "details": payload.get("details") or "",
        }
        append_jsonl(milestone_dir / "evidence.jsonl", evidence)
        if task is not None:
            task.setdefault("evidence_ids", [])
            if evidence_id not in task["evidence_ids"]:
                task["evidence_ids"].append(evidence_id)
        self._event(
            sdd,
            "evidence_recorded",
            evidence_id=evidence_id,
            task_id=evidence.get("task_id"),
            result=evidence.get("result"),
        )
        return evidence

    @staticmethod
    def _validate_evidence_payload(
        task: dict[str, Any] | None, payload: dict[str, Any], *, task_id: str | None
    ) -> None:
        supplied_task_id = payload.get("task_id")
        if supplied_task_id not in (None, task_id):
            raise ValueError(f"Evidence task_id {supplied_task_id} does not match target {task_id}")
        if not any(
            str(payload.get(key) or "").strip()
            for key in ("result", "command", "artifact", "details")
        ):
            raise ValueError("Evidence requires a result, command, artifact, or details")
        criterion_ids = payload.get("exit_criteria_ids", [])
        if not isinstance(criterion_ids, list) or any(
            not isinstance(item, str) or not item.strip() for item in criterion_ids
        ):
            raise ValueError("Evidence exit_criteria_ids must be a list of non-empty strings")
        passed = payload.get("passed")
        if passed is not None and not isinstance(passed, bool):
            raise ValueError("Evidence passed must be true, false, or omitted")

    def record_evidence(
        self, root: str | None, target: str | None, payload: dict[str, Any], options: dict[str, Any]
    ) -> dict[str, Any]:
        project_root = self._root(root)
        sdd = self._require(project_root)
        task_id = target or payload.get("task_id")
        if task_id:
            task_id = validate_id(task_id, "task id")
        with project_lock(sdd), project_transaction(sdd):
            if task_id:
                if payload.get("milestone_id"):
                    milestone_id, milestone_dir, _, plan = self._milestone(
                        sdd, payload.get("milestone_id")
                    )
                    task = self._find_task(plan, task_id)
                else:
                    milestone_id, milestone_dir, _, plan, task = self._locate_task(sdd, task_id)
            else:
                milestone_id, milestone_dir, _, plan = self._milestone(
                    sdd, payload.get("milestone_id")
                )
                task = None
            expected_revision = options.get("expected_revision")
            if expected_revision is not None and int(expected_revision) != int(
                plan.get("revision") or 0
            ):
                raise ValueError(
                    f"Plan revision changed: expected {expected_revision}, current {plan.get('revision', 0)}"
                )
            evidence = self._record_evidence_locked(project_root, sdd, milestone_dir, task, payload)
            plan["revision"] = int(plan.get("revision") or 0) + 1
            plan["updated_at"] = utc_now()
            atomic_write_json(milestone_dir / "plan.json", plan)
            render_all(project_root)
        return {
            "ok": True,
            "milestone_id": milestone_id,
            "evidence": evidence,
            "plan_revision": plan["revision"],
        }

    def finalize_milestone(
        self, root: str | None, target: str | None, payload: dict[str, Any], options: dict[str, Any]
    ) -> dict[str, Any]:
        project_root = self._root(root)
        sdd = self._require(project_root)
        summary = str(payload.get("summary") or "Milestone completed and verified.").strip()
        forced = bool(options.get("force"))
        override_reason = str(payload.get("override_reason") or "").strip()
        if forced and not override_reason:
            raise ValueError("Forced finalization requires payload.override_reason")
        with project_lock(sdd), project_transaction(sdd):
            milestone_id, milestone_dir, milestone, plan = self._milestone(
                sdd, target or payload.get("milestone_id")
            )
            expected_revision = options.get("expected_revision")
            if expected_revision is not None and int(expected_revision) != int(
                plan.get("revision") or 0
            ):
                raise ValueError(
                    f"Plan revision changed: expected {expected_revision}, current {plan.get('revision', 0)}"
                )
            state = self._read_required_json(sdd, "state.json")
            if (
                state.get("active_milestone")
                and state.get("active_milestone") != milestone_id
                and not options.get("force")
            ):
                raise ValueError(
                    f"Cannot finalize {milestone_id}; active milestone is {state.get('active_milestone')}"
                )
            if not plan.get("tasks") and not options.get("force"):
                raise ValueError("Milestone has no planned tasks")
            incomplete = [
                task.get("id")
                for task in plan.get("tasks", [])
                if task.get("status") not in {"done", "skipped"}
            ]
            if incomplete and not options.get("force"):
                raise ValueError(
                    f"Milestone has incomplete tasks: {', '.join(str(item) for item in incomplete)}"
                )
            validation = self.validate(str(project_root), {"record": False}, {"detail": "normal"})
            # Finalize just-in-time: defects in future, not-yet-active milestones should
            # remain visible in project health without blocking delivery of this one.
            task_ids = {str(task.get("id")) for task in plan.get("tasks", [])}
            milestone_criteria = milestone.get("exit_criteria_records", [])
            if not isinstance(milestone_criteria, list):
                milestone_criteria = []
            active_criteria_ids = {
                item.get("id")
                for item in milestone_criteria
                if isinstance(item, dict) and item.get("status") == "active"
            }
            legacy_criteria_unmapped = (
                bool(milestone.get("exit_criteria")) and not active_criteria_ids
            )
            relevant_targets = {
                None,
                milestone_id,
                *task_ids,
                *map(str, milestone.get("requirement_ids", [])),
                *map(
                    str,
                    (
                        requirement_id
                        for task in plan.get("tasks", [])
                        for requirement_id in task.get("requirement_ids", [])
                    ),
                ),
                *map(
                    str,
                    (item.get("id") for item in milestone_criteria),
                ),
                *map(
                    str,
                    (
                        criterion_id
                        for task in plan.get("tasks", [])
                        for criterion_id in task.get("exit_criteria_ids", [])
                    ),
                ),
            }
            blocking = [
                item
                for item in validation.get("findings", [])
                if (
                    item.get("severity") == "error"
                    and item.get("milestone_id") in (None, milestone_id)
                    and (
                        item.get("target") in relevant_targets
                        or item.get("milestone_id") == milestone_id
                    )
                )
                or (item.get("code") == "task.evidence_missing" and item.get("target") in task_ids)
            ]
            if legacy_criteria_unmapped:
                blocking.extend(
                    item
                    for item in validation.get("findings", [])
                    if item.get("code") == "milestone.exit_criteria_unmapped"
                    and item.get("target") == milestone_id
                )
            if blocking and not options.get("force"):
                codes = ", ".join(sorted({str(item.get("code")) for item in blocking}))
                raise ValueError(
                    f"Milestone cannot be finalized until validation blockers are resolved: {codes}"
                )
            milestone["status"] = "overridden" if forced else "verified"
            milestone["completed_at"] = utc_now()
            milestone["updated_at"] = utc_now()
            atomic_write_json(milestone_dir / "milestone.json", milestone)
            override_prefix = (
                f"> **Administrative override — not verified.** {override_reason}\n\n"
                if forced
                else ""
            )
            atomic_write_text(
                milestone_dir / "summary.md",
                f"# {milestone_id} summary\n\n{override_prefix}{summary}\n",
            )
            self._sync_roadmap_milestone(sdd, milestone)
            roadmap = self._read_required_json(sdd, "roadmap.json")
            remaining = [
                item
                for item in roadmap.get("milestones", [])
                if item.get("id") != milestone_id
                and item.get("status") not in {"verified", "overridden", "cancelled"}
            ]
            state["current_tasks"] = []
            state["active_milestone"] = remaining[0].get("id") if remaining else None
            state["status"] = (
                "overridden"
                if not remaining and forced
                else "verifying"
                if remaining and remaining[0].get("status") == "done"
                else "planning"
                if remaining
                else "complete"
            )
            state["updated_at"] = utc_now()
            atomic_write_json(sdd / "state.json", state)
            project = self._read_project(sdd)
            if not remaining:
                project["status"] = "overridden" if forced else "complete"
                project["updated_at"] = utc_now()
                atomic_write_json(sdd / "project.json", project)
            self._event(
                sdd,
                "milestone_finalized",
                milestone_id=milestone_id,
                next_milestone=state.get("active_milestone"),
                plan_revision=plan.get("revision", 0),
                forced=forced,
                override_reason=override_reason if forced else None,
            )
            render_all(project_root)
        return {
            "ok": True,
            "milestone_id": milestone_id,
            "status": milestone["status"],
            "forced": forced,
            "override_reason": override_reason if forced else None,
            "next_milestone": state.get("active_milestone"),
            "project_status": project.get("status"),
            "plan_revision": plan.get("revision", 0),
            "health": {"score": validation.get("score"), "counts": validation.get("counts")},
        }

    def record_decision(
        self, root: str | None, target: str | None, payload: dict[str, Any], _: dict[str, Any]
    ) -> dict[str, Any]:
        project_root = self._root(root)
        sdd = self._require(project_root)
        with project_lock(sdd), project_transaction(sdd):
            existing = [path.stem for path in (sdd / "decisions").glob("ADR-*.json")]
            decision_id = _decision_id(
                target or payload.get("id") or _next_numeric_id(existing, "ADR-", 4)
            )
            previous = read_json(sdd / "decisions" / f"{decision_id}.json", {}) or {}
            decision = {
                "id": decision_id,
                "title": payload.get("title") or previous.get("title") or decision_id,
                "status": payload.get("status") or previous.get("status") or "accepted",
                "context": payload.get("context")
                if "context" in payload
                else previous.get("context", ""),
                "decision": payload.get("decision")
                if "decision" in payload
                else previous.get("decision", ""),
                "alternatives": _string_list(
                    payload.get("alternatives", previous.get("alternatives", [])),
                    "decision alternatives",
                ),
                "consequences": _string_list(
                    payload.get("consequences", previous.get("consequences", [])),
                    "decision consequences",
                ),
                "requirement_ids": _string_list(
                    payload.get("requirement_ids", previous.get("requirement_ids", [])),
                    "decision requirement ids",
                ),
                "created_at": previous.get("created_at") or payload.get("created_at") or utc_now(),
                "updated_at": utc_now(),
            }
            if decision["status"] not in _DECISION_STATES:
                raise ValueError(f"Invalid decision status: {decision['status']}")
            atomic_write_json(sdd / "decisions" / f"{decision_id}.json", decision)
            self._event(
                sdd, "decision_recorded", decision_id=decision_id, title=decision.get("title")
            )
            render_decision_index(project_root)
        return {"ok": True, "decision": _compact(decision)}

    def context_pack(
        self, root: str | None, target: str | None, payload: dict[str, Any], options: dict[str, Any]
    ) -> dict[str, Any]:
        project_root = self._root(root)
        sdd = self._require(project_root)
        config = self._read_required_json(sdd, "config.json")
        budget = int(options.get("budget_tokens") or config.get("context_budget_tokens") or 12000)
        task_id = target or payload.get("task_id")
        milestone_id = payload.get("milestone_id")
        if task_id and not milestone_id:
            milestone_id, _, _, _, _ = self._locate_task(sdd, validate_id(task_id, "task id"))
        return {
            "ok": True,
            **build_context_pack(
                project_root,
                milestone_id=milestone_id,
                task_id=task_id,
                budget_tokens=max(2000, min(budget, 80000)),
                checkpoint_id=payload.get("checkpoint_id"),
                include_git=bool(options.get("include_git", True)),
            ),
        }

    def context_checkpoint(
        self, root: str | None, target: str | None, payload: dict[str, Any], _: dict[str, Any]
    ) -> dict[str, Any]:
        project_root = self._root(root)
        sdd = self._require(project_root)
        task = None
        if payload.get("task_id"):
            _, _, _, _, task = self._locate_task(sdd, validate_id(payload["task_id"], "task id"))
        with project_lock(sdd), project_transaction(sdd):
            snapshot = create_checkpoint(project_root, target or payload.get("id"), task)
            state = self._read_required_json(sdd, "state.json")
            state["last_checkpoint"] = snapshot["id"]
            state["updated_at"] = utc_now()
            atomic_write_json(sdd / "state.json", state)
            self._event(
                sdd,
                "checkpoint_created",
                checkpoint_id=snapshot["id"],
                task_id=snapshot.get("task_id"),
            )
            render_all(project_root)
            # Capture the checkpoint event and state pointer so an immediate delta is empty.
            snapshot = create_checkpoint(project_root, snapshot["id"], task)
        return {"ok": True, "checkpoint": snapshot}

    def context_delta(
        self, root: str | None, target: str | None, payload: dict[str, Any], _: dict[str, Any]
    ) -> dict[str, Any]:
        project_root = self._root(root)
        sdd = self._require(project_root)
        checkpoint_id = validate_id(target or payload.get("checkpoint_id") or "", "checkpoint id")
        task = None
        if payload.get("task_id"):
            _, _, _, _, task = self._locate_task(sdd, validate_id(payload["task_id"], "task id"))
        return {"ok": True, **checkpoint_delta(project_root, checkpoint_id, task)}

    def validate(
        self, root: str | None, payload: dict[str, Any], options: dict[str, Any]
    ) -> dict[str, Any]:
        project_root = self._root(root)
        sdd = self._require(project_root)
        project = self._read_project(sdd)
        config = self._read_required_json(sdd, "config.json")
        state = self._read_required_json(sdd, "state.json")
        requirements = self._read_required_json(sdd, "requirements.json")
        requirement_rows = self._require_object_list(requirements, "requirements", "requirements")
        roadmap = self._read_required_json(sdd, "roadmap.json")
        req_ids = {str(item["id"]) for item in requirement_rows if item.get("id")}
        decision_ids = {path.stem for path in (sdd / "decisions").glob("*.json")}
        milestone_rows = self._require_object_list(roadmap, "milestones", "milestones")
        milestone_ids = {str(item["id"]) for item in milestone_rows if item.get("id")}
        findings: list[dict[str, Any]] = []

        def add(
            severity: str,
            code: str,
            message: str,
            target: str | None = None,
            **details: Any,
        ) -> None:
            if config.get("strict") and severity == "warning" and code != "artifact.large":
                severity = "error"
            findings.append(
                _compact(
                    {
                        "severity": severity,
                        "code": code,
                        "message": message,
                        "target": target,
                        **details,
                    }
                )
            )

        requirement_id_list = [str(item["id"]) for item in requirement_rows if item.get("id")]
        for duplicate in sorted(
            {item for item in requirement_id_list if requirement_id_list.count(item) > 1}
        ):
            add(
                "error",
                "requirement.duplicate_id",
                f"Duplicate requirement id {duplicate}",
                duplicate,
            )
        milestone_id_list = [str(item["id"]) for item in milestone_rows if item.get("id")]
        for duplicate in sorted(
            {item for item in milestone_id_list if milestone_id_list.count(item) > 1}
        ):
            add("error", "milestone.duplicate_id", f"Duplicate milestone id {duplicate}", duplicate)
        if state.get("active_milestone") and state.get("active_milestone") not in milestone_ids:
            add(
                "error",
                "state.unknown_milestone",
                "State references an unknown active milestone",
                state.get("active_milestone"),
            )

        if not project.get("goal"):
            add("error", "project.goal_missing", "Project goal is empty")
        if not project.get("success_criteria") and project.get("mode") != "quick":
            add("warning", "project.success_missing", "No project success criteria recorded")
        if project.get("mode") in {"deep", "program"}:
            architecture = (
                (sdd / "architecture.md").read_text(encoding="utf-8")
                if (sdd / "architecture.md").exists()
                else ""
            )
            if len(architecture.strip()) < 80 or "Not established" in architecture:
                add(
                    "warning",
                    "architecture.missing",
                    "Deep/program project has no meaningful architecture record",
                )
        for req in requirement_rows:
            if not req.get("statement"):
                add(
                    "error",
                    "requirement.statement_missing",
                    "Requirement has no statement",
                    req.get("id"),
                )
            if not req.get("acceptance"):
                add(
                    "warning",
                    "requirement.acceptance_missing",
                    "Requirement has no acceptance criteria",
                    req.get("id"),
                )

        linked_requirements: set[str] = set()
        all_tasks: dict[str, dict[str, Any]] = {}
        for milestone in milestone_rows:
            milestone_id = str(milestone["id"]) if milestone.get("id") else None
            criteria_are_structured = "exit_criteria_records" in milestone
            criterion_records = (
                _validate_exit_criterion_records(
                    milestone_id or "",
                    milestone.get("exit_criteria_records"),
                    milestone.get("exit_criteria_schema_version"),
                )
                if criteria_are_structured
                else []
            )
            active_criteria = {
                item["id"]: item["text"] for item in criterion_records if item["status"] == "active"
            }
            if criteria_are_structured and (
                type(milestone.get("exit_criteria_schema_version")) is not int
                or milestone.get("exit_criteria_schema_version") != 1
            ):
                add(
                    "error",
                    "milestone.exit_criteria_schema_invalid",
                    "Structured exit criteria require exit_criteria_schema_version 1",
                    milestone_id,
                )
            linked_requirements.update(map(str, milestone.get("requirement_ids", [])))
            milestone_file = read_json(sdd / "milestones" / str(milestone_id) / "milestone.json")
            if not milestone_file:
                add(
                    "error",
                    "milestone.file_missing",
                    "Milestone metadata file is missing",
                    milestone_id,
                )
            elif any(
                milestone_file.get(key) != milestone.get(key)
                for key in (
                    "title",
                    "status",
                    "objective",
                    "interfaces_stable",
                    "requirement_ids",
                    "decision_ids",
                    "exit_criteria",
                    "exit_criteria_records",
                    "exit_criteria_schema_version",
                )
            ):
                link_drift_codes = {
                    "requirement_ids": "milestone.requirement_link_drift",
                    "decision_ids": "milestone.decision_link_drift",
                    "exit_criteria": "milestone.exit_criteria_drift",
                    "exit_criteria_records": "milestone.exit_criteria_records_drift",
                    "exit_criteria_schema_version": "milestone.exit_criteria_schema_drift",
                }
                for key, code in link_drift_codes.items():
                    if milestone_file.get(key) != milestone.get(key):
                        add(
                            "error",
                            code,
                            f"Roadmap projection differs from milestone metadata for {key}",
                            milestone_id,
                        )
                if any(
                    milestone_file.get(key) != milestone.get(key)
                    for key in ("title", "status", "objective", "interfaces_stable")
                ):
                    add(
                        "warning",
                        "milestone.roadmap_drift",
                        "Roadmap projection differs from milestone metadata",
                        milestone_id,
                    )
            if milestone.get("exit_criteria") and not criteria_are_structured:
                add(
                    "warning",
                    "milestone.exit_criteria_unmapped",
                    "Legacy prose exit criteria are not linked to evidence; update the milestone to enable proof gating",
                    milestone_id,
                )
            for req_id in milestone.get("requirement_ids", []):
                if req_id not in req_ids:
                    add(
                        "error",
                        "milestone.unknown_requirement",
                        f"Milestone references unknown requirement {req_id}",
                        milestone_id,
                    )
            for decision_id in milestone.get("decision_ids", []):
                if decision_id not in decision_ids:
                    add(
                        "error",
                        "milestone.unknown_decision",
                        f"Milestone references unknown decision {decision_id}",
                        milestone_id,
                    )
            if not milestone.get("exit_criteria"):
                add(
                    "warning",
                    "milestone.exit_missing",
                    "Milestone has no exit criteria",
                    milestone_id,
                )
            plan = self._read_required_json_path(
                sdd / "milestones" / str(milestone_id) / "plan.json"
            )
            tasks = self._require_object_list(plan, "tasks", "plan tasks")
            if plan.get("milestone_id") not in (None, milestone_id):
                add(
                    "error",
                    "plan.milestone_mismatch",
                    "Plan belongs to a different milestone",
                    milestone_id,
                )
            if not isinstance(plan.get("revision", 0), int) or int(plan.get("revision", 0)) < 0:
                add(
                    "error",
                    "plan.revision_invalid",
                    "Plan revision must be a non-negative integer",
                    milestone_id,
                )
            task_id_list = [str(item["id"]) for item in tasks if item.get("id")]
            for duplicate in sorted(
                {item for item in task_id_list if task_id_list.count(item) > 1}
            ):
                add("error", "task.duplicate_id", f"Duplicate task id {duplicate}", duplicate)
            dag_errors = _validate_dag(tasks)
            for error in dag_errors:
                add("error", "plan.invalid_dag", error, milestone_id)
            evidence = read_jsonl(sdd / "milestones" / str(milestone_id) / "evidence.jsonl")
            task_requirements = {
                str(task.get("id")): set(map(str, task.get("requirement_ids", [])))
                for task in tasks
                if task.get("id")
            }
            proof_task_ids = {
                str(task.get("id"))
                for task in tasks
                if task.get("id") and task.get("status") != "skipped"
            }
            task_criteria: dict[str, set[str]] = {
                str(task.get("id")): set(
                    map(str, _string_list(task.get("exit_criteria_ids"), "task exit criterion ids"))
                )
                for task in tasks
                if task.get("id")
            }
            criterion_success_task_ids: dict[str, set[str]] = defaultdict(set)
            for task in tasks:
                task_id = str(task.get("id") or "")
                for criterion_id in task_criteria.get(task_id, set()):
                    active_ids = set(active_criteria)
                    if criterion_id not in active_ids:
                        add(
                            "error",
                            "task.unknown_exit_criterion",
                            f"Task references unknown or retired exit criterion {criterion_id}",
                            task_id,
                            milestone_id=milestone_id,
                        )
            for item in evidence:
                task_id = str(item.get("task_id") or "")
                recorded_criterion_ids = _string_list(
                    item.get("exit_criteria_ids"), "evidence exit criterion ids"
                )
                for criterion_id in recorded_criterion_ids:
                    criterion_id = str(criterion_id)
                    known_ids = {row["id"] for row in criterion_records}
                    if criterion_id not in known_ids:
                        if any(
                            row.get("id") == criterion_id and row.get("status") == "retired"
                            for row in criterion_records
                        ):
                            continue
                        add(
                            "error",
                            "evidence.unknown_exit_criterion",
                            f"Evidence references unknown or retired exit criterion {criterion_id}",
                            str(item.get("id") or ""),
                            milestone_id=milestone_id,
                        )
                        continue
                    if criterion_id not in active_criteria:
                        continue
                    if criterion_id not in task_criteria.get(task_id, set()):
                        add(
                            "error",
                            "evidence.exit_criterion_task_mismatch",
                            f"Evidence for exit criterion {criterion_id} is not linked through its task",
                            str(item.get("id") or ""),
                            milestone_id=milestone_id,
                        )
                        continue
                    if item.get("passed") is True and task_id in proof_task_ids:
                        criterion_success_task_ids[criterion_id].add(task_id)
            evidence_by_task = Counter(item.get("task_id") for item in evidence)
            successful_evidence_by_task = Counter(
                item.get("task_id") for item in evidence if item.get("passed") is True
            )
            successful_evidence_by_requirement = {
                str(requirement_id)
                for item in evidence
                if item.get("passed") is True and str(item.get("task_id") or "") in proof_task_ids
                for requirement_id in item.get("requirement_ids", [])
                if str(requirement_id) in req_ids
                and str(requirement_id)
                in task_requirements.get(str(item.get("task_id") or ""), set())
            }
            for task in tasks:
                task_id = task.get("id")
                linked_requirements.update(map(str, task.get("requirement_ids", [])))
                if task_id:
                    if task_id in all_tasks:
                        add(
                            "error",
                            "task.global_duplicate_id",
                            "Task id is reused across milestones",
                            task_id,
                        )
                    all_tasks[task_id] = task
                if not task.get("objective"):
                    add("warning", "task.objective_missing", "Task has no objective", task_id)
                if not task.get("acceptance"):
                    add(
                        "warning",
                        "task.acceptance_missing",
                        "Task has no acceptance criteria",
                        task_id,
                    )
                for req_id in task.get("requirement_ids", []):
                    if req_id not in req_ids:
                        add(
                            "error",
                            "task.unknown_requirement",
                            f"Task references unknown requirement {req_id}",
                            task_id,
                        )
                for decision_id in task.get("decision_ids", []):
                    if decision_id not in decision_ids:
                        add(
                            "error",
                            "task.unknown_decision",
                            f"Task references unknown decision {decision_id}",
                            task_id,
                        )
                if (
                    project.get("mode") in {"deep", "program"}
                    and task.get("kind") == "implementation"
                    and not task.get("file_scope")
                ):
                    add(
                        "warning",
                        "task.scope_missing",
                        "Implementation task has no file scope and will serialize all work",
                        task_id,
                    )
                if task.get("status") == "skipped" and not (
                    task.get("summary") or task.get("notes")
                ):
                    add(
                        "warning",
                        "task.skip_reason_missing",
                        "Skipped task has no recorded rationale",
                        task_id,
                    )
                policy = config.get("require_evidence", "risk_based")
                if policy == "always":
                    require_evidence = True
                elif policy == "never":
                    require_evidence = False
                else:
                    require_evidence = task.get("risk") in {"high", "critical"} or project.get(
                        "mode"
                    ) in {"deep", "program"}
                if (
                    task.get("status") == "done"
                    and require_evidence
                    and not successful_evidence_by_task.get(task_id)
                ):
                    message = "Completed task has no successful evidence"
                    if evidence_by_task.get(task_id):
                        message += " (recorded evidence is failed or unclassified)"
                    add(
                        "error" if task.get("risk") in {"high", "critical"} else "warning",
                        "task.evidence_missing",
                        message,
                        task_id,
                    )
                if task.get("status") == "blocked" and not task.get("blocked_reason"):
                    add(
                        "warning",
                        "task.block_reason_missing",
                        "Blocked task has no reason",
                        task_id,
                    )

            for criterion_id, criterion_text in active_criteria.items():
                if criterion_success_task_ids.get(criterion_id):
                    continue
                terminal_plan = bool(tasks) and all(
                    task.get("status") in {"done", "skipped"} for task in tasks
                )
                add(
                    "error"
                    if terminal_plan or milestone.get("status") in {"done", "verified"}
                    else "warning",
                    "milestone.exit_criterion_proof_missing",
                    "Active exit criterion has no successful evidence linked through a non-skipped task",
                    criterion_id,
                    milestone_id=milestone_id,
                    criterion=criterion_text,
                )

            linked_requirement_ids = set(map(str, milestone.get("requirement_ids", [])))
            linked_requirement_ids.update(
                str(requirement_id)
                for task in tasks
                for requirement_id in task.get("requirement_ids", [])
            )
            for requirement in requirement_rows:
                requirement_id = str(requirement.get("id") or "")
                if (
                    requirement_id not in linked_requirement_ids
                    or requirement.get("status", "active") != "active"
                    or requirement.get("priority", "must") != "must"
                    or requirement_id in successful_evidence_by_requirement
                ):
                    continue
                add(
                    "error"
                    if milestone.get("status") in {"done", "verified"}
                    or (
                        plan.get("tasks")
                        and all(task.get("status") in {"done", "skipped"} for task in tasks)
                    )
                    else "warning",
                    "requirement.proof_missing",
                    "Active must-have requirement has no successful evidence linked to it",
                    requirement_id,
                    milestone_id=milestone_id,
                )

        if milestone_rows:
            for req in requirement_rows:
                req_id = str(req.get("id") or "")
                if (
                    req_id
                    and req.get("status", "active") == "active"
                    and req.get("priority", "must") == "must"
                    and req_id not in linked_requirements
                ):
                    add(
                        "warning",
                        "requirement.unplanned",
                        "Active must-have requirement is not linked to a milestone",
                        req_id,
                    )
        for task_id in state.get("current_tasks", []):
            task = all_tasks.get(task_id)
            if not task:
                add(
                    "error",
                    "state.unknown_current_task",
                    "State references an unknown current task",
                    task_id,
                )
            elif task.get("status") != "in_progress":
                add(
                    "warning",
                    "state.current_task_drift",
                    "State current task is not marked in progress",
                    task_id,
                )

        status_counts = Counter(item.get("status", "planned") for item in milestone_rows)
        task_status_counts = Counter(task.get("status", "pending") for task in all_tasks.values())
        for req in requirement_rows:
            req_id = str(req.get("id") or "")
            if req_id and req.get("status", "active") == "active":
                linked_tasks = [
                    task for task in all_tasks.values() if req_id in task.get("requirement_ids", [])
                ]
                if not linked_tasks:
                    add(
                        "warning", "requirement.uncovered", "Requirement has no linked task", req_id
                    )

        max_chars = int(config.get("max_artifact_chars") or 50000)
        for path in sdd.rglob("*"):
            if (
                path.is_file()
                and path.suffix in {".md", ".json", ".jsonl"}
                and path.stat().st_size > max_chars
            ):
                add(
                    "warning",
                    "artifact.large",
                    f"Artifact exceeds {max_chars} bytes; split or summarize it",
                    str(path.relative_to(project_root)),
                )
        weights = {"error": 15, "warning": 5, "info": 1}
        score = max(0, 100 - sum(weights.get(item["severity"], 0) for item in findings))
        severity_counts = Counter(item["severity"] for item in findings)
        result = {
            "ok": not severity_counts.get("error"),
            "score": score,
            "counts": dict(severity_counts),
            "findings": findings if options.get("detail", "normal") != "compact" else findings[:10],
            "milestone_status_counts": dict(status_counts),
            "task_status_counts": dict(task_status_counts),
        }
        if payload.get("record", True):
            self._event(sdd, "validation_completed", score=score, counts=dict(severity_counts))
        return result

    def status(
        self, root: str | None, _: dict[str, Any], options: dict[str, Any]
    ) -> dict[str, Any]:
        project_root = self._root(root)
        sdd = self._require(project_root)
        project = self._read_project(sdd)
        state = self._read_required_json(sdd, "state.json")
        roadmap = self._read_required_json(sdd, "roadmap.json")
        milestone_rows = self._require_object_list(roadmap, "milestones", "milestones")
        counts: Counter[str] = Counter()
        active = None
        active_plan = {"tasks": []}
        for milestone in milestone_rows:
            plan = self._read_required_json_path(
                sdd / "milestones" / str(milestone.get("id")) / "plan.json"
            )
            tasks = self._require_object_list(plan, "tasks", "plan tasks")
            counts.update(task.get("status", "pending") for task in tasks)
            if milestone.get("id") == state.get("active_milestone"):
                active = milestone
                active_plan = plan
        validation = self.validate(str(project_root), {"record": False}, {"detail": "normal"})
        next_wave = None
        if active:
            next_wave = self.next(
                str(project_root), active.get("id"), {}, {"limit": options.get("limit", 4)}
            )
        active_task_ids = {str(task.get("id")) for task in active_plan.get("tasks", [])}
        active_requirement_ids = set(map(str, (active or {}).get("requirement_ids", [])))
        active_requirement_ids.update(
            str(requirement_id)
            for task in active_plan.get("tasks", [])
            for requirement_id in task.get("requirement_ids", [])
        )
        active_targets = {None, (active or {}).get("id"), *active_task_ids, *active_requirement_ids}
        active_findings = [
            item
            for item in validation.get("findings", [])
            if item.get("severity") == "error"
            and (
                item.get("target") in active_targets
                or item.get("code") in {"project.goal_missing", "project.mode_invalid"}
            )
            and (
                item.get("code") != "requirement.proof_missing"
                or item.get("milestone_id") == (active or {}).get("id")
            )
        ]
        active_error_count = len(active_findings)
        status_result: dict[str, Any] = {
            "ok": True,
            "root": str(project_root),
            "project": {
                key: project.get(key) for key in ("name", "goal", "summary", "mode", "status")
            },
            "state": state,
            "milestone_count": len(milestone_rows),
            "task_counts": dict(counts),
            "active_milestone": active,
            "active_task_count": len(active_plan.get("tasks", [])),
            "next": next_wave,
            "health": {"score": validation.get("score"), "counts": validation.get("counts")},
            "active_validation": {
                "error_count": active_error_count,
                "findings": [
                    {
                        key: item[key]
                        for key in ("severity", "code", "message", "target")
                        if item.get(key) is not None
                    }
                    for item in active_findings[:10]
                ],
                "findings_truncated": active_error_count > 10,
            },
        }
        next_reason = (next_wave or {}).get("reason")
        if active_error_count:
            status_result["action"] = {
                "kind": "resolve_validation",
                "reason": "Active milestone has blocking findings; resolve them before advancing.",
            }
        elif active and next_wave and next_wave.get("wave"):
            status_result["action"] = {
                "kind": "execute_task",
                "reason": f"Start the next dependency-safe task wave for {active.get('id')}.",
            }
        elif next_reason == "milestone tasks are terminal; verify and finalize the milestone":
            status_result["action"] = {
                "kind": "verify_milestone",
                "reason": next_reason,
            }
        elif next_reason == "no dependency-ready task; blocked tasks require recovery":
            status_result["action"] = {
                "kind": "resolve_blocker",
                "reason": next_reason,
            }
        elif next_reason == "ready tasks conflict with or must wait for active work":
            status_result["action"] = {
                "kind": "reconcile_active_work",
                "reason": next_reason,
            }
        elif next_reason == "parallel disabled until interfaces are stable":
            status_result["action"] = {
                "kind": "stabilize_interfaces",
                "reason": next_reason,
            }
        elif active is None:
            status_result["action"] = {
                "kind": "plan_milestone",
                "reason": "No active milestone is selected; choose or create the next outcome to execute.",
            }
        elif not active_plan.get("tasks"):
            status_result["action"] = {
                "kind": "plan_tasks",
                "reason": f"Active milestone {active.get('id')} has no executable task plan.",
            }
        else:
            status_result["action"] = {
                "kind": "inspect_plan",
                "reason": next_reason or "No safe task wave is available; inspect the plan.",
            }
        status_result["action"]["validation_error_count"] = active_error_count
        if options.get("detail", "normal") != "compact":
            try:
                requested_limit = int(options.get("active_task_limit") or 12)
            except (TypeError, ValueError) as exc:
                raise ValueError("active_task_limit must be an integer") from exc
            limit = max(1, min(requested_limit, 50))
            status_result["active_tasks"] = [
                _compact(task) for task in active_plan.get("tasks", [])[:limit]
            ]
            status_result["active_tasks_truncated"] = len(active_plan.get("tasks", [])) > limit
        return status_result

    def search(
        self, root: str | None, target: str | None, payload: dict[str, Any], options: dict[str, Any]
    ) -> dict[str, Any]:
        project_root = self._root(root)
        sdd = self._require(project_root)
        query = str(target or payload.get("query") or "").strip().lower()
        if not query:
            raise ValueError("search requires target or payload.query")
        limit = max(1, min(int(options.get("limit") or 20), 100))
        results: list[dict[str, Any]] = []
        for path in sorted(sdd.rglob("*")):
            if not path.is_file() or path.suffix not in {".md", ".json", ".jsonl"}:
                continue
            try:
                content = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                continue
            lower = content.lower()
            start = lower.find(query)
            if start < 0:
                continue
            excerpt = content[
                max(0, start - 180) : min(len(content), start + len(query) + 420)
            ].replace("\n", " ")
            results.append({"path": str(path.relative_to(project_root)), "excerpt": excerpt})
            if len(results) >= limit:
                break
        return {"ok": True, "query": query, "results": results}

    def snapshot(self, root: str | None) -> dict[str, Any]:
        project_root = self._root(root)
        status = self.status(str(project_root), {}, {"limit": 6})
        sdd = self._require(project_root)
        roadmap = self._read_required_json(sdd, "roadmap.json")
        requirements = self._read_required_json(sdd, "requirements.json")
        requirement_rows = self._require_object_list(requirements, "requirements", "requirements")
        milestones = self._require_object_list(roadmap, "milestones", "milestones")
        return {
            **status,
            "roadmap": milestones,
            "requirements": requirement_rows,
        }

    def execute(
        self,
        operation: str,
        *,
        root: str | None = None,
        target: str | None = None,
        payload: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = payload or {}
        options = options or {}
        operation = str(operation or "").strip().lower()
        dispatch = {
            "init": lambda: self.init(root, payload, options),
            "status": lambda: self.status(root, payload, options),
            "configure": lambda: self.configure(root, payload, options),
            "upsert_spec": lambda: self.upsert_spec(root, payload, options),
            "create_milestone": lambda: self.create_milestone(root, payload, options),
            "update_milestone": lambda: self.update_milestone(root, target, payload, options),
            "set_plan": lambda: self.set_plan(root, payload, options),
            "update_task": lambda: self.update_task(root, target, payload, options),
            "next": lambda: self.next(root, target, payload, options),
            "transition": lambda: self.transition(root, target, payload, options),
            "record_decision": lambda: self.record_decision(root, target, payload, options),
            "record_evidence": lambda: self.record_evidence(root, target, payload, options),
            "finalize_milestone": lambda: self.finalize_milestone(root, target, payload, options),
            "context_pack": lambda: self.context_pack(root, target, payload, options),
            "context_checkpoint": lambda: self.context_checkpoint(root, target, payload, options),
            "context_delta": lambda: self.context_delta(root, target, payload, options),
            "validate": lambda: self.validate(root, payload, options),
            "search": lambda: self.search(root, target, payload, options),
            "register_source": lambda: {
                "ok": True,
                "source": self.registry.register(
                    payload.get("path") or root or "", payload.get("name")
                ),
            },
            "list_sources": lambda: {"ok": True, "sources": self.registry.list()},
            "remove_source": lambda: {
                "ok": self.registry.remove(target or payload.get("id") or payload.get("path") or "")
            },
        }
        if operation not in dispatch:
            raise ValueError(f"Unknown SDD operation: {operation}")
        return dispatch[operation]()


def tool_response(service: SDDService, params: dict[str, Any]) -> str:
    try:
        result = service.execute(
            params.get("operation", ""),
            root=params.get("root"),
            target=params.get("target"),
            payload=params.get("payload") or {},
            options=params.get("options") or {},
        )
        return json.dumps(result, ensure_ascii=False, separators=(",", ":"))
    except Exception as exc:  # Hermes tool handlers should return structured errors.
        return json.dumps(
            {
                "ok": False,
                "error": type(exc).__name__,
                "message": str(exc),
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
