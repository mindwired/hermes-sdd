# Hermes SDD Plugin Investigation Report

**Status:** Core investigation complete; state-integrity hardening verified; source changes ready for publication; native UI deployment gate remains
**Started:** 2026-09-22 03:02 -03
**Last updated:** 2026-09-22 14:30 -03
**Repository:** `/home/felipe.arantes/Projects/hermes-sdd`
**Installed plugin:** `/home/felipe.arantes/.hermes/plugins/sdd`
**Live Hermes:** `0.21.4` (`439eb039`)
**Plugin:** `sdd` `0.1.0`

> Durable handoff for the ongoing investigation. Update this file after each major probe, test, or conclusion. It distinguishes verified facts, hypotheses, blockers, and unverified surfaces so context compaction does not erase the investigation state.

## Executive conclusion so far

The SDD plugin is **not globally dead or undiscovered**. Its repository, installed copy, Agent registration, CLI, skills, Dashboard backend, and Desktop adapter files are present and loadable. The strongest user-visible failure is **Hermes project-context/root selection**, not plugin registration: the active Hermes process exports `TERMINAL_CWD=/home/felipe.arantes/Projects/agent`, so implicit SDD calls target that project even when repository investigation is occurring from `/home/felipe.arantes/Projects/hermes-sdd`.

A second confirmed defect was stale plugin documentation/schema text: the SDD tool description said `plugin:sdd-*`, but current Hermes resolves these skills as `sdd:sdd-*`. The repository fix, active-profile synchronization, live registry read-back, and regression test are complete.

Native Desktop visual verification remains incomplete. The Desktop log shows the renderer reached `#/sdd` and only reports benign `ResizeObserver` warnings around that route, but no capturable Electron window is available in the current Wayland/X11 environment. The running Desktop has additional unrelated/runtime noise: repeated backend churn, an old stored route/session failure, and LiteLLM model/rate-limit/config issues. Do not attribute those to SDD without a clean isolated Desktop run.

## Verified repository and installation state

- Git branch is `main`, aligned with `origin/main` at the investigation baseline.
- The worktree is now intentionally dirty with the verified fix, installer hardening, and durable report:
  - `hermes_sdd/schemas.py`
  - `tests/integration/test_registration.py`
  - `scripts/install-dev.sh`
  - `scripts/install-dev.ps1`
  - `docs/INSTALLATION.md`
  - `tests/integration/test_repository.py`
  - `docs/SDD_PLUGIN_INVESTIGATION.md`
- HEAD: `c2c96e37e6c4928cadbac1850ef520b8a33ad258` — `fix: harden SDD state integrity and verification`.
- The repository checkout contains the namespace fix, and the active installed path at `/home/felipe.arantes/.hermes/plugins/sdd` symlinks to this checkout. The previous byte-identical pre-fix copy is preserved outside the discovery root under `/home/felipe.arantes/.hermes/plugin-backups/sdd/`.
- Installed plugin is enabled and recognized as a Git plugin.
- Desktop adapter installation is a symlink and current:
  - source: `/home/felipe.arantes/.hermes/plugins/sdd/desktop/plugin.js`
  - target: `/home/felipe.arantes/.hermes/desktop-plugins/sdd/plugin.js`
  - SHA-256: `025a92ed0f78116b2d01ecd93204d105f221f698789c54769be66a59e2b2d437`
- `hermes sdd doctor --json` reports `ok: true`, zero errors, zero warnings.
- `hermes plugins doctor sdd` reports runtime discovery, manifest parsing, import, and registration passed; registrations are `1 tool(s), 0 hook(s)`.
- Hermes tool listing includes enabled `sdd`.

## Verified Agent/plugin contract

- Root loader and manifest remain in the repository root as required.
- Registration implementation registers one compact `sdd` tool, slash commands, CLI command, and bundled skills.
- Live plugin manager reports `sdd` enabled with:
  - tools: `1`
  - hooks: `0`
  - commands: `4`
  - load error: none
