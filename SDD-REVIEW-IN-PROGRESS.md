# Hermes SDD Deep Review — Final Review Report

**Status:** Follow-up adversarial review / implementation in progress per user request. Structured exit-criterion evidence is implemented and final local verification passes: 116 tests pass / 3 optional Dashboard skips, pinned Dashboard API 3/3, repository verifier, Ruff, JS behavior/syntax, and diff checks. Current-tree package artifacts were rebuilt in isolation. Exact pushed-revision plugin lifecycle acceptance, publication, commit/push, and consumer-project integration remain outstanding. Consumer report 147 was created before integration changes; it records that the existing active development symlink must not be replaced until an exact published SHA is available.
**Repository:** `/home/felipe.arantes/Projects/hermes-sdd`
**Branch:** `main` (no changes committed)
**Purpose:** Evidence-backed review of Hermes SDD's real-world usefulness, safety/integrity, product surfaces, and release readiness. Findings distinguish observed defects from design risks and product hypotheses.

> This report covers the current local working tree only. It is not evidence that graphical host integration or any future published release has been deployed or verified.

## Executive summary

The project retains a useful compact architecture: one Agent tool with progressively loaded skills, project-local `.sdd/` authority, and thin CLI/HTTP/Dashboard/Desktop adapters. A read-only local Hermes database census found **20 sessions / 1,694 exact SDD Agent-tool calls** and **45 CLI command-bearing calls across 4 sessions**; slash-command dispatch is not reliably recorded. The observed usage shows both sustained real-project use and repeat friction around discoverability/operation payloads, evidence capture, and plan reconciliation. Counts are observational evidence, not proof of user value or representative product analytics.

Several material defects were reproduced and fixed in the working tree, including must-have requirement proof bypass, misleading forced-finalization state, unbounded status payloads, unsafe release output handling, unexpected Dashboard errors mislabeled/leaked as client errors, and exit criteria lacking machine-checkable proof links. Structured exit criteria now require successful evidence explicitly linked through a non-skipped task that also links the criterion. Follow-up tests found migration edge cases: a retired criterion could remain linked to tasks, JSON boolean `true` was accepted as schema version `1`, and malformed status metadata could raise an unhandled `TypeError`; these are fixed and tested. The final full verification chain passed **116 tests with 3 optional Dashboard skips**, pinned Dashboard API tests passed 3/3, repository verification and Ruff passed, Dashboard JS behavioral/syntax checks passed, and `git diff --cached --check` passed. A previous clean-snapshot archive audit and disposable-profile install/CLI smoke test predate the latest changes.

**Release recommendation:** source-level implementation/tests are currently verified, but no commit or fresh clean-snapshot package/install acceptance exists yet. Do not publish until the exact final revision is committed and passes a disposable-profile plugin lifecycle smoke. Host GUI acceptance remains a separate unverified gate.

**Follow-up request (2026-09-24):** re-review this work, finish remaining implementation, keep this report current, commit and push when verified, then superficially audit `~/Projects/agent` and install SDD there using the intended supported workflow. The plugin and consumer repositories are separate ownership boundaries. Read-only inspection found that the consumer already has SDD enabled as a symlink into this checkout, but its committed `deploy/hermes-plugins.yaml` and reconciliation workflow do not manage SDD; no consumer mutation has been made.

## Scope and method

Reviewed repository instructions and public surfaces, actual SDD usage census, state authority and projections, task/milestone transitions, evidence/finalization, context packing/checkpoints, path/symlink protections, CLI/slash/Agent/HTTP/Dashboard/Desktop behavior, docs/skills/schemas, tests, and packaging/release. Investigation evidence is based on local read-only database queries, source/test inspection, disposable fixtures, and executed checks. Behavioral fixes were made test-first where the durable investigation recorded a specific failing reproduction; check the progress notes for exact reproductions and history.

Repository invariants followed: keep root directly installable, `.sdd/` canonical, SQLite registry discovery-only, one compact Agent tool, runtime standard library except optional Dashboard integration, Python 3.11–3.13, and use `uv`. Preserve the pre-existing `/sdd` Desktop-picker help-text change in `hermes_sdd/commands.py`.

## Actual usage and observed friction

A read-only query against `~/.hermes/state.db` matched structured SDD tool results and paired calls by `tool_call_id`; substring matches were rejected as noisy.

