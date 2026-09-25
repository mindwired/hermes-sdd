# `.sdd/` state format

## Authority and portability

Project-local `.sdd/` files are the source of truth. They are deliberately plain JSON, Markdown, and JSONL so
humans, Git, agents, scripts, and alternate UIs can inspect them without a service. The registry database under
`$HERMES_HOME` only remembers which repository paths visual clients should list.

Canonical JSON documents must contain an object at the top level, and collection fields must retain their documented
list shape. Required project metadata fields (`name`, `mode`, and `status`) and milestone/plan files must be present. Malformed JSON, malformed JSONL records, or symlinks anywhere below
`.sdd/` are integrity errors; the plugin refuses to read or write through them instead of silently defaulting or
following links outside the project.

## Top-level files

### `project.json`

Project identity, goal, mode, constraints, success criteria, complexity score/signals, timestamps, and format
version.

### `state.json`

Current project status, active milestone, current tasks, last checkpoint, and update timestamp. It is a compact
resume pointer, not a substitute for reading the active milestone plan.

### `requirements.json`

A versioned requirement collection. Each requirement has an id, title, normative statement, acceptance criteria,
priority, status, source, and timestamps. Markdown rendering is derived in `REQUIREMENTS.md`.

### `architecture.md`

Only durable architecture context needed across tasks. Avoid dumping exploratory transcripts here.

### `events.jsonl`

Append-only lifecycle facts: initialization, specification updates, planning, transitions, evidence, validation,
and finalization. Events support recovery and audit but do not override current JSON state.

## Milestones

Each `.sdd/milestones/<id>/` contains:

- `milestone.json`: objective, requirement links, exit criteria, dependencies, risk, status, interface stability,
  and `exit_criteria_schema_version: 1` with stable `exit_criteria_records` (`id`, `text`, `status`). IDs use
  `<milestone-id>-EC001`; removed criteria become `retired` and their IDs are never reused. Existing schema-v1
  milestones without these fields are legacy/unmapped until updated through `update_milestone`.
- `plan.json`: revisioned task DAG.
- `PLAN.md`: human rendering of the current plan.
- `summary.md`: verification/finalization record.

A task includes id, title, objective, status, risk, dependencies, acceptance criteria, conservative file scopes,
requirement links, `exit_criteria_ids`, evidence ids, notes, summary, and timestamps. A criterion link must refer to
an active criterion in the same milestone.

Milestone status `overridden` records an administrative forced finalization. It is not equivalent to `verified`;
the reason is persisted in the finalization event and summary. A forced finalization with no remaining milestones
marks project/state status `overridden`, not `complete`.
Criterion-to-evidence links are explicit: map a criterion to one or more tasks with `exit_criteria_ids`, then
record successful evidence with the same IDs in `evidence.exit_criteria_ids`. Evidence must belong to a non-skipped
task that also links that active criterion. Finalization blocks if any active structured criterion lacks such
evidence. This verifies traceability metadata, not the truth of user-entered evidence claims. Existing milestones
without structured records receive a warning and cannot be normally finalized until migrated using
`update_milestone` with `exit_criteria` or explicit `exit_criteria_records`. Updating legacy prose preserves stable
IDs where criteria are unchanged and retires removed IDs; changing criterion wording creates a new ID.

`plan.json.revision` increments on every task/plan mutation. Callers may pass `expected_revision` to prevent stale
whole-plan or targeted updates from overwriting concurrent work.

## Evidence

Evidence records are immutable JSONL entries under `.sdd/milestones/<id>/evidence.jsonl`. Typical fields include
type, task/milestone, command, result, `passed`, details, artifact paths, and timestamp. Manual completion evidence
may be recorded as failed/insufficient; it does not automatically satisfy program/high-risk verification gates.

An active `must` requirement linked to a milestone or one of its tasks needs successful evidence that explicitly
lists its requirement ID before the milestone can be verified. The evidence must belong to a non-skipped task in
that milestone, and that task must also link the requirement. Validation reports this as a warning while the
milestone is unfinished and as an error once its tasks are terminal; finalization blocks on the error. Taskless,
cross-linked, or skipped-task evidence does not count. This checks traceability of recorded evidence, not the truth
of a manually entered claim. `require_evidence: never` disables per-task risk-based evidence checks, but does not
waive this must-have requirement proof gate. A terminal plan (all tasks done or skipped) is treated as a completed
milestone for this gate even if cached milestone status has drifted.

## Checkpoints

A checkpoint stores hashes of authoritative `.sdd/` files plus task-scoped source files. Glob patterns are
expanded to concrete files at checkpoint time. A delta reports added, changed, and removed paths without reading
unrelated source content into the agent context.

## Context exclusions

`config.json.exclude_patterns` is a project-local list of glob patterns excluded from task-scoped checkpoint
hashes and context packs. The default excludes common `.env` files. Exclusions are metadata only: the plugin does
not copy excluded content into `.sdd`.

## Locking and atomicity

Read-modify-write mutations acquire a project metadata lock before reading the relevant plan/state. Writes use a
temporary file and atomic replacement. This prevents independent workers from silently losing each other's task
status updates. Lock files are implementation details and are not authoritative state.

Stale-lock recovery checks the recorded process ID before reclaiming an old lock. A lock whose owner is still alive
is allowed to time out rather than being removed underneath a concurrent writer; locks from dead processes can be
reclaimed. Forced reinitialization validates the replacement specification before moving the existing `.sdd/` tree
to its backup and restores it if initial rendering fails, so invalid input or rendering errors cannot displace a usable project. Remote terminal backends require callers to supply
an explicit project root because a host or container working directory may not identify the same project.