- Live plugin manager reports the five skills under the `sdd` namespace:
  - `sdd:sdd-start`
  - `sdd:sdd-plan`
  - `sdd:sdd-execute`
  - `sdd:sdd-verify`
  - `sdd:sdd-recover`
- `skill_view(name="sdd:sdd-start")` and `skill_view(name="sdd:sdd-verify")` succeed.
- `skill_view(name="plugin:sdd-start")` and `skill_view(name="plugin:sdd-verify")` fail with `Skill not found`.
- The stale wording was in `hermes_sdd/schemas.py:10-11`; it is now fixed to `sdd:sdd-*` and a registration regression test rejects `plugin:sdd-`.
- Current Hermes source confirms `PluginContext.register_skill()` derives `<plugin_name>:<name>`, and the live registry confirms `sdd:`.

## Historical tests and static checks

These earlier runs are preserved as evidence; the current hardening results appear in `Adversarial hardening applied and verified` below.

```text
/home/felipe.arantes/.hermes/hermes-agent/venv/bin/python -m unittest discover -s tests -v
Ran 37 tests in 7.538s
OK

uv run python scripts/verify.py
Repository verification passed (Hermes SDD 0.1.0).

uvx --from ruff==0.16.1 ruff check .
All checks passed!

uvx --from ruff==0.16.1 ruff format --check .
49 files already formatted
```

The historical full suite ran in Hermes' live Python environment containing FastAPI/HTTPX, so both Dashboard integration tests executed rather than being skipped.

Historical post-fix verification:

```text
/home/felipe.arantes/.hermes/hermes-agent/venv/bin/python -m unittest discover -s tests -v
Ran 37 tests in 6.509s
OK

uv run python -m unittest discover -s tests -v
Ran 37 tests in 6.518s
OK (skipped=2)

uv run python scripts/verify.py
Repository verification passed (Hermes SDD 0.1.0).

uvx --from ruff==0.16.1 ruff check .
All checks passed!

uvx --from ruff==0.16.1 ruff format --check .
50 files already formatted

git diff --check
passed
```

The historical `uv` project environment lacked optional FastAPI/HTTPX and skipped two Dashboard tests; the current isolated optional-dependency run is recorded in the hardening section below.

Post-fix disposable-profile smoke test (valid run, explicit root) also passed:

- temporary Hermes home with only the symlinked repository plugin;
- plugin doctor passed with `1 tool(s), 0 hook(s)`;
- live plugin manager exposed all five `sdd:sdd-*` skills;
- `init`, `status`, and `validate --no-record` against a disposable root returned `ok: true`; validation score was `100` with no findings;
- temporary home/project were removed afterward.

One earlier smoke command was invalid evidence because its shell cwd was the repository rather than the disposable project; it created only a temporary `.sdd/` directory in the checkout, which was immediately removed and verified absent. No project state remains in the repository.

## Verified root/context behavior

Current shell/process state:

```text
process cwd         /home/felipe.arantes/Projects/hermes-sdd
TERMINAL_CWD       /home/felipe.arantes/Projects/agent
HERMES_HOME        /home/felipe.arantes/.hermes
TERMINAL_ENV       local
HERMES_DESKTOP_CWD /home/felipe.arantes/Projects/agent
```

The SDD resolver intentionally does:

```python
raw = root or os.getenv("TERMINAL_CWD") or os.getcwd()
```

in `hermes_sdd/storage.py:24-31`.

Observed live behavior:

- `hermes sdd status --json` succeeds against `/home/felipe.arantes/Projects/agent`.
- `env -u TERMINAL_CWD -u HERMES_DESKTOP_CWD hermes sdd status --json` resolves to `/home/felipe.arantes/Projects/hermes-sdd` and fails because that checkout is not initialized as an SDD project. This failure is expected for the plugin repository itself.
- `hermes sdd status --json --root /home/felipe.arantes/Projects/hermes-sdd` fails with the same expected `No SDD project` error.
- `hermes sdd status --json --root /home/felipe.arantes/Projects/agent` succeeds.
- The SDD CLI accepts explicit roots in all tested forms:
  - `hermes sdd --json --root <project> status`
  - `hermes sdd status --json --root <project>`
  - `hermes sdd status --json -C <project>`
  Each returned the disposable project's root and healthy status.


