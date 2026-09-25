"""Generate concise human-readable views from authoritative JSON state."""

from __future__ import annotations

from pathlib import Path
from .storage import atomic_write_text, read_json, read_jsonl


def _bullets(values: list[str], empty: str = "None recorded.") -> str:
    return "\n".join(f"- {value}" for value in values) if values else empty


def render_all(root: Path) -> None:
    sdd = root / ".sdd"
    project = read_json(sdd / "project.json", {}) or {}
    requirements = read_json(sdd / "requirements.json", {"requirements": []}) or {
        "requirements": []
    }
    roadmap = read_json(sdd / "roadmap.json", {"milestones": []}) or {"milestones": []}
    state = read_json(sdd / "state.json", {}) or {}

    project_text = f"""# Project\n\n> Generated from `.sdd/project.json`; edit through the SDD tool or UI.\n\n## Goal\n\n{project.get("goal") or "Not recorded."}\n\n## Summary\n\n{project.get("summary") or "Not recorded."}\n\n## Mode\n\n`{project.get("mode", "standard")}`\n\n## Success criteria\n\n{_bullets(project.get("success_criteria", []))}\n\n## Constraints\n\n{_bullets(project.get("constraints", []))}\n\n## Non-goals\n\n{_bullets(project.get("non_goals", []))}\n\n## Engineering principles\n\n{_bullets(project.get("principles", []))}\n"""
    atomic_write_text(sdd / "PROJECT.md", project_text)

    req_lines = ["# Requirements", "", "> Generated from `.sdd/requirements.json`.", ""]
    for req in requirements.get("requirements", []):
        source = req.get("source") or "unspecified"
        req_lines.extend(
            [
                f"## {req.get('id')} — {req.get('title', 'Untitled')}",
                "",
                req.get("statement", ""),
                "",
                f"- Priority: `{req.get('priority', 'must')}`",
                f"- Status: `{req.get('status', 'active')}`",
                f"- Source: `{source}`",
                "- Acceptance:",
                *[f"  - {item}" for item in req.get("acceptance", [])],
                "",
            ]
        )
    atomic_write_text(sdd / "REQUIREMENTS.md", "\n".join(req_lines).rstrip() + "\n")

    roadmap_lines = ["# Roadmap", "", "> Generated from `.sdd/roadmap.json`.", ""]
    status_counts = {}
    for item in roadmap.get("milestones", []):
        status = item.get("status", "planned")
        status_counts[status] = status_counts.get(status, 0) + 1
    roadmap_lines.extend(
        [
            "## Milestone counts",
            "",
            ", ".join(f"{key}: {value}" for key, value in sorted(status_counts.items())),
            "",
        ]
    )
    for milestone in roadmap.get("milestones", []):
        reqs = ", ".join(milestone.get("requirement_ids", [])) or "none"
        decision_links = ", ".join(milestone.get("decision_ids", [])) or "none"
        criterion_records = milestone.get("exit_criteria_records", [])
        criterion_by_text = {
            item.get("text"): item.get("id")
            for item in criterion_records
            if isinstance(item, dict) and item.get("status") == "active"
        }
        roadmap_lines.extend(
            [
                f"## {milestone.get('id')} — {milestone.get('title', 'Untitled')}",
                "",
                milestone.get("objective", ""),
                "",
                f"- Status: `{milestone.get('status', 'planned')}`",
                f"- Risk: `{milestone.get('risk', 'medium')}`",
                f"- Requirements: {reqs}",
                f"- Decisions: {decision_links}",
                "- Exit criteria:",
                *[
                    f"  - `{criterion_by_text.get(item, 'unmapped')}` — {item}"
                    for item in milestone.get("exit_criteria", [])
                ],
                "",
            ]
        )
    atomic_write_text(sdd / "ROADMAP.md", "\n".join(roadmap_lines).rstrip() + "\n")

    milestones_dir = sdd / "milestones"
    for milestone in roadmap.get("milestones", []):
        milestone_id = str(milestone.get("id") or "")
        if not milestone_id:
            continue
        milestone_dir = milestones_dir / milestone_id
        plan = read_json(milestone_dir / "plan.json", {"tasks": []}) or {"tasks": []}
        evidence = read_jsonl(milestone_dir / "evidence.jsonl")
        evidence_by_task = {}
        for item in evidence:
            evidence_by_task.setdefault(item.get("task_id"), []).append(item)
        plan_lines = [
            f"# {milestone_id} plan",
            "",
            "> Generated from `.sdd/milestones/<id>/plan.json`; edit through the SDD tool or UI.",
            "",
            f"- Revision: `{plan.get('revision', 0)}`",
            f"- Status: `{milestone.get('status', 'planned')}`",
            "",
        ]
        for task in plan.get("tasks", []):
            task_id = task.get("id", "unknown")
            task_evidence = evidence_by_task.get(task_id, [])
            evidence_state = (
                "successful evidence recorded"
                if any(item.get("passed") is True for item in task_evidence)
                else "evidence missing or unclassified"
                if task.get("status") == "done"
                else "not completed"
            )
            requirement_links = ", ".join(map(str, task.get("requirement_ids", []))) or "none"
            exit_criterion_links = ", ".join(map(str, task.get("exit_criteria_ids", []))) or "none"
            plan_lines.extend(
                [
                    f"## {task_id} — {task.get('title', 'Untitled')}",
                    "",
                    task.get("objective", "") or "No objective recorded.",
                    "",
                    f"- Status: `{task.get('status', 'pending')}`",
                    f"- Risk: `{task.get('risk', 'medium')}`",
                    f"- Depends on: {', '.join(map(str, task.get('depends_on', []))) or 'none'}",
                    f"- File scope: {', '.join(map(str, task.get('file_scope', []))) or 'global/unknown'}",
                    f"- Evidence: {evidence_state}",
                    f"- Requirements: {requirement_links}",
                    f"- Exit criteria: {exit_criterion_links}",
                    "- Acceptance:",
                    *[f"  - {item}" for item in task.get("acceptance", [])],
                    "",
                ]
            )
        atomic_write_text(milestone_dir / "PLAN.md", "\n".join(plan_lines).rstrip() + "\n")

    task_counts = {}
    for milestone in roadmap.get("milestones", []):
        plan = read_json(sdd / "milestones" / str(milestone.get("id")) / "plan.json", {}) or {}
        for task in plan.get("tasks", []):
            status = task.get("status", "pending")
            task_counts[status] = task_counts.get(status, 0) + 1
    state_text = f"""# Current state\n\n> Generated from `.sdd/state.json`. Keep this file small; details live in milestone plans.\n\n- Project status: `{state.get("status", "active")}`\n- Active milestone: `{state.get("active_milestone") or "none"}`\n- Current tasks: {", ".join(state.get("current_tasks", [])) or "none"}\n- Last checkpoint: `{state.get("last_checkpoint") or "none"}`\n- Updated: `{state.get("updated_at") or "unknown"}`\n\n## Task counts\n\n{", ".join(f"{key}: {value}" for key, value in sorted(task_counts.items())) or "none"}\n"""
    atomic_write_text(sdd / "STATE.md", state_text)


def render_decision_index(root: Path) -> None:
    decisions_dir = root / ".sdd" / "decisions"
    lines = ["# Architectural decisions", ""]
    if decisions_dir.exists():
        for path in sorted(decisions_dir.glob("*.json")):
            decision = read_json(path, {}) or {}
            lines.extend(
                [
                    f"## {decision.get('id')} — {decision.get('title', 'Untitled')}",
                    "",
                    f"- Status: `{decision.get('status', 'accepted')}`",
                    f"- Decision: {decision.get('decision', '')}",
                    "",
                ]
            )
    atomic_write_text(root / ".sdd" / "DECISIONS.md", "\n".join(lines).rstrip() + "\n")