- Exact Agent tool census: **1,694** results and paired calls across **20 sessions**, 2026-07-31 to 2026-09-22; result classification: 1,451 `ok:true`, 199 `ok:false`, 44 JSON results without `ok`.
- Broader SDD surface census: 22 deduplicated sessions with Agent and/or CLI evidence. CLI: **45 command-bearing tool calls across 4 sessions**; these are matches, not necessarily successful exits.
- Captured fields do not reliably record actual slash dispatch. A `/sdd` occurrence in assistant prose is not a dispatch event; no claim is made that slash commands were never used.
- A prior sampled census counted about **104.45M input tokens, 8.60M output tokens, 2.71B cached-read tokens, and 13,838 API calls** over those sessions. This describes this local DB/profile snapshot, not product-wide usage, unique model reasoning, or tokens caused by SDD specifically.

Recurring failed results, not automatically defects: 37 `update_task` status attempts, 12 evidence submissions missing required fields, 10 plan replacements rejected because work was active, 9 empty transition statuses, 9 invalid ADR IDs, and 7 finalizations blocked by missing task evidence. These patterns support making operation-specific payload guidance and recovery flows more discoverable while keeping strict validation; they do not support permissive silent reinterpretation of ambiguous fields. Session-level counts/titles and census caveats remain in the progress history captured during the investigation.

## Verified findings and fixes

### High — Must-have requirement could be finalized without proof (fixed)

A disposable standard-mode project with an active must-have requirement linked to a milestone and low-risk task could be marked done and finalized with no evidence; validation reported no blocker and finalization returned `verified` / project `complete`. Validation now requires successful evidence explicitly linked to the requirement, owned by a non-skipped task in that milestone that itself links the requirement. Terminal plans elevate missing proof to an error; task-linked requirements are included in finalization blockers. Wrong/unlinked/taskless/skipped-owner evidence is insufficient. This validates traceability metadata, not truth of user-entered evidence claims.

### High — Forced finalization looked verified and lacked rationale (fixed)

Previously force bypassed blockers but returned normal milestone `verified` and project `complete`. Forced finalization now requires `payload.override_reason`, returns/records `overridden` (not `verified`), persists the reason in summary/event, does not treat overridden milestones as pending during project advancement, and marks project/state `overridden` when there are no remaining milestones. A regression probe then found that creating a new milestone did not reopen project status from `overridden`; it now transitions back to `active`, with a focused regression test. Force remains a deliberate administrative bypass; its exact authority and residual risk should remain visible.

### High — Release builder could delete arbitrary output content (fixed)

Disposable tests reproduced deletion of unrelated marker files and repository contents when `--output` targeted an unsafe location. Output containment and symlink checks now reject unsafe in-repository paths, use the managed `release/` directory for in-repo output, preserve unrelated files, and fail closed on contaminated managed output rather than recursive deletion. External output paths remain caller-managed. Tests also cover tracked/untracked inclusion, staged/unstaged state, deletion/rename and symlink cases.

### Medium — Untracked workspace files could enter release archives (fixed)

The release collector included untracked report/test artifacts. It now derives archive members from Git-tracked paths, rejects tracked modifications/deletions/renames, and excludes untracked files. A historical clean-snapshot build contained 74 entries in each archive, required plugin entrypoints, no pycache/pyc, valid checksum sidecars, and identical ZIP/tar bytes across two runs. This was before the latest current-tree changes; rerun packaging from a new clean snapshot before release.

### Medium — Status was an unbounded project dump / weak action guidance (fixed)

A large observed project had ~259 `.sdd` files, 31 milestones, 59 requirements, and 105 tasks; status previously returned all active milestone tasks. Status now bounds task preview (default 12, configurable maximum 50), supports compact mode, reports counts/truncation and target-scoped blockers, and provides a deterministic recommended next action. `next` explains terminal, blocked, or no-ready-wave conditions. CLI `/sdd status` surfaces the action and blockers, Agent schema names operations and directs to progressively loaded skills, and docs explain compact/status→next/context-pack flow. Snapshot APIs inherit the bounded payload. Literal file search remains unindexed and can be expensive on very large `.sdd/` trees; semantic/indexed search is a future design option, not an immediate defect.

### Medium — Unexpected Dashboard API errors were client errors and exposed exception text (fixed)