- `agent/runtime_cwd.py` resolves configured/session cwd before process cwd.
- `tools/terminal_scope.py` provides per-profile terminal policy in multiplexed surfaces.
- Desktop explicitly spawns its backend with `TERMINAL_CWD=<resolved Desktop project cwd>`.
- Desktop `resolveHermesCwd()` prioritizes configured default project directory, then `HERMES_DESKTOP_CWD`.
- The active Desktop backend has `TERMINAL_CWD=/home/felipe.arantes/Projects/agent` and cwd `/home/felipe.arantes/Projects/agent`.

**CLI/session distinction confirmed:** Hermes `--in DIR` is a top-level chat/session startup option. Running `hermes --in <disposable-project> sdd status --json` still resolved to the inherited active `TERMINAL_CWD=/home/felipe.arantes/Projects/agent`; with the env unset it resolved to the shell cwd `/home/felipe.arantes/Projects/hermes-sdd`. Therefore `--in` is not a valid way to retarget the standalone SDD CLI command. The SDD CLI must receive `--root/-C` on `hermes sdd` or its subcommand; interactive chat/Desktop should be started with `hermes --in DIR` or `--cwd DIR` respectively.

## Verified Dashboard backend and web assets

Previously completed isolated authenticated Dashboard checks:

- `/api/plugins/sdd/health` → HTTP 200, `{"ok":true,"plugin":"sdd","version":"0.1.0"}`.
- `/api/plugins/sdd/sources` → HTTP 200.
- `/api/plugins/sdd/snapshot?root=/home/felipe.arantes/Projects/agent` → HTTP 200.
- `/api/plugins/sdd/snapshot?root=/home/felipe.arantes/Projects/hermes-sdd` → HTTP 400 with the expected uninitialized-project message.
- `/api/plugins/sdd/doctor?root=/home/felipe.arantes/Projects/agent` → HTTP 200, zero errors/warnings.
- Invalid operation → HTTP 400 with typed `ValueError` and no traceback leak.
- Unauthenticated plugin API → HTTP 401.
- `/api/dashboard/plugins` lists `sdd` as an active user plugin.
- `/dashboard-plugins/sdd/manifest.json` → HTTP 200.
- `/dashboard-plugins/sdd/dist/index.js` → HTTP 200, 18,801 bytes.
- `/dashboard-plugins/sdd/dist/style.css` → HTTP 200, 3,886 bytes.
- Static asset traversal/backend-source probes were blocked as expected.

The browser harness loaded the web shell but showed `Desktop IPC bridge is unavailable`; this is expected for ordinary Chromium and is not evidence against the native Desktop plugin. The web shell did not expose native `window.hermesDesktop` or native plugin globals.

## Packaged Desktop artifact inspection (completed)

The packaged `app.asar` was extracted read-only and inspected, then the extraction tree was removed. The current release does include the native runtime-plugin machinery:

- `__HERMES_PLUGIN_SDK__` appears in `dist/assets/sdk-CZpw2_w0.js`.
- `desktopPluginsRoot` appears in the packaged preload and renderer bundles.
- `Reload desktop plugins` appears in `dist/assets/index-AnJQ5OA-.js`.
- The bundled runtime loader includes the app-level Desktop plugin scan and live SDK shim code.

The SDD adapter's own strings (`/sdd`, `Spec-driven development`) do not appear as literal strings in the packaged core bundle, which is expected because SDD is a disk plugin loaded from `/home/felipe.arantes/.hermes/desktop-plugins/sdd/plugin.js`. The artifact therefore is not an old pre-plugin Desktop build; visual failure remains an environment/window-observability or runtime-state issue, not missing core loader support.


The existing Desktop backend is listening on `127.0.0.1:42859` with PID `2266962`. Its environment confirms:

