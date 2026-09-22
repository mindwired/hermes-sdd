"""Compact tool schema for the Hermes SDD plugin."""

SDD_SCHEMA = {
    "name": "sdd",
    "description": (
        "Maintain a compact, durable spec-driven project graph. Use for large or "
        "multi-session work: initialize, store requirements/architecture, plan milestones, "
        "select dependency-safe work, update task state, record evidence/decisions, build "
        "bounded context packs, validate traceability, and manage UI source paths. For exact "
        "payloads load the sdd:sdd-start, sdd:sdd-plan, sdd:sdd-execute, or "
        "sdd:sdd-verify skill. Do not use for trivial one-turn edits."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
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
                "description": "Optional task, milestone, checkpoint, decision, or source identifier.",
            },
            "payload": {
                "type": "object",
                "description": "Operation-specific structured data. Keep prose concise and put large research in files.",
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
