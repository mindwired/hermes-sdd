# Hermes SDD

Adaptive, durable, and context-efficient spec-driven development for Hermes Agent.

Hermes SDD is designed for projects that are too large, risky, or long-running to rely on one conversation,
without forcing every change through an expensive ceremony. It gives Hermes a compact orchestration surface,
project-local state, bounded context packs, dependency-aware parallel work, evidence gates, and optional native
interfaces for the web Dashboard and Hermes Desktop.

## Design goals

- **Results before process.** Artifacts exist only to improve implementation, recovery, verification, or coordination.
- **Adaptive rigor.** Small changes stay small; greenfield programs receive stronger planning and evidence.
- **Lean agent context.** One Agent tool and progressively loaded skills avoid a permanent wall of SDD schemas.
- **Durable continuity.** Plain `.sdd/` files preserve intent across sessions, models, machines, and context resets.
- **Safe parallelism.** Dependencies, active work, risk, interface stability, and file scopes constrain task waves.
- **Evidence over completion claims.** High-risk work needs successful evidence before milestone finalization.
- **Portable core, thin UIs.** TUI, CLI, gateways, Dashboard, and Desktop operate on the same state and backend.

## What is included

```text
.
├── plugin.yaml                 # Hermes Agent plugin manifest
├── __init__.py                 # Hermes plugin entry point
├── hermes_sdd/                 # Core, commands, installer, diagnostics, API
├── skills/                     # Five progressively loaded workflow skills
├── dashboard/                  # Web Dashboard tab + shared FastAPI backend
├── desktop/plugin.js           # Native Hermes Desktop adapter
├── tests/                      # Unit and integration tests
├── scripts/                    # Verification, release, and local-dev installation
├── docs/                       # Architecture, format, operation, and research docs
└── .github/                    # CI, security, release, issue templates, Dependabot
```

The runtime Python core has no third-party dependency. `fastapi` is imported only when Hermes loads the
Dashboard/Desktop backend, where FastAPI is already part of Hermes.

## Installation

### Recommended: Hermes's built-in plugin manager

After publishing this repository on GitHub:

```bash
hermes plugins install mindwired/hermes-sdd --enable
hermes gateway restart
```

This installs the Agent tool, slash commands, CLI command, skills, Dashboard frontend, and backend.

It is a global installation for the active Hermes profile. Do this once; do not repeat it in every project.

Install the native Desktop adapter once as well:

```bash
hermes sdd ui install
```

Restart the gateway after the plugin install. Restart the Dashboard process, then reload the browser page. In
Hermes Desktop, open the command palette and run **Reload desktop plugins** (or restart Desktop). Both UIs then
show **SDD** in the sidebar and open it at `/sdd`.

On a fresh Linux or macOS install, `auto` mode creates a symlink from Hermes Desktop's plugin folder to the
installed repository. A normal `hermes plugins update sdd` then updates both layers automatically. Windows uses a
copy fallback. If an existing adapter is current, `auto` preserves its existing copy/link mode; use `--force` only
when intentionally switching modes or replacing a different target.

Verify everything:

```bash
hermes sdd doctor
hermes plugins list --plain
```

See [Installation](docs/INSTALLATION.md) for manual, profile, local-development, rollback, and uninstall paths.

### Is cloning into the plugin folder enough?

Technically, yes for the Agent and Dashboard portions: a directory under `$HERMES_HOME/plugins/sdd` containing
`plugin.yaml` and `__init__.py` can be discovered after it is enabled. It is not the preferred production path.
The built-in manager also validates the manifest, uses the manifest name safely, preserves Git metadata for
`hermes plugins update`, handles enabling, and presents post-install guidance. Native Desktop remains separate
because Hermes intentionally loads it from `$HERMES_HOME/desktop-plugins/sdd/plugin.js`.

## First project

The plugin is global, while SDD state is intentionally per project. In each project, initialize the local state
once; this does not reinstall or configure the plugin:

From a project directory:

```bash
hermes sdd init auto "Build a local-first observability platform"
hermes sdd status
```