```text
HERMES_HOME=/home/felipe.arantes/.hermes
TERMINAL_CWD=/home/felipe.arantes/Projects/agent
HERMES_DESKTOP_CWD=/home/felipe.arantes/Projects/agent
HERMES_DESKTOP=1
```

Using the token already injected into that process (never printed), read-only requests succeeded:

- `GET /api/plugins/sdd/health` → HTTP 200.
- `GET /api/plugins/sdd/doctor?root=/home/felipe.arantes/Projects/agent` → HTTP 200.
- `GET /api/plugins/sdd/snapshot?root=/home/felipe.arantes/Projects/agent` → HTTP 200.
- `GET /api/plugins/sdd/snapshot?root=/home/felipe.arantes/Projects/hermes-sdd` → HTTP 400 with the expected uninitialized-project message.
- The same endpoint without a token → HTTP 401.

**Conclusion:** the native Desktop-spawned backend and SDD API are live and correctly rooted at the Desktop project. This verifies the backend path independently of visual Electron capture; it does not prove the native SDD route rendered successfully.


Source-side native Desktop architecture is verified:

- Plain ESM adapter imports only `@hermes/plugin-sdk`, `react`, and `react/jsx-runtime`.
- Runtime loader scans the app-level `<HERMES_HOME>/desktop-plugins/<name>/plugin.js` door.
- It rewrites SDK imports to live shims, validates the default plugin, registers contributions, watches/hot-reloads files, and exposes a `Reload desktop plugins` palette action.
- SDD adapter registers `/sdd`, a sidebar item, status-bar item, and palette command.
- Native backend calls are namespace-scoped through `ctx.rest('/...')`.

Running packaged Desktop facts:

- Electron process: `/home/felipe.arantes/.hermes/hermes-agent/apps/desktop/release/linux-unpacked/Hermes`.
- Packaged release stamp: commit `439eb0395eed5025139ee917526f31e2d161699e`, built `2026-09-22T03:50:41.548Z`, clean.
- Desktop log contains repeated renderer entries with URL `.../index.html#/sdd` and only `ResizeObserver loop completed with undelivered notifications` around the route.
- No SDD-specific load error, unsupported-import error, or plugin registration exception was found in `desktop.log`.
- `computer_use list_windows` sees only `xwaylandvideobridge`; no capturable Hermes window is exposed through the current desktop bridge.
- X11 root client list also only exposes the bridge window. The session is Wayland/KDE and the Electron window is not available to current capture tools.

Known unrelated Desktop/runtime noise:

- Desktop log shows `renderer process gone reason=killed exitCode=9` once.
- Desktop log shows repeated backend start/stop churn and socket hangup after long/rate-limited interactions.
- Desktop log includes a stored-session error `sqlite3.OperationalError: no such table: system_prompts`.
- Desktop log includes a config parse warning at one point (`config.yaml` lines 317-318), although current `hermes config check` succeeds and the live config loads.
- Desktop log includes model-not-supported, OpenRouter rate-limit, LiteLLM prompt-cache-key-too-long, and usage-limit errors.
- These are Hermes/runtime/provider issues and should not be attributed to SDD without a clean isolated Desktop test.

## Current hypotheses (ranked)

1. **Most likely user symptom:** Hermes is rooted at `/home/felipe.arantes/Projects/agent`; SDD appears broken when invoked from another checkout because implicit root follows active Hermes cwd. Supported by live environment and resolver behavior.
2. **Fixed documentation/interface mismatch:** the tool schema previously said `plugin:sdd-*`, while current Hermes requires `sdd:sdd-*`. The repository and active installation now document the qualified `sdd:` form, registration regression coverage rejects `plugin:sdd-` wording, and a live Hermes-runtime registry read-back confirms the loaded `sdd` tool description contains the four `sdd:sdd-*` names and no obsolete namespace.
3. **Possible stale/racy Desktop runtime state:** the current Desktop process has provider/session/backend errors and cannot be captured. The SDD route was reached, but successful visual rendering and native plugin inventory are not independently proven.
4. **Low likelihood:** installed plugin corruption or missing registration. Repository/installed hashes, plugin doctor, live manager, and API probes contradict this.

