# Development

## Requirements

- Python 3.11, 3.12, or 3.13
- `uv`
- Node.js for JavaScript syntax validation
- Git
- A current Hermes installation for end-to-end UI smoke tests

## Bootstrap

```bash
uv sync --locked
```

There are no mandatory third-party runtime or test dependencies. This keeps local and offline verification
possible and avoids installing an independent FastAPI version into Hermes. Integration tests use the FastAPI and
HTTPX versions already available in the test environment when present; otherwise they skip cleanly.

When the optional Dashboard dependencies are absent, the two Dashboard tests are expected skips rather than passing
coverage. To execute them explicitly, use the isolated dependency command documented in `docs/VERIFICATION.md`.

## Test layers

```bash
uv run python -m unittest discover -s tests -v
uv run python scripts/verify.py
```

The suite covers:

- lifecycle from initialization through finalization;
- adaptive complexity selection;
- task DAG cycles and dependency enforcement;
- conservative file-scope overlap and parallel waves;
- start-time revalidation against already-running workers;
- critical-task and unstable-interface isolation;
- evidence gates proportional to mode and task risk;
- context checkpoints, wildcard file hashes, deltas, and budgets;
- concurrent independent task transitions and plan revision safety;
- forced initialization backups;
- required project schema fields and malformed empty-object state;
- symlink, malformed-state, typed-collection, registry-projection, remote-root, project-schema, initial-render rollback, and process-aware lock regressions;
- Agent plugin registration and skill discovery;
- Desktop adapter installation modes;
- Dashboard API behavior when FastAPI test support is available (the optional Dashboard command is in `docs/VERIFICATION.md`);
- manifest/version consistency, JavaScript syntax, and release layout.

## Linting

```bash
uvx --from ruff==0.16.1 ruff check .
uvx --from ruff==0.16.1 ruff format --check .
```

Ruff is intentionally run through `uvx` rather than made a runtime dependency. CI pins the same version.

## Live Hermes testing

```bash
./scripts/install-dev.sh
hermes gateway restart
hermes sdd doctor
```

Exercise at least:

1. `hermes sdd init` in a disposable Git repository.
2. `/sdd status` and the `sdd` Agent tool in TUI/Desktop chat.
3. Dashboard source registration and operations.
4. Desktop page, status bar, task start, and context copying.
5. `hermes plugins update` from a test remote or local bare repository.

For a clean native Desktop attempt, use `hermes desktop --cwd /path/to/disposable-project --skip-build` when the
packaged app is already built, or add `--force-build` to rebuild first. Do not use the active user Desktop as a
destructive test target.

## Release

```bash
uv run python scripts/build_release.py --version 0.1.0
```

The script rejects inconsistent versions or a dirty layout, runs verification, creates deterministic ZIP and
source tar archives, and writes SHA-256 files under `release/`. GitHub Actions performs the same validation before
attaching artifacts to a version tag.