A RuntimeError from the snapshot route was returned as HTTP 400 with internal exception text. Expected `ValueError` input failures now map to 400; unexpected exceptions return generic 500 without internal details. Isolated FastAPI tests cover both classes and lifecycle. Optimistic revision conflicts also remain HTTP 400 because the service reports them as `ValueError`; this compatibility limitation is documented for clients rather than inferred from an error string in the router.

### Low — Desktop implementation completion was visually conflated with verification (improved)

Desktop completion now explicitly says implementation complete / verification pending, and done tasks without linked evidence expose a follow-up verification action. The Dashboard completion flow requires explicit confirmation of a successful result, distinguishes implementation from verification, and lets verification be recorded later. These UI changes have behavior/syntax tests but were not rendered in the Hermes host GUI.

### Medium — Must-have requirement links could drift in roadmap projection (fixed)

A disposable test changed roadmap requirement/decision/exit-criteria links without changing canonical milestone metadata. Validation now emits blocking drift findings for those link-bearing projections; descriptive/status drift remains a warning. Regression coverage verifies such drift blocks finalization.

### Medium — Checkpoint file-count bound silently truncated state (fixed)

A checkpoint scope exceeding its cap previously returned a partial set without signaling incompleteness. It now fails clearly at first unique overflow and uses lazy traversal so it does not materialize unbounded candidate lists. Outside-root symlinks and secret exclusions remain tested.

### Medium — Exit criteria could be finalized without criterion-specific evidence (fixed)

A disposable quick project reproduced `validate.ok == true` and `finalize_milestone.status == "verified"` with a prose exit criterion, completed task, and no evidence. Milestones now store schema-v1 structured records with stable IDs (`M001-EC001`), active/retired status, and explicit legacy migration via `update_milestone`. Tasks and successful evidence must both link an active criterion; the evidence must be owned by a non-skipped task in the milestone. Finalization blocks missing proof and unmapped legacy prose criteria; validation rejects unknown/mismatched links. Explicit force remains an audited override, never a verified result. Evidence establishes traceability metadata only, not truth of a claim. Candidate updates cannot erase/reuse IDs or change a criterion's text in place; linked task references must be reconciled before retiring criteria. Roadmap/plan Markdown render criterion IDs. Focused core tests and the full test/check suite are recorded below.

Subsequent adversarial probes reproduced two additional integrity gaps in that fix: callers could mark a criterion retired while tasks still referenced it, or pass JSON `true` as schema version `1` (Python equality treats `True == 1`). Both update paths (`exit_criteria_records` and legacy `exit_criteria` reconciliation) now reject retirement until task links are removed, before writes; schema versions require an actual integer type. Focused regression tests pass. Retired evidence links remain historical and do not satisfy active proof.

A disposable project with an explicitly empty `exit_criteria` list was also validated and finalized successfully as `verified` (no active criterion proof is required, as intended); empty criteria are not mistaken for an unmapped legacy criterion.

### Medium — Consumer repository did not pin its already-installed SDD plugin (open)

The consumer project describes `deploy/hermes-plugins.yaml` as the reproducible source of user-installed plugin revisions and invokes its reconciliation during `just install` / `just update`. That declaration contains only `hermes-lcm`, while the active Hermes profile has `sdd` enabled from `$HOME/.hermes/plugins/sdd`, which is a symlink directly to this editable checkout. Read-only `hermes plugins doctor sdd`, `hermes sdd doctor`, and `status --json --root /home/felipe.arantes/Projects/agent` passed against that checkout; status identifies the project and active milestone M023. `validate --no-record` reports 12 errors and 98 warnings, predominantly historic evidence/requirement linkage and legacy prose-only criteria, and exits nonzero as expected; no SDD project data was changed by those reads. The current dirty plugin changes therefore load in the active profile already, but this is a development symlink—not a reproducible/published pin. Adding SDD blindly to the reconciler would replace that non-Git symlink target with a detached remote clone and could silently lose the intended local development linkage; choose the desired pin only after the plugin revision is pushed, then use the supported installer/reconciler deliberately. No consumer config or plugin installation path has been changed.

## Residual risks and product recommendations

The plan, execute, verify, and recover skills now explicitly guide criterion IDs, task/evidence linkage, legacy migration, and the distinction between `overridden` and `verified`; agent guidance remains progressively loaded rather than adding another tool surface.