## Verified active-profile refresh and live Agent read-back

At the user's direction, the active Agent/Dashboard plugin installation was synchronized through the repository's local-development installer. The installer now points `/home/felipe.arantes/.hermes/plugins/sdd` at `/home/felipe.arantes/Projects/hermes-sdd`; the previous stale copy was preserved at `/home/felipe.arantes/.hermes/plugin-backups/sdd/sdd.backup-20260922-100024`, outside the plugin discovery root. The Desktop adapter remains a current symlink to the repository source with matching SHA-256 `025a92ed0f78116b2d01ecd93204d105f221f698789c54769be66a59e2b2d437`.

The first local-development refresh exposed a second concrete defect: the old installer placed its backup directory directly under `/home/felipe.arantes/.hermes/plugins/`, where Hermes correctly scanned it as another manifest. Because both copies declared `name: sdd`, the stale backup could win discovery; `hermes sdd doctor --json` consequently reported the backup path as `plugin_root`. Moving that preserved backup outside the discovery root immediately restored the repository checkout as the loaded plugin root. The installer and documentation now enforce this boundary for future refreshes.

The gateway was restarted successfully at `2026-09-22 10:02:16 -03` (PID `4183542`) and restarted once more for final read-back at `2026-09-22 10:14:32 -03` (PID `70968` at that time). Post-refresh checks passed:

- `hermes plugins doctor sdd`: runtime discovery, manifest parsing, import, and registration passed; `1 tool(s), 0 hook(s)`.
- `hermes sdd doctor --json`: `ok: true`, plugin root is the repository checkout, zero errors/warnings.
- A Hermes-runtime Python probe forced plugin discovery and read the live tool registry: `sdd_enabled=True`, `sdd_error=None`, `sdd_tools=['sdd']`; description contained `sdd:sdd-start`, `sdd:sdd-plan`, `sdd:sdd-execute`, and `sdd:sdd-verify`, with `obsolete=False` for `plugin:sdd-`.
- `skill_view("sdd:sdd-start")` and `skill_view("sdd:sdd-verify")` succeed; the obsolete `plugin:sdd-start` and `plugin:sdd-verify` forms fail as expected.
- Gateway logs show `capability_check plugin=sdd` and successful plugin discovery; no SDD load error was emitted.

Final live read-back after the hardening pass still reports `sdd` enabled as a Git plugin, plugin doctor passing with
one tool and zero hooks, and `hermes sdd doctor --json` reporting zero errors and zero warnings with the repository
checkout as `plugin_root`.

The installer was corrected so future backups are stored under `$HERMES_HOME/plugin-backups/sdd/`, not as `sdd.backup-*` directories inside `$HERMES_HOME/plugins/`. A disposable installer probe confirmed that an old target is moved to the backup directory while the discovery root contains only the active `sdd` link. A repository regression test now protects this invariant.

Historical repository gates after installer hardening passed in the Hermes runtime environment: `38` unittest cases, repository verification, Ruff lint, Ruff format check, and `git diff --check`. The project `uv` environment also ran `38` cases and reported only the two known optional FastAPI/HTTPX skips. A second disposable installer probe confirmed idempotence and exactly one preserved backup outside the discovery root.

## Adversarial state-integrity probe (2026-09-22 10:54 -03)

A disposable Python probe exercised symlink boundaries, registry failure, malformed payloads, and malformed canonical JSON. The probe used only temporary directories under the Hermes scratch area and was removed after read-back.

Verified defects:

