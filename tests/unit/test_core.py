from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from hermes_sdd.context_pack import checkpoint_delta
from hermes_sdd.core import SDDService, _path_overlap, complexity_mode, tool_response
from hermes_sdd.registry import SourceRegistry
from hermes_sdd.storage import project_lock


class CoreTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.service = SDDService(SourceRegistry(self.base / "registry.db"))

    def tearDown(self) -> None:
        self.temp.cleanup()

    def root(self, *, source: bool = False) -> Path:
        root = self.base / "repo"
        root.mkdir(exist_ok=True)
        if source:
            (root / "src").mkdir(exist_ok=True)
        return root

    def initialize(self, root: Path, *, mode: str = "program") -> None:
        result = self.service.execute(
            "init",
            root=str(root),
            payload={
                "name": "Atlas",
                "goal": "Deliver an end-to-end data platform",
                "mode": mode,
                "success_criteria": ["A user can ingest and query data"],
                "constraints": ["Local-first development"],
            },
        )
        self.assertTrue(result["ok"] and result["created"])

    def test_complexity_mode_and_path_overlap(self) -> None:
        zeros = {
            key: 0
            for key in ("novelty", "ambiguity", "surface_area", "risk", "duration", "coordination")
        }
        threes = {key: 3 for key in zeros}
        self.assertEqual(complexity_mode(zeros), ("quick", 0))
        self.assertEqual(complexity_mode(threes), ("program", 18))
        self.assertTrue(_path_overlap("src/api/**", "src/api/routes.py"))
        self.assertFalse(_path_overlap("src/api/**", "src/ui/view.ts"))

    def test_project_lifecycle(self) -> None:
        root = self.root()
        self.initialize(root)
        spec = self.service.execute(
            "upsert_spec",
            root=str(root),
            payload={
                "architecture": "# Architecture\n\nA modular monolith owns ingestion and query contracts. Interfaces are versioned.",
                "requirements": [
                    {
                        "id": "REQ-001",
                        "title": "Ingest records",
                        "statement": "The system ingests validated records.",
                        "acceptance": [
                            "Invalid records are rejected",
                            "Valid records are queryable",
                        ],
                    }
                ],
            },
        )
        self.assertEqual(spec["requirements_updated"], ["REQ-001"])
        milestone = self.service.execute(
            "create_milestone",
            root=str(root),
            payload={
                "id": "M001",
                "title": "Executable vertical slice",
                "objective": "Ingest and query one record end to end",
                "requirement_ids": ["REQ-001"],
                "exit_criteria": ["Integration test passes"],
                "interfaces_stable": True,
            },
        )
        self.assertEqual(milestone["milestone"]["id"], "M001")
        plan = self.service.execute(
            "set_plan",
            root=str(root),
            payload={
                "milestone_id": "M001",
                "tasks": [
                    {
                        "id": "M001-T001",
                        "title": "Define contract",
                        "objective": "Create validated record contract",
                        "risk": "high",
                        "acceptance": ["Contract rejects invalid data"],
                        "file_scope": ["src/contracts/**", "tests/contracts/**"],
                        "requirement_ids": ["REQ-001"],
                    },
                    {
                        "id": "M001-T002",
                        "title": "Build query path",
                        "objective": "Query persisted records",
                        "depends_on": ["M001-T001"],
                        "acceptance": ["Query returns the ingested record"],
                        "file_scope": ["src/query/**", "tests/query/**"],
                        "requirement_ids": ["REQ-001"],
                    },
                ],
            },
        )
        self.assertEqual(plan["task_count"], 2)
        self.assertEqual([task["id"] for task in plan["next"]["wave"]], ["M001-T001"])
        checkpoint = self.service.execute(
            "context_checkpoint", root=str(root), payload={"task_id": "M001-T001"}
        )["checkpoint"]
        context = self.service.execute(
            "context_pack",
            root=str(root),
            target="M001-T001",
            payload={"checkpoint_id": checkpoint["id"]},
            options={"budget_tokens": 4000},
        )
        self.assertLessEqual(context["estimated_tokens"], 4000)
        self.assertIn("Selected task", context["sections"])
        self.service.execute(
            "transition", root=str(root), target="M001-T001", payload={"status": "in_progress"}
        )
        done = self.service.execute(
            "transition",
            root=str(root),
            target="M001-T001",
            payload={
                "status": "done",
                "summary": "Contract implemented",
                "evidence": {
                    "type": "test",
                    "command": "python -m unittest",
                    "result": "passed",
                    "passed": True,
                },
            },
        )
        self.assertTrue(done["task"]["evidence_ids"])
        self.assertEqual(self.service.execute("next", root=str(root))["wave"][0]["id"], "M001-T002")
        self.service.execute(
            "transition", root=str(root), target="M001-T002", payload={"status": "in_progress"}
        )
        self.service.execute(
            "transition",
            root=str(root),
            target="M001-T002",
            payload={
                "status": "done",
                "summary": "Query implemented",
                "evidence": {
                    "type": "integration_test",
                    "command": "tests/query",
                    "result": "passed",
                    "passed": True,
                },
            },
        )
        self.assertTrue(
            self.service.execute("validate", root=str(root), payload={"record": False})["ok"]
        )
        finalized = self.service.execute(
            "finalize_milestone",
            root=str(root),
            target="M001",
            payload={"summary": "Vertical slice delivered and integration-tested."},
        )
        self.assertEqual(finalized["status"], "verified")
        self.assertEqual(finalized["project_status"], "complete")
        self.assertTrue((root / ".sdd" / "PROJECT.md").exists())

    def test_conflict_safe_wave(self) -> None:
        root = self.root()
        self.initialize(root, mode="standard")
        self.service.execute(
            "create_milestone",
            root=str(root),
            payload={"id": "M001", "title": "Parallel", "interfaces_stable": True},
        )
        self.service.execute(
            "set_plan",
            root=str(root),
            payload={
                "milestone_id": "M001",
                "tasks": [
                    {
                        "id": "M001-T001",
                        "title": "A",
                        "objective": "A",
                        "acceptance": ["A"],
                        "file_scope": ["src/a/**"],
                    },
                    {
                        "id": "M001-T002",
                        "title": "B",
                        "objective": "B",
                        "acceptance": ["B"],
                        "file_scope": ["src/b/**"],
                    },
                    {
                        "id": "M001-T003",
                        "title": "A2",
                        "objective": "A2",
                        "acceptance": ["A2"],
                        "file_scope": ["src/a/file.py"],
                    },
                ],
            },
        )
        wave = self.service.execute("next", root=str(root), options={"limit": 4})["wave"]
        self.assertEqual([task["id"] for task in wave], ["M001-T001", "M001-T002"])

    def test_checkpoint_delta_and_tool_errors(self) -> None:
        root = self.root()
        self.initialize(root, mode="quick")
        checkpoint = self.service.execute("context_checkpoint", root=str(root))["checkpoint"]
        self.service.execute("upsert_spec", root=str(root), payload={"summary": "Changed"})
        self.assertIn(".sdd/project.json", checkpoint_delta(root, checkpoint["id"])["changed"])
        response = json.loads(
            tool_response(self.service, {"operation": "unknown", "root": str(root)})
        )
        self.assertFalse(response["ok"])

    def test_invalid_dag_rejected(self) -> None:
        root = self.root()
        self.initialize(root)
        self.service.execute(
            "create_milestone", root=str(root), payload={"id": "M001", "title": "Cycle"}
        )
        with self.assertRaisesRegex(ValueError, "cycle"):
            self.service.execute(
                "set_plan",
                root=str(root),
                payload={
                    "milestone_id": "M001",
                    "tasks": [
                        {"id": "M001-T001", "title": "A", "depends_on": ["M001-T002"]},
                        {"id": "M001-T002", "title": "B", "depends_on": ["M001-T001"]},
                    ],
                },
            )

    def test_critical_task_isolation_and_custom_ids(self) -> None:
        root = self.root()
        self.initialize(root, mode="deep")
        self.service.execute(
            "create_milestone",
            root=str(root),
            payload={"id": "M001", "title": "Contracts", "interfaces_stable": False},
        )
        self.service.execute(
            "set_plan",
            root=str(root),
            payload={
                "milestone_id": "M001",
                "tasks": [
                    {
                        "id": "contract-core",
                        "title": "Contract",
                        "objective": "Contract",
                        "risk": "critical",
                        "acceptance": ["Valid"],
                        "file_scope": ["contracts/**"],
                    },
                    {
                        "id": "docs-work",
                        "title": "Docs",
                        "objective": "Docs",
                        "acceptance": ["Written"],
                        "file_scope": ["docs/**"],
                    },
                ],
            },
        )
        self.assertEqual(
            [
                task["id"]
                for task in self.service.execute("next", root=str(root), options={"limit": 4})[
                    "wave"
                ]
            ],
            ["contract-core"],
        )
        self.service.execute(
            "update_milestone", root=str(root), target="M001", payload={"interfaces_stable": True}
        )
        self.assertEqual(
            [
                task["id"]
                for task in self.service.execute("next", root=str(root), options={"limit": 4})[
                    "wave"
                ]
            ],
            ["contract-core"],
        )
        self.assertEqual(
            self.service.execute("context_pack", root=str(root), target="contract-core")[
                "milestone_id"
            ],
            "M001",
        )
        self.service.execute(
            "transition", root=str(root), target="contract-core", payload={"status": "in_progress"}
        )
        result = self.service.execute(
            "transition",
            root=str(root),
            target="contract-core",
            payload={"status": "done", "evidence": {"type": "test", "result": "passed"}},
        )
        plan = json.loads((root / ".sdd" / "milestones" / "M001" / "plan.json").read_text())
        saved = next(task for task in plan["tasks"] if task["id"] == "contract-core")
        self.assertEqual(saved["evidence_ids"], [result["evidence"]["id"]])

    def test_force_init_backs_up_existing_state(self) -> None:
        root = self.root()
        self.initialize(root, mode="quick")
        (root / ".sdd" / "custom.txt").write_text("keep", encoding="utf-8")
        result = self.service.execute(
            "init",
            root=str(root),
            payload={"goal": "Replacement", "mode": "quick"},
            options={"force": True},
        )
        backup = Path(result["backup"])
        self.assertTrue(backup.exists())
        self.assertEqual((backup / "custom.txt").read_text(), "keep")
        self.assertEqual(
            json.loads((root / ".sdd" / "project.json").read_text())["goal"], "Replacement"
        )

    def test_force_init_validates_before_backup(self) -> None:
        root = self.root()
        self.initialize(root, mode="quick")
        original = (root / ".sdd" / "project.json").read_text(encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Invalid mode"):
            self.service.execute(
                "init",
                root=str(root),
                payload={"goal": "Invalid replacement", "mode": "not-a-mode"},
                options={"force": True},
            )
        self.assertEqual((root / ".sdd" / "project.json").read_text(encoding="utf-8"), original)
        self.assertEqual(list(root.glob(".sdd.backup-*")), [])

    def test_init_rolls_back_new_state_when_render_fails(self) -> None:
        root = self.root()
        with patch("hermes_sdd.core.render_all", side_effect=OSError("render failed")):
            with self.assertRaisesRegex(OSError, "render failed"):
                self.service.execute(
                    "init", root=str(root), payload={"goal": "Render failure", "mode": "quick"}
                )
        self.assertFalse((root / ".sdd").exists())

    def test_force_init_restores_old_state_when_render_fails(self) -> None:
        root = self.root()
        self.initialize(root, mode="quick")
        original = (root / ".sdd" / "project.json").read_text(encoding="utf-8")
        with patch("hermes_sdd.core.render_all", side_effect=OSError("render failed")):
            with self.assertRaisesRegex(OSError, "render failed"):
                self.service.execute(
                    "init",
                    root=str(root),
                    payload={"goal": "Replacement", "mode": "quick"},
                    options={"force": True},
                )
        self.assertEqual((root / ".sdd" / "project.json").read_text(encoding="utf-8"), original)
        self.assertEqual(list(root.glob(".sdd.backup-*")), [])

    def test_wildcard_checkpoint_tracks_source_changes(self) -> None:
        root = self.root()
        source = root / "src" / "api" / "routes.py"
        source.parent.mkdir(parents=True)
        source.write_text("VALUE = 1\n", encoding="utf-8")
        self.initialize(root, mode="standard")
        self.service.execute(
            "create_milestone",
            root=str(root),
            payload={"id": "M001", "title": "API", "interfaces_stable": True},
        )
        self.service.execute(
            "set_plan",
            root=str(root),
            payload={
                "milestone_id": "M001",
                "tasks": [
                    {
                        "id": "api-task",
                        "title": "API",
                        "objective": "Change API",
                        "acceptance": ["Updated"],
                        "file_scope": ["src/api/**/*.py"],
                    }
                ],
            },
        )
        checkpoint = self.service.execute(
            "context_checkpoint", root=str(root), payload={"task_id": "api-task"}
        )["checkpoint"]
        immediate = self.service.execute(
            "context_delta",
            root=str(root),
            target=checkpoint["id"],
            payload={"task_id": "api-task"},
        )
        self.assertEqual(
            (immediate["added"], immediate["changed"], immediate["removed"]), ([], [], [])
        )
        source.write_text("VALUE = 2\n", encoding="utf-8")
        delta = self.service.execute(
            "context_delta",
            root=str(root),
            target=checkpoint["id"],
            payload={"task_id": "api-task"},
        )
        self.assertIn("src/api/routes.py", delta["changed"])

    def test_context_checkpoint_excludes_default_secret_patterns(self) -> None:
        root = self.root(source=True)
        self.initialize(root, mode="standard")
        (root / ".env").write_text("TOKEN=do-not-hash\n")
        (root / "src" / "example.py").write_text("print('ok')\n")
        self.service.execute(
            "create_milestone",
            root=str(root),
            payload={"id": "M001", "title": "Context", "interfaces_stable": True},
        )
        self.service.execute(
            "set_plan",
            root=str(root),
            payload={
                "milestone_id": "M001",
                "tasks": [{"id": "work", "title": "Work", "file_scope": ["**/*"]}],
            },
        )
        snapshot = self.service.execute(
            "context_checkpoint", root=str(root), payload={"task_id": "work"}
        )["checkpoint"]
        self.assertNotIn(".env", snapshot["files"])

    def test_context_checkpoint_rejects_symlinked_authoritative_file(self) -> None:
        root = self.root()
        self.initialize(root, mode="quick")
        outside = self.base / "outside-architecture.md"
        architecture = root / ".sdd" / "architecture.md"
        architecture.unlink()
        architecture.symlink_to(outside)
        with self.assertRaisesRegex(ValueError, "symlink"):
            self.service.execute("context_checkpoint", root=str(root))

    def test_validation_reports_status_counts_and_uncovered_requirements(self) -> None:
        root = self.root()
        self.initialize(root, mode="quick")
        self.service.execute(
            "upsert_spec",
            root=str(root),
            payload={
                "requirements": [
                    {
                        "id": "REQ-001",
                        "title": "Uncovered",
                        "statement": "Must be addressed",
                        "acceptance": ["It works"],
                    }
                ]
            },
        )
        result = self.service.execute("validate", root=str(root), payload={"record": False})
        self.assertEqual(result["milestone_status_counts"], {})
        self.assertTrue(any(item["code"] == "requirement.uncovered" for item in result["findings"]))

    def test_failed_evidence_blocks_program_milestone(self) -> None:
        root = self.root()
        self.initialize(root, mode="program")
        self.service.execute(
            "upsert_spec",
            root=str(root),
            payload={
                "architecture": "# Architecture\n\nA stable modular boundary governs this implementation and its contracts."
            },
        )
        self.service.execute(
            "create_milestone",
            root=str(root),
            payload={"id": "M001", "title": "Verified", "exit_criteria": ["Tests pass"]},
        )
        self.service.execute(
            "set_plan",
            root=str(root),
            payload={
                "milestone_id": "M001",
                "tasks": [
                    {
                        "id": "work",
                        "title": "Work",
                        "objective": "Implement",
                        "acceptance": ["Works"],
                        "file_scope": ["src/**"],
                    }
                ],
            },
        )
        self.service.execute(
            "transition", root=str(root), target="work", payload={"status": "in_progress"}
        )
        self.service.execute(
            "transition",
            root=str(root),
            target="work",
            payload={
                "status": "done",
                "evidence": {"type": "manual", "result": "verification required", "passed": False},
            },
        )
        with self.assertRaisesRegex(ValueError, "evidence_missing"):
            self.service.execute("finalize_milestone", root=str(root), target="M001", payload={})
        self.service.execute(
            "record_evidence",
            root=str(root),
            target="work",
            payload={"type": "test", "command": "tests", "result": "passed", "passed": True},
        )
        self.assertEqual(
            self.service.execute("finalize_milestone", root=str(root), target="M001", payload={})[
                "status"
            ],
            "verified",
        )

    def test_future_milestone_error_does_not_block_current(self) -> None:
        root = self.root()
        self.initialize(root, mode="standard")
        self.service.execute(
            "create_milestone",
            root=str(root),
            payload={
                "id": "M001",
                "title": "Current",
                "exit_criteria": ["Done"],
                "interfaces_stable": True,
            },
        )
        self.service.execute(
            "set_plan",
            root=str(root),
            payload={
                "milestone_id": "M001",
                "tasks": [
                    {
                        "id": "current-work",
                        "title": "Current",
                        "objective": "Deliver",
                        "acceptance": ["Done"],
                        "file_scope": ["src/current/**"],
                    }
                ],
            },
        )
        self.service.execute(
            "transition", root=str(root), target="current-work", payload={"status": "in_progress"}
        )
        self.service.execute(
            "transition",
            root=str(root),
            target="current-work",
            payload={"status": "done", "summary": "Delivered"},
        )
        self.service.execute(
            "create_milestone",
            root=str(root),
            payload={
                "id": "M002",
                "title": "Future",
                "requirement_ids": ["REQ-MISSING"],
                "exit_criteria": ["Later"],
            },
            options={"activate": False},
        )
        validation = self.service.execute("validate", root=str(root), payload={"record": False})
        self.assertTrue(
            any(
                item["target"] == "M002" and item["severity"] == "error"
                for item in validation["findings"]
            )
        )
        finalized = self.service.execute(
            "finalize_milestone", root=str(root), target="M001", payload={}
        )
        self.assertEqual(finalized["next_milestone"], "M002")

    def test_start_enforces_dependencies_and_scope_conflicts(self) -> None:
        root = self.root()
        self.initialize(root, mode="standard")
        self.service.execute(
            "create_milestone",
            root=str(root),
            payload={"id": "M001", "title": "Safety", "interfaces_stable": True},
        )
        self.service.execute(
            "set_plan",
            root=str(root),
            payload={
                "milestone_id": "M001",
                "tasks": [
                    {
                        "id": "a",
                        "title": "A",
                        "objective": "A",
                        "acceptance": ["A"],
                        "file_scope": ["src/shared/**"],
                    },
                    {
                        "id": "b",
                        "title": "B",
                        "objective": "B",
                        "acceptance": ["B"],
                        "file_scope": ["src/shared/file.py"],
                    },
                    {
                        "id": "c",
                        "title": "C",
                        "objective": "C",
                        "depends_on": ["a"],
                        "acceptance": ["C"],
                        "file_scope": ["src/c/**"],
                    },
                ],
            },
        )
        with self.assertRaisesRegex(ValueError, "incomplete dependencies"):
            self.service.execute(
                "transition", root=str(root), target="c", payload={"status": "in_progress"}
            )
        self.service.execute(
            "transition", root=str(root), target="a", payload={"status": "in_progress"}
        )
        with self.assertRaisesRegex(ValueError, "file scope conflicts"):
            self.service.execute(
                "transition", root=str(root), target="b", payload={"status": "in_progress"}
            )
        self.assertEqual(self.service.execute("next", root=str(root))["wave"], [])

    def test_concurrent_independent_transitions_preserve_updates(self) -> None:
        root = self.root()
        registry = self.base / "shared.db"
        setup = SDDService(SourceRegistry(registry))
        result = setup.execute(
            "init",
            root=str(root),
            payload={"name": "Atlas", "goal": "Parallel", "mode": "standard"},
        )
        self.assertTrue(result["ok"])
        setup.execute(
            "create_milestone",
            root=str(root),
            payload={"id": "M001", "title": "Parallel", "interfaces_stable": True},
        )
        setup.execute(
            "set_plan",
            root=str(root),
            payload={
                "milestone_id": "M001",
                "tasks": [
                    {
                        "id": "a",
                        "title": "A",
                        "objective": "A",
                        "acceptance": ["A"],
                        "file_scope": ["src/a/**"],
                    },
                    {
                        "id": "b",
                        "title": "B",
                        "objective": "B",
                        "acceptance": ["B"],
                        "file_scope": ["src/b/**"],
                    },
                ],
            },
        )

        def start(task_id: str) -> dict:
            worker = SDDService(SourceRegistry(registry))
            return worker.execute(
                "transition", root=str(root), target=task_id, payload={"status": "in_progress"}
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(start, ["a", "b"]))
        self.assertTrue(all(item["ok"] for item in results))
        plan = json.loads((root / ".sdd" / "milestones" / "M001" / "plan.json").read_text())
        self.assertEqual(
            {task["id"] for task in plan["tasks"] if task["status"] == "in_progress"}, {"a", "b"}
        )
        self.assertGreaterEqual(plan["revision"], 3)

    def test_update_task_is_targeted_and_revision_checked(self) -> None:
        root = self.root()
        self.initialize(root, mode="standard")
        self.service.execute(
            "create_milestone",
            root=str(root),
            payload={"id": "M001", "title": "Targeted", "interfaces_stable": True},
        )
        plan = self.service.execute(
            "set_plan",
            root=str(root),
            payload={
                "milestone_id": "M001",
                "tasks": [
                    {
                        "id": "a",
                        "title": "A",
                        "objective": "Old",
                        "acceptance": ["Old"],
                        "file_scope": ["src/a/**"],
                    },
                    {
                        "id": "b",
                        "title": "B",
                        "objective": "B",
                        "acceptance": ["B"],
                        "file_scope": ["src/b/**"],
                    },
                ],
            },
        )
        updated = self.service.execute(
            "update_task",
            root=str(root),
            target="a",
            payload={"objective": "New", "acceptance": ["New proof"]},
            options={"expected_revision": plan["revision"]},
        )
        self.assertEqual(updated["task"]["objective"], "New")
        stored = json.loads((root / ".sdd" / "milestones" / "M001" / "plan.json").read_text())
        self.assertEqual(
            next(task for task in stored["tasks"] if task["id"] == "b")["objective"], "B"
        )
        with self.assertRaisesRegex(ValueError, "Plan revision changed"):
            self.service.execute(
                "update_task",
                root=str(root),
                target="a",
                payload={"notes": "stale write"},
                options={"expected_revision": plan["revision"]},
            )

    def test_invalid_completion_evidence_is_transactional(self) -> None:
        root = self.root()
        self.initialize(root, mode="deep")
        self.service.execute(
            "create_milestone",
            root=str(root),
            payload={"id": "M001", "title": "Evidence", "interfaces_stable": True},
        )
        self.service.execute(
            "set_plan",
            root=str(root),
            payload={
                "milestone_id": "M001",
                "tasks": [
                    {
                        "id": "work",
                        "title": "Work",
                        "objective": "Work",
                        "acceptance": ["Works"],
                        "file_scope": ["src/**"],
                    }
                ],
            },
        )
        self.service.execute(
            "transition", root=str(root), target="work", payload={"status": "in_progress"}
        )
        with self.assertRaisesRegex(ValueError, "Evidence requires"):
            self.service.execute(
                "transition",
                root=str(root),
                target="work",
                payload={"status": "done", "evidence": {"passed": False}},
            )
        plan = json.loads((root / ".sdd" / "milestones" / "M001" / "plan.json").read_text())
        state = json.loads((root / ".sdd" / "state.json").read_text())
        task = plan["tasks"][0]
        self.assertEqual(task["status"], "in_progress")
        self.assertEqual(state["current_tasks"], ["work"])
        self.assertEqual(state["status"], "executing")
        self.assertEqual(
            len((root / ".sdd" / "milestones" / "M001" / "evidence.jsonl").read_text()), 0
        )

    def test_transition_rolls_back_when_late_event_write_fails(self) -> None:
        root = self.root()
        self.initialize(root, mode="quick")
        self.service.execute(
            "create_milestone",
            root=str(root),
            payload={"id": "M001", "title": "Rollback", "interfaces_stable": True},
        )
        self.service.execute(
            "set_plan",
            root=str(root),
            payload={"milestone_id": "M001", "tasks": [{"id": "work", "title": "Work"}]},
        )
        self.service.execute(
            "transition", root=str(root), target="work", payload={"status": "in_progress"}
        )
        events = root / ".sdd" / "events.jsonl"
        before = events.read_bytes()
        original_event = self.service._event
        self.service._event = lambda *args, **kwargs: (_ for _ in ()).throw(OSError("disk full"))
        try:
            with self.assertRaisesRegex(OSError, "disk full"):
                self.service.execute(
                    "transition",
                    root=str(root),
                    target="work",
                    payload={
                        "status": "done",
                        "evidence": {"result": "passed", "passed": True},
                    },
                )
        finally:
            self.service._event = original_event
        plan = json.loads((root / ".sdd" / "milestones" / "M001" / "plan.json").read_text())
        self.assertEqual(plan["tasks"][0]["status"], "in_progress")
        self.assertEqual(events.read_bytes(), before)

    def test_evidence_task_id_cannot_override_target(self) -> None:
        root = self.root()
        self.initialize(root, mode="quick")
        self.service.execute(
            "create_milestone",
            root=str(root),
            payload={"id": "M001", "title": "Evidence", "interfaces_stable": True},
        )
        self.service.execute(
            "set_plan",
            root=str(root),
            payload={
                "milestone_id": "M001",
                "tasks": [
                    {"id": "a", "title": "A", "objective": "A"},
                    {"id": "b", "title": "B", "objective": "B"},
                ],
            },
        )
        with self.assertRaisesRegex(ValueError, "does not match"):
            self.service.execute(
                "record_evidence",
                root=str(root),
                target="a",
                payload={"task_id": "b", "result": "passed", "passed": True},
            )

    def test_set_plan_rejects_unreconciled_execution_statuses(self) -> None:
        root = self.root()
        self.initialize(root, mode="standard")
        self.service.execute(
            "create_milestone",
            root=str(root),
            payload={"id": "M001", "title": "Plan", "interfaces_stable": True},
        )
        with self.assertRaisesRegex(ValueError, "status.*set_plan"):
            self.service.execute(
                "set_plan",
                root=str(root),
                payload={
                    "milestone_id": "M001",
                    "tasks": [
                        {"id": "done", "title": "Done", "status": "done"},
                    ],
                },
            )

    def test_invalid_risk_is_rejected_and_plan_is_not_coerced(self) -> None:
        root = self.root()
        self.initialize(root, mode="standard")
        self.service.execute(
            "create_milestone",
            root=str(root),
            payload={"id": "M001", "title": "Plan", "interfaces_stable": True},
        )
        with self.assertRaisesRegex(ValueError, "Invalid task risk"):
            self.service.execute(
                "set_plan",
                root=str(root),
                payload={
                    "milestone_id": "M001",
                    "tasks": [{"id": "work", "title": "Work", "risk": "extreme"}],
                },
            )

    def test_custom_decision_id_is_rejected_consistently(self) -> None:
        root = self.root()
        self.initialize(root, mode="quick")
        with self.assertRaisesRegex(ValueError, "ADR"):
            self.service.execute(
                "record_decision",
                root=str(root),
                target="DEC-1",
                payload={"title": "Decision", "decision": "Use it"},
            )

    def test_explicit_false_evidence_is_not_reclassified_from_result(self) -> None:
        root = self.root()
        self.initialize(root, mode="quick")
        self.service.execute(
            "create_milestone",
            root=str(root),
            payload={"id": "M001", "title": "Evidence", "interfaces_stable": True},
        )
        result = self.service.execute(
            "record_evidence",
            root=str(root),
            payload={"result": "no errors observed", "passed": False},
        )
        self.assertIs(result["evidence"]["passed"], False)
        self.assertEqual(result["evidence"]["task_id"], None)

    def test_plan_markdown_is_generated(self) -> None:
        root = self.root()
        self.initialize(root, mode="quick")
        self.service.execute(
            "create_milestone",
            root=str(root),
            payload={"id": "M001", "title": "Plan", "interfaces_stable": True},
        )
        self.service.execute(
            "set_plan",
            root=str(root),
            payload={
                "milestone_id": "M001",
                "tasks": [{"id": "work", "title": "Work", "objective": "Do work"}],
            },
        )
        plan_path = root / ".sdd" / "milestones" / "M001" / "PLAN.md"
        self.assertTrue(plan_path.is_file())
        self.assertIn("work", plan_path.read_text(encoding="utf-8"))

    def test_symlinked_authoritative_state_is_rejected(self) -> None:
        root = self.root()
        self.initialize(root, mode="quick")
        outside = self.base / "outside-events.jsonl"
        events = root / ".sdd" / "events.jsonl"
        events.unlink()
        events.symlink_to(outside)
        with self.assertRaisesRegex(ValueError, "symlink"):
            self.service.execute("status", root=str(root))

        root2 = self.base / "repo2"
        root2.mkdir()
        self.initialize(root2, mode="quick")
        self.service.execute(
            "create_milestone",
            root=str(root2),
            payload={"id": "M001", "title": "Symlinked milestone"},
        )
        outside_milestone = self.base / "outside-milestone"
        milestone_dir = root2 / ".sdd" / "milestones" / "M001"
        milestone_dir.rename(outside_milestone)
        milestone_dir.symlink_to(outside_milestone, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlink"):
            self.service.execute("status", root=str(root2))

    def test_symlinked_events_are_rejected_before_context_reads(self) -> None:
        root = self.root()
        self.initialize(root, mode="quick")
        outside = self.base / "outside-events.jsonl"
        events = root / ".sdd" / "events.jsonl"
        events.unlink()
        events.symlink_to(outside)
        with self.assertRaisesRegex(ValueError, "symlink"):
            self.service.execute("context_pack", root=str(root))

    def test_registry_projection_failure_does_not_fail_init(self) -> None:
        class BrokenRegistry:
            def register(self, *_args, **_kwargs):
                raise OSError("registry unavailable")

        root = self.root()
        result = SDDService(BrokenRegistry()).execute(
            "init", root=str(root), payload={"goal": "Registry failure", "mode": "quick"}
        )
        self.assertTrue(result["ok"])
        self.assertIsNone(result["source"])
        self.assertIn("registry unavailable", result["source_warning"])
        self.assertTrue((root / ".sdd" / "project.json").is_file())

    def test_registry_initialization_failure_does_not_fail_init(self) -> None:
        root = self.root()
        with patch.object(
            SourceRegistry, "_initialize", side_effect=OSError("registry init unavailable")
        ):
            result = SDDService().execute(
                "init", root=str(root), payload={"goal": "Registry init failure", "mode": "quick"}
            )
        self.assertTrue(result["ok"])
        self.assertIn("registry init unavailable", result["source_warning"])
        self.assertTrue((root / ".sdd" / "project.json").is_file())

    def test_registry_warning_is_not_persisted_in_canonical_state(self) -> None:
        class BrokenRegistry:
            def register(self, *_args, **_kwargs):
                raise OSError("registry unavailable")

        root = self.root()
        result = SDDService(BrokenRegistry()).execute(  # type: ignore[arg-type]
            "init", root=str(root), payload={"goal": "Projection", "mode": "quick"}
        )
        self.assertIn("registry unavailable", result["source_warning"])
        project = json.loads((root / ".sdd" / "project.json").read_text(encoding="utf-8"))
        self.assertNotIn("source_warning", project)

    def test_malformed_task_list_values_are_rejected(self) -> None:
        root = self.root()
        self.initialize(root, mode="quick")
        self.service.execute(
            "create_milestone",
            root=str(root),
            payload={"id": "M001", "title": "Types", "interfaces_stable": True},
        )
        self.service.execute(
            "set_plan",
            root=str(root),
            payload={"milestone_id": "M001", "tasks": [{"id": "work", "title": "Work"}]},
        )
        with self.assertRaisesRegex(ValueError, "file_scope"):
            self.service.execute(
                "update_task", root=str(root), target="work", payload={"file_scope": 42}
            )
        with self.assertRaisesRegex(ValueError, "acceptance"):
            self.service.execute(
                "update_task",
                root=str(root),
                target="work",
                payload={"acceptance": {"unexpected": "object"}},
            )
        with self.assertRaisesRegex(ValueError, "decision ids"):
            self.service.execute(
                "update_task",
                root=str(root),
                target="work",
                payload={"decision_ids": "ADR-0001"},
            )

    def test_malformed_canonical_json_is_not_treated_as_empty_state(self) -> None:
        root = self.root()
        self.initialize(root, mode="quick")
        (root / ".sdd" / "project.json").write_text("[]\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "JSON object"):
            self.service.execute("status", root=str(root))

    def test_empty_canonical_object_is_not_treated_as_healthy_state(self) -> None:
        root = self.root()
        self.initialize(root, mode="quick")
        (root / ".sdd" / "project.json").write_text("{}\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "project.json.*required fields"):
            self.service.execute("status", root=str(root))

    def test_missing_canonical_project_file_is_not_defaulted(self) -> None:
        root = self.root()
        self.initialize(root, mode="quick")
        (root / ".sdd" / "project.json").unlink()
        with self.assertRaisesRegex(ValueError, "No SDD project"):
            self.service.execute("status", root=str(root))

    def test_decision_and_project_list_fields_reject_scalars(self) -> None:
        root = self.root()
        with self.assertRaisesRegex(ValueError, "success criteria"):
            self.service.execute(
                "init",
                root=str(root),
                payload={"goal": "Typed project", "mode": "quick", "success_criteria": "one"},
            )
        root = self.base / "repo2"
        root.mkdir()
        self.initialize(root, mode="quick")
        with self.assertRaisesRegex(ValueError, "decision alternatives"):
            self.service.execute(
                "record_decision",
                root=str(root),
                payload={"title": "Typed decision", "alternatives": "one"},
            )

    def test_malformed_jsonl_is_not_silently_ignored(self) -> None:
        root = self.root()
        self.initialize(root, mode="quick")
        events = root / ".sdd" / "events.jsonl"
        with events.open("a", encoding="utf-8") as handle:
            handle.write("not-json\n")
        with self.assertRaisesRegex(ValueError, "Malformed SDD JSONL"):
            self.service.execute("context_pack", root=str(root))

    def test_missing_canonical_state_file_is_not_defaulted(self) -> None:
        root = self.root()
        self.initialize(root, mode="quick")
        (root / ".sdd" / "state.json").unlink()
        with self.assertRaisesRegex(ValueError, "Missing required SDD file"):
            self.service.execute("status", root=str(root))

    def test_upsert_spec_requires_requirement_list(self) -> None:
        root = self.root()
        self.initialize(root, mode="quick")
        with self.assertRaisesRegex(ValueError, "requirements must be a list"):
            self.service.execute(
                "upsert_spec",
                root=str(root),
                payload={"requirements": "REQ-001"},
            )

    def test_malformed_plan_and_roadmap_collections_are_rejected(self) -> None:
        root = self.root()
        self.initialize(root, mode="quick")
        roadmap = root / ".sdd" / "roadmap.json"
        roadmap.write_text('{"milestones": "M001"}\n', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "milestones must be a list"):
            self.service.execute("status", root=str(root))

        root2 = self.base / "repo2"
        root2.mkdir()
        self.initialize(root2, mode="quick")
        self.service.execute(
            "create_milestone", root=str(root2), payload={"id": "M001", "title": "Plan"}
        )
        plan = root2 / ".sdd" / "milestones" / "M001" / "plan.json"
        plan.write_text('{"tasks": "work"}\n', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "plan tasks must be a list"):
            self.service.execute(
                "set_plan",
                root=str(root2),
                payload={"milestone_id": "M001", "tasks": [{"id": "replacement"}]},
            )
        with self.assertRaisesRegex(ValueError, "plan tasks must be a list"):
            self.service.execute("next", root=str(root2), target="M001")

    def test_init_does_not_overwrite_partial_sdd_without_force(self) -> None:
        root = self.root()
        sdd = root / ".sdd"
        sdd.mkdir()
        marker = sdd / "partial.json"
        marker.write_text("partial\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "incomplete or malformed"):
            self.service.execute(
                "init", root=str(root), payload={"goal": "Recover", "mode": "quick"}
            )
        self.assertEqual(marker.read_text(encoding="utf-8"), "partial\n")
        self.assertFalse((sdd / "project.json").exists())

    def test_stale_lock_is_not_removed_while_owner_process_is_alive(self) -> None:
        root = self.root()
        self.initialize(root, mode="quick")
        lock_dir = root / ".sdd" / ".locks"
        lock_dir.mkdir(exist_ok=True)
        lock_path = lock_dir / "state.lock"
        lock_path.write_text('{"pid": %d, "created_at": 0}' % os.getpid(), encoding="utf-8")
        old_time = time.time() - 1
        os.utime(lock_path, (old_time, old_time))
        with self.assertRaises(TimeoutError):
            with project_lock(root / ".sdd", timeout=0.05, stale_after=0):
                pass

    def test_stale_lock_from_dead_process_is_reclaimed(self) -> None:
        root = self.root()
        self.initialize(root, mode="quick")
        lock_dir = root / ".sdd" / ".locks"
        lock_dir.mkdir(exist_ok=True)
        lock_path = lock_dir / "state.lock"
        lock_path.write_text('{"pid": 2147483647, "created_at": 0}', encoding="utf-8")
        old_time = time.time() - 1
        os.utime(lock_path, (old_time, old_time))
        with project_lock(root / ".sdd", timeout=0.2, stale_after=0):
            self.assertTrue(lock_path.exists())

    def test_zombie_lock_owner_is_reclaimable(self) -> None:
        root = self.root()
        self.initialize(root, mode="quick")
        lock_dir = root / ".sdd" / ".locks"
        lock_dir.mkdir(exist_ok=True)
        lock_path = lock_dir / "state.lock"
        lock_path.write_text('{"pid": 2147483647, "created_at": 0}', encoding="utf-8")
        old_time = time.time() - 1
        os.utime(lock_path, (old_time, old_time))
        with patch("hermes_sdd.storage._pid_is_alive", return_value=False):
            with project_lock(root / ".sdd", timeout=0.2, stale_after=0):
                self.assertTrue(lock_path.exists())

    def test_implicit_remote_root_requires_explicit_path(self) -> None:
        with patch.dict(os.environ, {"TERMINAL_ENV": "ssh", "TERMINAL_CWD": "~"}, clear=False):
            with self.assertRaisesRegex(ValueError, "explicit project root"):
                self.service.execute("status", root=None)


if __name__ == "__main__":
    unittest.main()