1. **Evidence metadata is not factual verification.** A successful evidence row documents an assertion/observation but does not independently establish that a command ran or that the result is true. Criterion gating closes missing traceability, not independent truth verification.
2. **Large-project UX/value.** Bounded status and task context packs reduce repeated payload, but no controlled token/context experiment establishes that they reduce compaction frequency or improve project outcomes. Measure on representative small and large projects before adding semantic search or more UI breadth.
3. **Interaction design.** Keep one Agent tool and progressive skills unless evidence establishes that surface is inadequate. Improve per-operation examples, common failure recovery, and read/search/update/delete affordances through focused changes and observed usage. Avoid expanding schemas into duplicate tools or permissive aliases without a clear compatibility contract.
4. **Host acceptance.** Graphical Dashboard/Desktop rendering, accessibility/long-content layout, real clipboard behavior, and GUI uninstall were not verified. Syntax and mocked/isolated adapter tests do not establish host SDK compatibility.
5. **Publication gate.** An isolated clean tracked-file snapshot with all 18 current tracked modifications copied in, and untracked report/test files excluded, passed repository verification and the release builder. Both archives had 74 matching members, required root entrypoints, and valid checksums: ZIP `c5fcd7c5f4f24777f8f9a37e69bc190b56eadbf80de662194edb179495ef3a5c`; tar.gz `96d77408a231083f22eca8576e5ca9ce70a476ebfb3542acd4b1c9c5aa573779`. This verifies packaging of the current tree, not GitHub publication or a final pushed-revision install. Still run the disposable-profile lifecycle smoke after commit/push.
6. **Consumer pin is not reconciled.** The active profile uses a symlink to the local checkout, but the consumer's managed plugin list omits SDD. Resolve after publication whether the consumer should pin an exact remote SHA and replace the dev symlink, or whether local development should remain intentionally unmanaged; then follow the consumer's report-first/scoped-change workflow. Its dirty worktree, including existing `.sdd/`, was not modified.

## Verification performed on current worktree

- `uv run python -m unittest discover -s tests -v` — **116 tests passed; 3 skipped**, all optional FastAPI/HTTPX Dashboard tests in the base environment. Includes criterion-proof, failed/missing/mismatched evidence, legacy migration, linked-retirement refusal, malformed schema/status, stable-ID, and render-output probes. This run generated test archives in isolated temporary workspaces; this is not the clean-snapshot release audit.
- `uv run python -m unittest tests.unit.test_core -v` — **75/75 passed** after structured criterion-gate and milestone-scoping changes (before two additional regression tests were added).
- Isolated pinned Dashboard API suite passed **3/3** after the final 116-test chain (`fastapi==0.128.2`, `httpx==0.28.1`, `pydantic==2.12.5`, `pydantic-core==2.41.5`, `HERMES_REQUIRE_DASHBOARD_TESTS=1`).
- `uv run python scripts/verify.py --require-node` — passed (`Repository verification passed (Hermes SDD 0.1.0).`).
- `uvx --from ruff==0.16.1 ruff check .` — passed.
- `uvx --from ruff==0.16.1 ruff format --check .` — passed; 52 files already formatted.
- `node tests/js/test_dashboard_completion.js` — passed.
- `node --check dashboard/dist/index.js` and `node --check desktop/plugin.js` — passed.
- `git diff --cached --check` passed after the final staged review; no unstaged SDD changes remain.
- Current isolated tracked-file release snapshot: `scripts/build_release.py` completed successfully in a temporary clean Git repository built from all tracked current bytes; the working tree was not changed. ZIP and tar each contained 74 members, matching content paths, expected root entrypoints, and valid checksum sidecars; hashes are recorded under finding 5 above. Untracked report/tests were excluded by the tracked-file snapshot. This is release-builder acceptance for this source tree, not a tag, publication, or plugin-manager install.
- Historical (pre-latest-change) checks: a disposable Hermes profile installed/doctor/init/status/validate smoke passed. This was not rerun after all current changes.

## Worktree and closeout status

All changes remain uncommitted. The report is untracked by design. The pre-existing Desktop-picker help edit in `hermes_sdd/commands.py` was preserved. Consumer report 147 is also untracked and records the intended later pin. Do not claim a clean worktree. Final source-level verification and isolated archive generation pass, but host GUI acceptance, exact-final-revision plugin lifecycle install, commit/push, and SDD pin reconciliation in the consumer project remain outstanding.