- A symlinked `.sdd/events.jsonl` was accepted and `transition` wrote the event through the link into an outside file. The operation returned success; the outside file changed.
- A symlinked individual milestone directory (`.sdd/milestones/M001`) was accepted even though the parent `milestones` directory was checked. `transition` wrote the plan and rendered artifacts through the link into the outside directory.
- If the optional SQLite source registry raised during `init`, canonical `.sdd/` files remained on disk but the operation raised `OSError` instead of returning a successful project initialization with a non-authoritative registry warning.
- `update_task` accepted scalar/dict values for list-like fields (`file_scope=42`, `acceptance={"bad":"shape"}`), persisted them, and returned success.
- An empty-list `project.json` was treated as a missing/default object because callers used `read_json(..., {}) or {}`. `status` returned `ok: true` with null project fields instead of reporting malformed canonical state.
- Forced initialization moved the existing `.sdd/` backup before validating replacement input, so an invalid forced init could leave the project without its active state; replacement validation and rollback on render failure are now covered by regression testing.

Impact classification:

- Symlinked authoritative files/directories are a **high integrity/security defect**: a project-local operation can write outside the project root when an attacker or accidental setup places a link in `.sdd/`.
- Registry failure is a **medium reliability defect**: the canonical state is created but the caller receives a failure and may retry or misdiagnose the project.
- Weak list/type validation, malformed JSON fallback, and invalid forced-init ordering are **high state-integrity defects**: invalid state can be persisted, silently presented as healthy, or displaced during a failed replacement.

The adversarial findings above were remediated in the current hardening pass; the regression coverage and residual UI deployment gate are recorded in the next section.

## Adversarial hardening applied and verified

The following production hardening changes were implemented with regression tests:

- Reject symlinks anywhere under project-local `.sdd/` metadata before reads or writes; JSON/JSONL, checkpoint reads, and atomic-write helpers also refuse symlink targets.
- Require explicit project roots for remote terminal backends (`docker`, `singularity`, `modal`, `managed_modal`, `daytona`, `vercel_sandbox`, and `ssh`).
- Treat the SQLite source registry as a non-authoritative projection: registry initialization or registration failures return a warning while canonical initialization remains usable.
- Reject malformed top-level JSON, malformed JSONL records, missing required canonical files, malformed collection shapes, scalar task/project/decision lists, and malformed decision-id lists rather than silently coercing or defaulting them; validate forced replacements before moving backups.
- Make stale-lock recovery process-aware: an old lock held by a live PID is not removed; locks from dead processes can be reclaimed.

Focused tests and the full project suite pass after this hardening. The project environment reports `61` tests passed with `2` optional Dashboard tests skipped because FastAPI/HTTPX are not installed (`Ran 61 tests`, `OK (skipped=2)`); 61 test methods are present across the suite. Repository verification, pinned Ruff lint/format, and `git diff --check` also pass. Initial-render rollback, replacement-validation, checkpoint symlink, process-aware lock, and empty-object schema cases are included in that count.

Optional Dashboard integration was then run in an isolated environment with FastAPI `0.128.2`, HTTPX `0.28.1`,
Pydantic `2.12.5`, and Pydantic Core `2.41.5`; both Dashboard tests passed (`Ran 2 tests`, `OK`). The release builder also passed
repository verification and produced inspected ZIP/tar.gz archives with 86 entries each, the root plugin manifest,
and no `__pycache__` entries. The scratch release artifacts were not added to the repository.

The latest optional Dashboard run and `hermes desktop --help` read-back also passed; the latter exposes the documented
`--cwd`, `--skip-build`, and `--force-build` launch controls without launching or altering the active Desktop.

An explicit remote-backend smoke probe also passed: implicit `ssh` root selection returned the expected explicit-root
error, while the same disposable project initialized successfully when `root=` was supplied.

## Not yet verified

- A fresh native Desktop launch with a clean isolated Hermes profile and a disposable initialized SDD project.
- Native Desktop plugin inventory record for `sdd` (`loaded` versus `error`) through Settings → Plugins or runtime introspection.
- Native Desktop mutation/read-back flow (`init`, `validate`, task transition) against a disposable project.
- Visible Dashboard `/sdd` page in a healthy browser shell with its SDK globals present.
- ~~Whether the current packaged release actually includes the latest native loader after the exact build used.~~ **Verified:** ASAR contains the runtime loader, SDK shim, Desktop plugin root IPC, and `Reload desktop plugins` action.
- A clean user-facing reproduction from a newly opened Hermes project rooted at `/home/felipe.arantes/Projects/hermes-sdd`.