The standalone CLI uses the active Hermes terminal working directory. If it differs from the intended repository,
pass the project explicitly with `--root` or `-C`. Remote backends such as SSH, Docker, Modal, Daytona, Vercel
Sandbox, and Singularity require an explicit root:

```bash
hermes sdd status -C /path/to/project
```

The same project can be opened later from any Hermes surface. Its `.sdd/` directory is the authoritative local
state; the installed plugin and its UI adapters stay available globally.

Or inside any Hermes chat surface:

```text
/sdd init auto Build a local-first observability platform
/sdd status
/sdd next
```

The `auto` mode scores novelty, ambiguity, surface area, risk, expected duration, and coordination, then chooses:

| Mode | Use |
|---|---|
| `quick` | Small bounded work; minimal state and evidence |
| `standard` | Multi-file or multi-session work; requirements and one milestone |
| `deep` | Cross-cutting architecture, uncertainty, or higher operational risk |
| `program` | Large greenfield products, many milestones, or multiple workers |

## Core workflow

1. Initialize or onboard the project.
2. Record concise requirements and load-bearing architectural decisions.
3. Create outcome-oriented milestones; fully detail only the active one.
4. Decompose it into context-sized tasks with acceptance criteria, dependencies, risks, and file scopes.
5. Ask for the next safe wave; parallelize only the returned independent tasks.
6. Create a checkpoint and bounded context pack before substantial work.
7. Implement, verify, and attach evidence.
8. Validate traceability and finalize the milestone.
9. Recover from interruption by reconciling `.sdd/`, Git, source files, and evidence—not by trusting stale status.

## One compact Agent tool

The model sees one `sdd` tool with an `operation` field. Major operations include:

- `init`, `status`, `configure`
- `upsert_spec`, `record_decision`
- `create_milestone`, `update_milestone`, `set_plan`, `update_task`
- `next`, `transition`, `record_evidence`, `finalize_milestone`
- `context_checkpoint`, `context_delta`, `context_pack`
- `validate`, `register_source`, `list_sources`, `remove_source`

The five bundled skills add procedural guidance only when relevant:

- `sdd-start`
- `sdd-plan`
- `sdd-execute`
- `sdd-verify`
- `sdd-recover`

## State model

`.sdd/` is authoritative and suitable for version control:

```text
.sdd/
├── project.json
├── state.json
├── PROJECT.md
├── requirements.json
├── REQUIREMENTS.md
├── architecture.md
├── decisions/
├── milestones/
│   └── M001/
│       ├── milestone.json
│       ├── plan.json
│       ├── PLAN.md
│       └── summary.md
├── milestones/<id>/evidence.jsonl
├── checkpoints/
├── validations/
└── events.jsonl
```

SQLite is used only for the optional UI source registry under the user's Hermes home. It can be deleted and
reconstructed without losing project state.

## Development

```bash
uv sync --locked
uv run python -m unittest discover -s tests -v
uv run python scripts/verify.py
```

With network access:

```bash
uvx --from ruff==0.16.1 ruff check .
uvx --from ruff==0.16.1 ruff format --check .
```

For live local development:

```bash
./scripts/install-dev.sh
hermes gateway restart
```

The script symlinks this checkout into both Hermes plugin locations on POSIX so edits are immediately visible.

## Documentation

- [Installation and updates](docs/INSTALLATION.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Deep SDD comparison](docs/ANALYSIS.md)
- [State format](docs/STATE_FORMAT.md)
- [Operations and recovery](docs/OPERATIONS.md)
- [Development and testing](docs/DEVELOPMENT.md)
- [Compatibility policy](docs/COMPATIBILITY.md)
- [Verification report](docs/VERIFICATION.md)
- [Agent handoff](HANDOFF.md)

## Status

`0.1.0` is an alpha with project-local state, bounded context packs, evidence gates, and UI adapters. Optional
Dashboard dependencies and graphical adapters remain deployment gates; skipped integration tests are not treated as
coverage. Before broad distribution, smoke-test the graphical adapters against the exact Hermes release you deploy.
The repository is published at [mindwired/hermes-sdd](https://github.com/mindwired/hermes-sdd).

## License

MIT
