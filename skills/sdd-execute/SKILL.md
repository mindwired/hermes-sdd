---
name: sdd-execute
description: Execute an SDD milestone efficiently using bounded context packs, safe parallel waves, durable checkpoints, and evidence-based task completion.
license: MIT
compatibility: Hermes Agent with the sdd plugin enabled and normal coding tools available.
metadata:
  author: hermes-sdd
  version: "0.1.0"
---

# Execute an SDD milestone

The goal is working, maintainable software. SDD state exists to preserve intent and coordinate work; do not spend more effort updating process artifacts than implementing and validating the result.

## Select work

1. Call `sdd(operation="next")` for the active milestone. If its wave is empty, read `reason` and reconcile/finalize rather than retrying the same selection.
2. Use the returned wave as the maximum parallel set, not a requirement to parallelize. Do not call `status` with full detail repeatedly; use bounded `status`, then `next`, then a task-specific `context_pack`.
3. Execute a task directly when it is small and the current session has clean context. Delegate when the task is large, specialized, independent, or would pollute the orchestrator context.
4. Before a substantial task, create a checkpoint:

```json
{"operation":"context_checkpoint","root":"<repo>","payload":{"task_id":"M001-T001"}}
```

5. Build a bounded context pack:

```json
{"operation":"context_pack","root":"<repo>","target":"M001-T001","payload":{"checkpoint_id":"<checkpoint>"},"options":{"budget_tokens":12000}}
```

The pack is an index. The executor must still read the exact files it edits.

## Task lifecycle

Mark the task in progress before edits:

```json
{"operation":"transition","root":"<repo>","target":"M001-T001","payload":{"status":"in_progress"}}
```

During implementation:

- honor linked requirements and ADRs;
- implement the task's `exit_criteria_ids` links where applicable; add a link with `update_task` before recording
  criterion-specific evidence;
- inspect existing conventions rather than inventing parallel abstractions;
- keep edits inside the declared scope unless a discovered dependency makes expansion necessary;
- when scope expands, stop conflicting workers and call `update_task` before continuing;
- implement the simplest design satisfying the acceptance criteria;
- run focused checks early, then the appropriate broader checks;
- do not mark work complete from reasoning alone.

## Completion and evidence

Record concise, reproducible evidence. Prefer commands, test names, artifact paths, screenshots, benchmark results, migrations, or manual verification steps over narrative confidence.

```json
{"operation":"transition","root":"<repo>","target":"M001-T001","payload":{"status":"done","summary":"Implemented the end-to-end path.","evidence":{"type":"test","command":"uv run pytest tests/integration/test_path.py","result":"passed","requirement_ids":["REQ-001"]}}}
```

For low-risk quick tasks, one focused check may be enough. For high/critical tasks or deep/program mode, provide evidence for all meaningful acceptance criteria. When evidence verifies a milestone exit criterion, include that ID in `evidence.exit_criteria_ids`; the target task must also link it in `exit_criteria_ids`.

If blocked, record the real blocker and what was tried. Do not repeatedly retry the same approach without new information:

```json
{"operation":"transition","root":"<repo>","target":"M001-T001","payload":{"status":"blocked","blocked_reason":"Specific dependency or decision required"}}
```

## Context hygiene

Keep the main session lean: collect short worker summaries and durable artifacts, not full subagent transcripts. Use checkpoint deltas to avoid rereading unchanged SDD files. Do not inject the entire roadmap into each executor. Finish one wave, reconcile results, then request the next wave.

## When the milestone is exhausted

Load `sdd-verify`. Never finalize automatically merely because all tasks say `done`.