The repository checkout intentionally remains uninitialized as an SDD project; disposable probes used temporary roots
and left no `.sdd/`, `release/`, or generated `__pycache__` state in this checkout.

## Next actions / remaining deployment gate

1. Keep the explicit-root guidance prominent: use `hermes sdd status -C <project>` for the standalone CLI; launch interactive Hermes with `hermes --in <project>` and Desktop with `hermes desktop --cwd <project>`.
2. Use the native Desktop Plugins rescan/palette action and inspect the plugin inventory/load status when a capturable Electron window or clean isolated Desktop profile is available.
3. Exercise a disposable Desktop mutation/read-back flow if the native UI can be observed; otherwise leave visual UI as an explicit deployment gate.
4. Keep this report updated after every major probe.

No further source-side blocker was found in this pass. The source-side hardening may be committed and pushed after
the final staged review requested by the maintainer. Do not mark the native UI gate verified without a capturable clean
Desktop launch, plugin inventory (`sdd` loaded rather than errored), native `/sdd` rendering, and disposable Desktop
mutation/read-back. The native UI gate also remains a release/tagging prerequisite.

## Historical fresh-profile probe (completed)

The first isolated probe command was malformed because `env -u` was placed after a prebuilt argument list; it performed no SDD operation and did not mutate the disposable project. The corrected probe used:

```bash
env -u TERMINAL_CWD -u HERMES_DESKTOP_CWD HERMES_HOME=<temporary-home> hermes ...
```

Results from temporary Hermes home `/home/felipe.arantes/.hermes/cache/scratch/sdd-profile-probe-20260922/home` and project `/home/felipe.arantes/.hermes/cache/scratch/sdd-profile-probe-20260922/project`:

- `hermes plugins doctor sdd` passed; it loaded the symlinked repository plugin and registered `1 tool(s), 0 hook(s)`.
- Implicit `hermes sdd init --json quick ...` returned `ok: true`, root equal to the disposable process cwd, mode `quick`, complexity score `6`.
- Implicit `hermes sdd status --json` returned `ok: true`, state `active`, health score `100`.
- Implicit `hermes sdd validate --json --no-record` returned `ok: true`, score `100`, no findings.
- Explicit `--root <temporary-project>` returned the same healthy project.
- The temporary home contained its own `sdd/sources.db`; the project contained canonical `.sdd/` files including `project.json`, `state.json`, `events.jsonl`, and rendered docs.
- No active Hermes home, gateway, Desktop process, or `/home/felipe.arantes/Projects/agent` state was touched.

**Conclusion:** a fresh profile with no inherited `TERMINAL_CWD` works end-to-end for the core CLI/plugin path. This materially strengthens the root/context hypothesis: the plugin itself works when Hermes is rooted at the intended project.

## Process cleanup ledger

- Isolated Dashboard process `proc_57d017a9564b` reached `HERMES_DASHBOARD_READY` on `127.0.0.1:40305`, then was terminated with signal 15 by process cleanup; a follow-up listener/process check found no listener on port `40305` and no investigation Dashboard process remains. The earlier `proc_22057910afaf` process is also stopped.
- Existing Desktop process was not stopped because it belongs to the user session and has not been safely restarted.
- The temporary fresh-profile probe tree `/home/felipe.arantes/.hermes/cache/scratch/sdd-profile-probe-20260922` was removed after final read-back; no disposable probe process or files remain.


```bash
git status --short --branch
hermes --version
hermes plugins doctor sdd
hermes sdd doctor --json
hermes sdd status --json
hermes sdd status --json --root /home/felipe.arantes/Projects/agent
env -u TERMINAL_CWD -u HERMES_DESKTOP_CWD hermes sdd status --json
```

## Compaction handoff

When context compacts, read this file first. Then re-check the process cleanup ledger, `git status`, and the **Not yet verified** / **Next actions** sections before doing more work. Do not repeat the full repository inventory unless new evidence contradicts the ledger.
