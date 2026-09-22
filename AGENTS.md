# Agent instructions

This repository is a standalone Hermes plugin. The repository root must remain directly installable by
`hermes plugins install mindwired/hermes-sdd --enable`; do not move `plugin.yaml` or root `__init__.py`.

Use `uv` for Python project commands. Runtime code must use the standard library except for the optional
FastAPI module loaded only by Hermes Dashboard/Desktop. Keep the Agent surface to one `sdd` tool and
progressively loaded skills. Never make hidden SQLite data authoritative over project-local `.sdd/` files.

Before finishing a change, run:

```bash
uv run python -m unittest discover -s tests -v
uv run python scripts/verify.py
```

When network access is available, also run the pinned Ruff checks in `CONTRIBUTING.md`.
