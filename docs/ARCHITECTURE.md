# Architecture

## System shape

```text
                    ┌───────────────────────────────┐
                    │ Hermes Agent plugin           │
CLI / TUI / chat ──▶│ one `sdd` tool + commands    │
Desktop chat     ──▶│ five on-demand skills         │
Dashboard chat   ──▶└──────────────┬────────────────┘
                                   │
                                   ▼
                          ┌─────────────────┐
                          │ SDDService      │
                          │ pure operations │
                          └───────┬─────────┘
                                  │
                    ┌─────────────┴──────────────┐
                    ▼                            ▼
             project-local `.sdd/`       source registry SQLite
             authoritative state         UI discovery only
                    ▲                            ▲
                    │                            │
       ┌────────────┴────────────┐      ┌────────┴────────┐
       │ shared FastAPI backend │      │ registered repos │
       └───────┬────────┬───────┘      └─────────────────┘
               │        │
               ▼        ▼
        Dashboard UI   Desktop UI
```

## Why the Agent plugin is the primary integration

Hermes's Python Agent plugin surface is available wherever the agent runs: CLI, TUI, Desktop/Dashboard chat, gateways, and worker processes. Dashboard and Desktop use unrelated frontend SDKs. Therefore the durable workflow belongs in the Python core, and each visual surface remains a thin adapter.

This prevents semantic drift such as a Dashboard changing a task differently from a Desktop plugin or a TUI session lacking an operation available elsewhere.

## Authoritative state

Project-local files are chosen over a central database because they:

- travel with the repository and branch;
- survive session resets and model changes;
- can be reviewed, diffed, merged, backed up, or edited in an emergency;
- are available to fresh-context subagents without shared conversational memory;
- do not require a daemon or service to recover a project.

SQLite stores only source paths used by visual clients. It is intentionally non-authoritative.

## Data model

### Project

Long-lived goal, scope, success criteria, constraints, non-goals, engineering principles, and rigor mode.

### Requirement

A stable behavioral or quality contract with acceptance criteria. Requirements avoid internal implementation details unless the implementation constraint is itself mandatory.

### ADR

A costly-to-reverse or cross-cutting decision with context, alternatives, and consequences. Routine choices remain in task context to avoid documentation inflation.

### Milestone

A demonstrable outcome with linked requirements and exit criteria. A milestone is not a component bucket.

### Task

A context-sized, reviewable unit with dependencies, acceptance criteria, file scope, risk, and role. Task status is operational state, not proof of correctness.

### Evidence

Concise, reproducible verification metadata. Logs and large artifacts remain outside `.sdd/` and are referenced by path.

### Event

Append-only lifecycle observation for recovery and auditing. Events do not duplicate full documents.

## Adaptive rigor

The mode controls default expectations, not a rigid state machine. The core always supports the same operations. Skills interpret the mode to decide how much architecture, evidence, independent review, and decomposition is justified.

This is important because complexity is local: a program-scale project can contain a trivial task, and a small repository can contain a critical migration.

## Context engineering

### Progressive disclosure

Only one tool schema is permanently visible to the model. Detailed instructions reside in intent-loaded skills. This removes the repeated schema cost of 10–30 separate lifecycle tools.

### Context packs

The context pack is deterministic and prioritized. It does not call an LLM, embed documents, or summarize recursively. This yields predictable cost, avoids hidden semantic loss, and makes tests straightforward.

### Checkpoints

A checkpoint hashes authoritative and scoped files. Wildcard scopes are expanded recursively inside the repository with a hard file-count bound; symlinks escaping the repository are ignored. Deltas identify added, removed, and changed files. This lets a new session orient around change rather than reload every historical artifact.

### Bounded status and search

Status is an orientation response, not a project export: it provides counts, target-scoped blocking findings, a
deterministic recommended action, and a capped active-task preview. Compact mode omits the preview. Detailed
milestone/task data should be fetched only when selected by `next`, `search`, or a context pack. Search remains a
literal substring scan today; large-project semantic/indexed search is a future scalability option.

### Main-session discipline

The main session may implement small work directly. For large work, it should orchestrate and receive compact worker summaries. Worker transcripts are not persisted as project state.

## Scheduling

The scheduler first filters tasks whose dependencies are terminal (`done` or intentionally `skipped`). It then greedily builds a wave up to `max_parallel`, rejecting:

- overlapping file scopes;
- multiple tasks when interfaces are unstable;
- co-scheduling with a critical-risk task;
- tasks beyond the configured limit.

Unknown scope is treated as global conflict. This is intentionally conservative: false serialization costs time; false independence can corrupt work.

## Verification

Validation checks structural consistency:

- missing goals and acceptance criteria;
- unknown requirement references;
- duplicate or unknown requirement, milestone, task, and ADR references;
- roadmap/milestone drift and invalid plan revisions;
- dependency cycles;
- unplanned must-have requirements;
- unsafe missing file scopes in deep/program implementation work;
- missing or unsuccessful evidence under the active policy;
- stale current-task pointers and blocked/skipped tasks without reasons;
- oversized artifacts;
- missing architecture in deep/program work.

It cannot replace actual tests. `finalize_milestone` requires all tasks to be terminal and rejects structural errors unless explicitly forced. The explicit `options.force` escape hatch bypasses active-milestone, empty-plan, incomplete-task, and validation gates, but requires `payload.override_reason` and marks the milestone `overridden` rather than `verified`; the reason is recorded in the summary and event. This is an administrative override, not proof the work is verified. Structured exit criteria use stable milestone-scoped IDs and require successful evidence explicitly linked through a task that also links the criterion. Legacy prose-only milestones must be migrated before verified finalization; the gate validates traceability metadata, not factual truth.

## Concurrency and durability

Metadata writes use atomic replacement and a short-lived cross-platform lock file. Read-modify-write operations occur inside that lock, and milestone plans carry monotonically increasing revisions for optimistic client checks. JSONL appends are flushed and fsynced. Task starts re-check dependencies, active milestone, interface stability, critical-risk isolation, and overlap with already-running scopes; safety therefore does not depend on a previously rendered wave remaining current. The lock protects SDD metadata only; source-control isolation still handles code-level merges.

## Security

- IDs are restricted to a conservative character set.
- Project roots are resolved to directories.
- Context file collection refuses paths escaping the repository.
- Desktop REST calls are namespace-scoped by Hermes.
- Dashboard routes use Hermes's normal authentication gate.
- Python plugins and Desktop renderer plugins are trusted code with host authority; this project does not provide a sandbox.

## Extension points

Future additions should preserve the one-core/thin-adapter rule. Good candidates:

- Git worktree provisioning for a selected safe wave;
- CI artifact ingestion as evidence;
- GitHub issue/PR projection;
- richer requirement coverage visualization;
- pluggable estimators for model-specific context budgets;
- an upstream Hermes TUI contribution API, should one become available.

Avoid adding an LLM call inside every state transition, an always-on prompt injection hook, or separate source-of-truth stores per UI.
