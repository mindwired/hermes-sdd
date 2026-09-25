---
name: sdd-plan
description: Plan one SDD milestone into dependency-aware, context-sized tasks with safe parallel waves. Use after project initialization or when an active milestone needs an executable plan.
license: MIT
compatibility: Hermes Agent with the sdd plugin enabled.
metadata:
  author: hermes-sdd
  version: "0.1.0"
---

# Plan one milestone

A plan is an execution aid, not a substitute for engineering judgment. Detail only the active milestone; preserve later milestones as outcomes and risks.

## Before planning

1. Call `sdd` with `operation="status"`.
2. Read the active milestone, linked requirements, relevant ADRs, and only the source files needed to understand the affected boundaries.
3. Research unfamiliar or volatile technology before fixing the design. Delegate bounded research when it benefits from fresh context; require a concise evidence-backed conclusion rather than a transcript.
4. Resolve load-bearing unknowns. Leave reversible choices to the implementing task.

## Task design

Each task should:

- produce one coherent, reviewable result;
- fit comfortably in a fresh agent context;
- name its objective and measurable acceptance criteria;
- list dependencies by task id;
- list a conservative `file_scope` so the scheduler can prevent conflicting parallel edits;
- link requirements and ADRs that directly constrain it;
- link any milestone exit criteria it will implement or verify with `exit_criteria_ids`;
- identify risk and a suitable role (`architect`, `builder`, `tester`, `reviewer`, `security`, `data`, etc.).

Prefer vertical slices. Avoid tasks such as “implement backend” or “finish frontend.” Avoid microtasks that force the agent to repeatedly reload the same context.

## Interfaces and parallelism

When interfaces are not stable, plan contract/schema/boundary work first and set `interfaces_stable` false on the milestone. The plugin will serialize implementation tasks until stability is explicit. After interfaces are stable, call `update_milestone` with `interfaces_stable: true`; independent tasks with non-overlapping file scopes can then run in one wave.

Parallel work is safe only when dependencies and edit scopes are independent. Never use parallelism merely to reduce wall time.

## Save the plan

```json
{"operation":"set_plan","root":"<repo>","payload":{"milestone_id":"M001","context":"# Decisions and implementation context\n\nOnly facts every executor needs.","planning_notes":"Key sequencing rationale.","tasks":[{"id":"M001-T001","title":"Create executable vertical skeleton","objective":"One end-to-end path runs locally and in CI","risk":"high","kind":"implementation","depends_on":[],"acceptance":["command exits successfully","integration test proves the path"],"file_scope":["src/core/**","tests/integration/**","pyproject.toml"],"requirement_ids":["REQ-001"],"decision_ids":["ADR-0001"],"agent_role":"builder"}]}}
```

Then call `operation="next"`. Review the proposed wave. If tasks unexpectedly conflict, correct their scopes or dependencies instead of forcing parallel execution.

## Plan quality checks

A strong plan has no dependency cycles, no orphaned must-have requirement, no unverifiable acceptance criterion, no critical task without explicit risk handling, and no task that requires reading the entire project history. Use `operation="validate"` before execution on deep/program work.

Milestone exit criteria receive stable IDs when created or migrated. Every active criterion must be mapped to at least
one task; finalization later requires successful criterion-linked evidence from a non-skipped linked task. Do not
map criteria to tasks that cannot provide observable verification.

## Output

Summarize the milestone strategy, critical path, safe first wave, major risks, and assumptions. Do not recite every task field unless the user requested it.
