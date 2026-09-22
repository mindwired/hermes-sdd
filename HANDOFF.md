# Implementation handoff

This directory is intended to become the root of a new GitHub repository.

## Before publishing

1. Confirm the target repository is `mindwired/hermes-sdd` and keep the manifest plugin name `sdd`.
2. Run all verification commands.
3. Initialize Git, commit, and push.
4. Enable GitHub private vulnerability reporting and branch protection.
5. Create the `v0.1.0` tag only after a live Hermes smoke test.

## Required validation

```bash
uv sync --locked
uv run python -m unittest discover -s tests -v
uv run python scripts/verify.py
uvx --from ruff==0.16.1 ruff check .
uvx --from ruff==0.16.1 ruff format --check .
```

## Live smoke test

```bash
hermes plugins install mindwired/hermes-sdd --enable
hermes gateway restart
hermes sdd ui install
hermes sdd doctor
```

Then verify Agent/TUI commands, Dashboard `/sdd`, and Desktop `/sdd` in a disposable project.

## Architectural invariants

- The repository root is the installable Hermes Agent plugin.
- `.sdd/` remains authoritative, portable, and service-independent.
- The model sees one compact `sdd` tool.
- UI adapters never implement independent scheduling or state semantics.
- Dashboard and Desktop call the same FastAPI backend.
- Process cost scales with project complexity rather than being mandatory ceremony.
