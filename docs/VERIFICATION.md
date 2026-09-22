# Verification report

Date: **September 22, 2026**

## Completed locally

- `uv lock --offline` and `uv sync --locked --offline` with Python 3.13.5.
- Standard-library unit/integration tests: `61` passed, with `2` optional Dashboard tests skipped in the base `uv` environment (`Ran 61 tests`, `OK (skipped=2)`); 61 test methods are present across the suite.
- Isolated Dashboard integration: `2` passed with FastAPI `0.128.2`, HTTPX `0.28.1`, Pydantic `2.12.5`, and Pydantic Core `2.41.5` (latest output: `Ran 2 tests`, `OK`).
- Python AST parsing and isolated bytecode compilation for every Python file.
- JSON parsing for every committed JSON file.
- Node.js syntax checks for Dashboard and Desktop JavaScript.
- Hermes-style package loading with `spec_from_file_location(..., submodule_search_locations=[...])`.
- Native Desktop copy, symlink, idempotency, overwrite protection, freshness, and uninstall tests.
- A clean `file://` Git clone, locked offline environment synchronization, full test suite, and contract verification.
- Deterministic ZIP and tar.gz builds; release contents were inspected (86 entries each, root manifest present, no `__pycache__`) and then removed from the checkout.
- No SQLite `ResourceWarning` under repeated lifecycle and concurrent-worker operations.

The optional Dashboard command is:

```bash
uv run --isolated \
  --with fastapi==0.128.2 --with httpx==0.28.1 \
  --with pydantic==2.12.5 --with pydantic-core==2.41.5 \
  env HERMES_REQUIRE_DASHBOARD_TESTS=1 \
  python -m unittest tests.integration.test_dashboard_api -v
```

## Core behaviors exercised

- Complete project initialization → specification → milestone → plan → execution → evidence → validation → finalization.
- Adaptive complexity modes and context budgets.
- Task dependency cycles, incomplete dependencies, file-scope overlap, and critical-task isolation.
- Start-time safety revalidation against stale clients and already-running work.
- Concurrent non-overlapping task starts without lost plan updates.
- Optimistic plan revisions and targeted task updates.
- Context checkpoints, wildcard source scopes, and changed-file deltas.
- Program-mode evidence requirements and failed/manual evidence handling.
- Future-milestone validation errors isolated from current-milestone finalization.
- Forced initialization backup and recovery behavior.
- Symlink rejection (including checkpoint reads), malformed JSON/JSONL and collection-shape rejection, incomplete-state protection, explicit remote-root handling, process-aware stale-lock recovery, and non-authoritative registry failure handling.
- Compact Hermes tool/command/skill registration.

## Current repository gates

- `uv run python scripts/verify.py` passed.
- `uvx --from ruff==0.16.1 ruff check .` passed.
- `uvx --from ruff==0.16.1 ruff format --check .` passed.
- `git diff --check` passed.
- `hermes plugins validate --json <checkout>` passed; the Hermes security scanner emitted a caution for contextual
  prose in `docs/ANALYSIS.md`, not executable plugin code.
- `hermes plugins doctor sdd` and `hermes sdd doctor --json` passed with zero errors and zero warnings.
- `hermes plugins list --plain` showed the enabled user plugin `sdd` at version `0.1.0`.
- Explicit remote-root smoke coverage passed for built-in `ssh`.
- `scripts/build_release.py --version 0.1.0` passed in scratch output; ZIP/tar.gz archives each contained 86 entries,
  included the root manifest, and contained no `__pycache__` entries.

## Remaining deployment validation

Dashboard integration tests must execute in CI with FastAPI, HTTPX, and a compatible Pydantic wheel; a skipped
optional test is not evidence of adapter coverage. Local environments without those wheels should report the
environment blocker explicitly rather than claim the dashboard path passed.

The repository was also smoke-tested with a disposable Hermes profile and project: plugin doctor, implicit init/status/
validation with a clean local root, and explicit-root read-back passed. `hermes desktop --help` confirmed the documented
`--cwd`, `--skip-build`, and `--force-build` launch paths. Graphical Dashboard/Desktop interaction remains
a manual gate because native Electron capture and plugin inventory are unavailable in the current Wayland session.
Run the smoke test in `HANDOFF.md` against the exact Hermes release and profile that will be used before creating
`v0.1.0`.
