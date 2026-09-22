# Operations and recovery

## Normal operation

Use `status` and `next` as compact orientation calls. Create context packs for substantial tasks rather than
loading every SDD artifact. Checkpoint before work that may span a subagent, context reset, or long tool sequence.

A returned safe wave is an upper bound. Serial execution is always acceptable when workers would compete for
human attention, infrastructure, or a shared semantic boundary not captured by file paths.

## Validation

```bash
hermes sdd validate
```

Validation checks state structure, requirement links, task DAGs, evidence, milestone readiness, and project
traceability. It does not prove the implementation works; repository tests and operational checks remain
necessary.

For a standalone CLI invocation, pass `--root`/`-C` when the active Hermes working directory is not the intended
repository. Remote terminal backends (`ssh`, Docker, Modal, Daytona, Vercel Sandbox, and Singularity) require an
explicit project root; they do not infer one from a potentially host-local working directory.

## Interrupted session

1. Inspect `git status`, recent commits, processes, and test results.
2. Run `hermes sdd status` and `hermes sdd validate --no-record`.
3. Compare the last checkpoint with current files.
4. Reconcile every `in_progress` task against actual code and evidence.
5. Keep, reopen, block, or reset task status based on evidence.
6. Request a new safe wave and context pack.

Do not regenerate all specifications. Preserve decisions that remain true and update only stale facts.

## Concurrent workers

The core rejects task starts with incomplete dependencies, an inactive milestone, unstable interfaces where the
mode forbids parallelism, critical-task concurrency, or overlap with running task scopes. This check happens when
a task starts, not only when `next` was computed, so stale clients cannot bypass it.

File scopes are intentionally conservative. They cannot detect semantic conflicts across disjoint files. Encode
those as dependencies or keep interface work serial until stable.

## Stale-plan writes

Use targeted `update_task` and pass `expected_revision` when an agent read the plan before editing it. On a
revision conflict, reload the active plan and reapply only the still-valid change.

## Damaged state

- Parse or schema errors: restore from Git or a known backup, then validate.
- Do not replace malformed JSON/JSONL with `{}` or follow symlinks inside `.sdd/`; the plugin rejects both so the
  canonical state cannot silently drift or write outside the project.
- A project JSON object missing `name`, `mode`, or `status` is malformed; restore it from Git or a known backup rather
  than treating it as a healthy empty project.
- Accidental force initialization: recover the timestamped `.sdd.backup-*` directory.
- Lost UI registry: re-register repository paths; project data is unaffected.
- Removed plugin: reinstall it; `.sdd/` remains usable and inspectable.

If a forced reinitialization input is invalid, no backup is moved and the existing project remains in place. A valid
forced initialization moves the old `.sdd/` tree to a timestamped `.sdd.backup-*` directory before creating the new
state; if initial rendering fails, the old tree is restored and the backup is removed.
