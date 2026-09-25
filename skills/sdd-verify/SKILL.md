---
name: sdd-verify
description: Verify an SDD milestone against requirements, acceptance criteria, architecture, tests, and operational evidence before finalization.
license: MIT
compatibility: Hermes Agent with the sdd plugin enabled and project verification tools available.
metadata:
  author: hermes-sdd
  version: "0.1.0"
---

# Verify and finalize a milestone

Verification asks whether the intended outcome works, not whether the task list was checked off.

## Verify in layers

1. Call `sdd(operation="status")` and `sdd(operation="validate", payload={"record":false})`.
2. Inspect the actual diff and implementation. Confirm no task summary claims work outside the changed code.
3. Map linked requirements and milestone exit criteria to concrete evidence.
4. Run the smallest trustworthy test set first, then broader checks proportional to blast radius:
   - formatting, linting, type checks;
   - unit and integration tests;
   - build/package/startup checks;
   - migrations and rollback behavior;
   - security, concurrency, performance, or failure-path tests where relevant;
   - user-visible/manual verification for interfaces that automated tests do not cover.
5. For a high-risk milestone, use an independent reviewer or fresh-context verifier. Give it the implementation, requirements, and evidence—not the original planner's reasoning.
6. Fix failures as implementation work. Add or reopen tasks when a repair is substantial; do not hide it in the verification narrative.

## Record missing evidence

```json
{"operation":"record_evidence","root":"<repo>","target":"M001-T002","payload":{"type":"integration_test","command":"pnpm test:integration","result":"passed","artifact":"artifacts/integration.xml","requirement_ids":["REQ-002"]}}
```

Evidence is concise metadata; large logs belong in project artifacts or CI.

## Final checks

Do not finalize while:

- any task remains pending, in progress, or blocked;
- validation has an error;
- any active structured milestone exit criterion lacks successful evidence explicitly linked through a non-skipped
  task that also links that criterion. Legacy prose-only criteria must be migrated with `update_milestone` first;
- a must-have requirement lacks successful evidence explicitly linked to it through a non-skipped task that also links the requirement;
- critical behavior relies only on a mocked path;
- a known regression or security issue is deferred without explicit acceptance.

Warnings may remain when they are understood and proportionate. Record material residual risk as an ADR, issue, or future milestone rather than expanding the current milestone indefinitely.

## Finalize

```json
{"operation":"finalize_milestone","root":"<repo>","target":"M001","payload":{"summary":"What shipped, how it was verified, and remaining known limitations."}}
```

The plugin marks the milestone verified, advances to the next planned milestone, or completes the project when none remain.

The core normally rejects finalization when the requested milestone is not active, its plan is empty, any task is nonterminal, or validation reports an error. An explicit escape hatch is available as `options: {"force": true}` for deliberate recovery/administrative override only. Force requires `payload.override_reason`, marks the milestone `overridden` rather than `verified`, and records the override in the event and summary; it is not evidence of successful verification. Do not use force to make an incomplete outcome appear verified. Communicate the unresolved blockers explicitly.

Structured exit-criterion validation proves traceability metadata only, not the truth of user-entered evidence claims.
Do not call a criterion factually proven merely because a task is done or evidence text sounds positive.

## Output

Report delivered outcomes, exact verification evidence, unresolved risks, health score, and next milestone. Avoid a process diary.
