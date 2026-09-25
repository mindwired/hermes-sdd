"""Compact tool schema for the Hermes SDD plugin."""

SDD_SCHEMA = {
    "name": "sdd",
    "description": (
        "Use for durable multi-session, ambiguous, risky, or coordinated project work; keep trivial "
        "one-turn edits in normal workflow. Call status for a bounded overview, next for the safe "
        "task wave, and context_pack for one executor; avoid repeatedly requesting full state. "
        "Operations: init/configure, upsert_spec, create_milestone/update_milestone, set_plan/"
        "update_task, next/transition, record_decision/record_evidence, finalize_milestone, "
        "context_checkpoint/context_delta/context_pack, validate/search, and UI source registry. "
        "Changing status requires transition with payload.status (pending, in_progress, blocked, "
        "done, skipped), not update_task. Evidence requires result, command, artifact, or details; "
        "record_decision requires ADR-0001 IDs. For exact payloads load sdd:sdd-start, sdd:sdd-plan, "
        "sdd:sdd-execute, or sdd:sdd-verify."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "description": (
                    "Supported: init/status/configure, upsert_spec, create_milestone/update_milestone, "
                    "set_plan/update_task, next/transition, record_decision/record_evidence, "
                    "finalize_milestone, context_checkpoint/context_delta/context_pack, validate, "
                    "search, register_source/list_sources/remove_source. status is read-only; use "
                    "next to select work. Use transition with payload.status to change task state, "
                    "update_task for metadata, and record_evidence with result, command, artifact, or "
                    "details. Link each milestone exit criterion through task.exit_criteria_ids and "
                    "successful evidence.exit_criteria_ids; legacy prose criteria must be migrated "
                    "with update_milestone before verified finalization. For exact payloads load "
                    "sdd:sdd-start, sdd:sdd-plan, sdd:sdd-execute, "
                    "sdd:sdd-verify, or sdd:sdd-recover."
                ),
                "enum": [
                    "init",
                    "status",
                    "configure",
                    "upsert_spec",
                    "create_milestone",
                    "update_milestone",
                    "set_plan",
                    "update_task",
                    "next",
                    "transition",
                    "record_decision",
                    "record_evidence",
                    "finalize_milestone",
                    "context_pack",
                    "context_checkpoint",
                    "context_delta",
                    "validate",
                    "search",
                    "register_source",
                    "list_sources",
                    "remove_source",
                ],
            },
            "root": {
                "type": "string",
                "description": "Project root. Omit to use the active Hermes working directory.",
            },
            "target": {
                "type": "string",
                "description": (
                    "Target ID: task for transition/update_task/record_evidence/context_pack; "
                    "milestone for next/finalize_milestone; checkpoint for context_delta; "
                    "source ID/path for remove_source."
                ),
            },
            "payload": {
                "type": "object",
                "description": (
                    "Operation-specific structured data. transition requires status; "
                    "record_evidence requires result, command, artifact, or details; "
                    "record_decision IDs use ADR-0001 format. Keep prose concise and put large "
                    "research in files. Link criterion proof with milestone.exit_criteria_records, "
                    "task.exit_criteria_ids, and evidence.exit_criteria_ids."
                ),
                "additionalProperties": True,
            },
            "options": {
                "type": "object",
                "description": "Optional limits and behavior flags such as detail, limit, budget_tokens, or allow_parallel.",
                "additionalProperties": True,
            },
        },
        "required": ["operation"],
        "additionalProperties": False,
    },
}
