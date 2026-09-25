# Hermes SDD Deep Review — Final Review Report

**Status:** SDD implementation commit `bd1018f` is pushed (116 tests and pinned Dashboard API tests pass); review changes are pushed and `main` is clean/synchronized at `61dc451`. The implementation SHA passed disposable Hermes profile doctor, CLI init/status, and Desktop-adapter install checks. Consumer integration is pushed; consumer `just check` passed 254 tests, and the active profile reconciles to the pinned SDD Git checkout. The requested plugin pin/install is complete. Separate limitations: GUI rendering/accessibility/clipboard acceptance and historical validation findings in consumer `.sdd/`; gateway messaging/HA adapters are disabled by profile policy and outside the pin scope.
**Repository:** `/home/felipe.arantes/Projects/hermes-sdd`
**Branch:** `main` clean and synchronized with `origin/main`; implementation commit `bd1018fe8cea44dac4a383080b194e7eb24a1c9c` is pushed.
**Purpose:** Evidence-backed review of Hermes SDD's real-world usefulness, safety/integrity, product surfaces, and release readiness. Findings distinguish observed defects from design risks and product hypotheses.

> This report covers the current local working tree only. It is not evidence that graphical host integration or any future published release has been deployed or verified.

## Executive summary

The project retains a useful compact architecture: one Agent tool with progressively loaded skills, project-local `.sdd/` authority, and thin CLI/HTTP/Dashboard/Desktop adapters. A read-only local Hermes database census found **20 sessions / 1,694 exact SDD Agent-tool calls** and **45 CLI command-bearing calls across 4 sessions**; slash-command dispatch is not reliably recorded. The observed usage shows both sustained real-project use and repeat friction around discoverability/operation payloads, evidence capture, and plan reconciliation. Counts are observational evidence, not proof of user value or representative product analytics.

|Several material defects were reproduced and fixed, including must-have requirement proof bypass, misleading forced-finalization state, unbounded status payloads, unsafe release output handling, Dashboard error leakage/classification, and exit criteria lacking machine-checkable proof links. Structured criteria now require successful evidence linked through a non-skipped task that also links the criterion. Further probes fixed retirement while tasks still referenced criteria, JSON `true` treated as schema version 1, and malformed status metadata causing unhandled `TypeError`. Implementation commit `bd1018f` is pushed to GitHub; subsequent source-report corrections are also pushed through `5c1856f`. The implementation verification chain passed **116 tests with 3 optional Dashboard skips**, pinned Dashboard API tests passed 3/3, repository verification/Ruff/JS checks passed, and a tracked-source clean snapshot produced two matching 74-member archives with verified checksums. Installing the implementation SHA in a disposable Hermes home, running CLI init/status on disposable state, `hermes sdd doctor`, and installing the Desktop adapter all passed. No host GUI rendering test was available.

The application static scan labeled ordinary test/CI subprocess use and test paths as caution findings; install was first blocked and then deliberately continued only inside the disposable Hermes home with `--force`. This did not disable scanning globally or alter the active profile. Preserve the distinction between static matches, actual runtime behavior, and GUI acceptance.

**Release recommendation:** source implementation is pushed, verified, and the exact revision passes disposable-profile install/runtime smoke. A tracked-source archive build passed. GUI acceptance for Dashboard/Desktop is not verified. Gateway adapters remain intentionally disabled and outside this plugin-pin scope.

**Follow-up request (2026-09-24):** re-review, implement fixes, commit/push, then audit and install in `~/Projects/agent`. Source implementation commit `bd1018f` and subsequent review-report commits are pushed. Consumer integration and Report 147 are pushed. Existing consumer `.sdd/` state was preserved.

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

### Medium — Consumer repository did not pin its already-installed SDD plugin (fixed)

The consumer project describes `deploy/hermes-plugins.yaml` as the reproducible source of user-installed plugin revisions and invokes its reconciler during `just install` / `just update`. It initially pinned only `hermes-lcm`, while the active Hermes profile had SDD as a development symlink into this checkout. After pushing the verified source SHA, the consumer pin and test include SDD `bd1018fe8cea44dac4a383080b194e7eb24a1c9c`; reconciliation replaced the development symlink with a detached Git checkout at the pin. `just plugins-plan` reports LCM and SDD current/enabled, configure/check pass, and profile revision/origin, plugin doctor, SDD doctor, and project status read back. Consumer `.sdd/` was not changed. `validate --no-record` still reports 12 errors and 98 warnings from historical requirement proof and legacy prose-only criteria; that is a separate project-state issue, not an install failure. Consumer commits `b994aa3`, `0d0c62d`, `a854303`, `d6856af`, and `aa4cb59` are pushed; unrelated dirty paths were left untouched. Report 147 is complete for the scoped SDD pin/install. The active gateway is cron-only because the messaging platform plugins remain disabled by profile policy; no live platform/SDD schema registration is claimed.

## Residual risks and product recommendations

The plan, execute, verify, and recover skills now explicitly guide criterion IDs, task/evidence linkage, legacy migration, and the distinction between `overridden` and `verified`; agent guidance remains progressively loaded rather than adding another tool surface.

1. **Evidence metadata is not factual verification.** A successful evidence row documents an assertion/observation but does not independently establish that a command ran or that the result is true. Criterion gating closes missing traceability, not independent truth verification.
2. **Large-project UX/value.** Bounded status and task context packs reduce repeated payload, but no controlled token/context experiment establishes that they reduce compaction frequency or improve project outcomes. Measure on representative small and large projects before adding semantic search or more UI breadth.
3. **Interaction design.** Keep one Agent tool and progressive skills unless evidence establishes that surface is inadequate. Improve per-operation examples, common failure recovery, and read/search/update/delete affordances through focused changes and observed usage. Avoid expanding schemas into duplicate tools or permissive aliases without a clear compatibility contract.
4. **Host acceptance.** Graphical Dashboard/Desktop rendering, accessibility/long-content layout, real clipboard behavior, and GUI uninstall were not verified. Syntax and mocked/isolated adapter tests do not establish host SDK compatibility.
5. **Consumer SDD historical state.** The new pin makes the stricter requirement/exit-criterion policy active for the consumer. Existing state reports 12 errors/98 warnings; resolve incrementally with its project owners, do not fabricate evidence or auto-migrate prose as proof.
6. **Gateway adapter availability (out of scope for plugin pin).** Platform adapters are disabled by the active profile. Gateway runs for cron only; enabling external messaging/HA integrations requires separate operator intent. Do not report live gateway SDD registration based on CLI/profile doctor checks alone.

## Verification performed on current worktree

- `uv run python -m unittest discover -s tests -v` — **116 tests passed; 3 skipped**, all optional FastAPI/HTTPX Dashboard tests in the base environment. Includes criterion-proof, failed/missing/mismatched evidence, legacy migration, linked-retirement refusal, malformed schema/status, stable-ID, and render-output probes.
- `uv run python -m unittest tests.unit.test_core -v` — **75/75 passed** after structured criterion-gate and milestone-scoping changes (before two additional regression tests were added).
- Isolated pinned Dashboard API suite passed **3/3** after the final 116-test chain (`fastapi==0.128.2`, `httpx==0.28.1`, `pydantic==2.12.5`, `pydantic-core==2.41.5`, `HERMES_REQUIRE_DASHBOARD_TESTS=1`).
- `uv run python scripts/verify.py --require-node` — passed (`Repository verification passed (Hermes SDD 0.1.0).`).
- `uvx --from ruff==0.16.1 ruff check .` — passed.
- `uvx --from ruff==0.16.1 ruff format --check .` — passed; 52 files already formatted.
- `node tests/js/test_dashboard_completion.js` — passed.
- `node --check dashboard/dist/index.js` and `node --check desktop/plugin.js` — passed.
- `git show bd1018f --check` — passed on implementation commit; later report-only commits are pushed and clean.
- Isolated tracked-file archive build — completed in a temporary clean Git snapshot with 74 matching ZIP/tar members, plugin entrypoints and checksum sidecars verified (ZIP SHA-256 `c5fcd7c5f4f24777f8f9a37e69bc190b56eadbf80de662194edb179495ef3a5c`; tar.gz SHA-256 `96d77408a231083f22eca8576e5ca9ce70a476ebfb3542acd4b1c9c5aa573779`).
- Exact pushed-SHA disposable install — security scan produced caution due to broad static matches; initial install was blocked, then explicitly continued using Hermes `--force` only in a disposable `HERMES_HOME`. Installed revision read back as `bd1018f`; plugin and SDD doctor passed; CLI initialized a disposable project and status returned `ok`; Desktop adapter installation and doctor passed. No production profile or SDD project state was mutated by this smoke.
- Consumer repo: `rtk uv run pytest tests/test_reconcile_hermes_plugins.py -q -o addopts=` — **5 passed**; `rtk just check` — **254 passed** with configuration alignment, Ruff, format, mypy and test suites passing.
- Active profile: initial `just plugins-plan` reported SDD update from docs-only source commit `3fca109`; configure replaced development symlink with detached Git checkout at pin; `just plugins-check` passed and subsequent plan is current/enabled. Plugin and SDD doctor pass; Hermes lists SDD, LCM, and RTK enabled. Consumer status succeeds. `validate --no-record` remains nonzero with 12 errors / 98 warnings from historical SDD state.
- Active gateway after restart: user unit active, MainPID `3149242`, ExecMainStatus `0`; service definition was refreshed. Journal records `No adapter available for telegram`, `whatsapp`, and `homeassistant`, and `No adapter could be created for any of the 3 configured platform(s). Gateway will continue for cron job execution.` Thus restart was successful but live messaging/SDD schema registration was not verified.

## Worktree and closeout status

The SDD source changes and review-report corrections are pushed. Consumer integration commit `b994aa3` contains the plugin pin/test/docs/report; report handoff updates are in `0d0c62d`, `a854303`, `d6856af`, and `aa4cb59`. Branches are synchronized. Report 147 is complete for the SDD pin/install. The active gateway is cron-only because messaging platform plugins remain disabled by profile policy; this is a separate, deliberately deferred capability and not a blocker for the SDD CLI/plugin installation. Pre-existing consumer `.sdd/`, service, security, model, documentation, and other report work remains dirty and was not committed. Graphical host GUI acceptance and historical SDD state remediation remain outstanding.
