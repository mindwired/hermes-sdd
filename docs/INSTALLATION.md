# Installation, updates, and removal

## Recommended production installation

Hermes already provides the correct repository installer. Publish this project with `plugin.yaml` and
`__init__.py` at the repository root, then run:

```bash
hermes plugins install mindwired/hermess-sdd --enable
hermes gateway restart
hermes sdd ui install
hermes sdd doctor
```

This is a one-time global installation for the active Hermes profile. It clones the complete repository into the
profile's plugin directory; do not repeat it for each project. Keeping the plugin
at the repository root is important: Hermes retains the Git checkout, so later updates can use:

```bash
hermes plugins update sdd
hermes gateway restart
```

### Why there is still a Desktop command

Hermes has three intentionally separate extension systems:

- Agent plugin: `$HERMES_HOME/plugins/sdd/plugin.yaml` and `__init__.py`
- Dashboard adapter: `$HERMES_HOME/plugins/sdd/dashboard/`
- Native Desktop adapter: `$HERMES_HOME/desktop-plugins/sdd/plugin.js`

Agent and Dashboard install together. Desktop cannot be discovered from the regular plugin folder, so
`hermes sdd ui install` creates the smallest possible bridge. This is also a one-time global installation, not a
per-project setup step.

On a fresh install, the default is a symlink on POSIX and a copy on Windows because symlink privileges are
inconsistent. If a current adapter already exists, the default preserves its mode so repeated installs are
idempotent. Explicit modes are available:

```bash
hermes sdd ui install --mode link
hermes sdd ui install --mode copy
hermes sdd ui install --force
hermes sdd ui status
hermes sdd ui uninstall
```

After installing or updating, restart the gateway. Restart the Dashboard process and reload its browser page. In
Desktop, use the command palette command **Reload desktop plugins** or restart the Desktop app. The SDD sidebar
entry is `/sdd`; the command palette entry is **Open SDD Project**.

## Per-project initialization

Only the project state is local. From each project directory, initialize `.sdd/` once:

```bash
cd /path/to/project
hermes sdd init auto "Describe the project goal"
```

This does not install the plugin again. It creates the authoritative requirements, roadmap, task, evidence, and
checkpoint files for that project. Later, use `hermes sdd status`, `/sdd status`, the `sdd` Agent tool, or the
Dashboard/Desktop **SDD** page without repeating installation.

The standalone CLI follows the active Hermes terminal working directory. Use `--root`/`-C` when the shell and active
Hermes project differ. For remote terminal backends such as SSH, Docker, Modal, Daytona, Vercel Sandbox, or
Singularity, always pass an explicit root because the backend working directory may not identify the host repository:

```bash
hermes sdd init quick "Describe the project goal" --root /path/to/project
hermes sdd status -C /path/to/project
```

## Is a manual clone sufficient?

The following can work for Agent and Dashboard:

```bash
git clone https://github.com/mindwired/hermess-sdd.git "$HERMES_HOME/plugins/sdd"
hermes plugins enable sdd
hermes gateway restart
```

It is less robust than `hermes plugins install` because the built-in command validates the plugin manifest,
normalizes the destination, handles an existing install safely, updates Hermes configuration, and displays the
repository's `after-install.md` instructions. Use manual cloning mainly for debugging the installer itself.

You would still need:

```bash
hermes sdd ui install
```

for native Desktop.

## Local development

POSIX:

```bash
./scripts/install-dev.sh
```

This creates development symlinks from the active `$HERMES_HOME` to the checkout. Existing destinations are
moved to timestamped backups under `$HERMES_HOME/plugin-backups/sdd/` unless they already point to this checkout.
Keeping backups outside `$HERMES_HOME/plugins/` prevents Hermes from discovering a stale backup as a second plugin.

Windows PowerShell:

```powershell
./scripts/install-dev.ps1
```

The PowerShell script copies the checkout because creating directory symlinks may require elevated privileges or
Developer Mode. Run it again to synchronize changes.

A production-like local Git installation is also available:

```bash
./scripts/install-local.sh
```

It asks Hermes to clone the current Git repository through a `file://` URL, then installs Desktop. Commit local
changes first because Git clones only committed content.

## Profiles and custom HERMES_HOME

All paths are derived from `HERMES_HOME`; no path is hardcoded to `~/.hermes`. When Hermes is operating under a
named profile, run installation and UI commands in that profile's environment. Confirm the resolved path with:

```bash
hermes sdd doctor
```

## Updates

Symlink Desktop installation:

```bash
hermes plugins update sdd
hermes gateway restart
```

Copy Desktop installation:

```bash
hermes plugins update sdd
hermes sdd ui install --force   # replace the copied adapter after the source update
hermes gateway restart
```

The gateway restart matters because Python plugin and FastAPI route modules are imported into long-lived
processes. Dashboard frontend-only rescans do not remount changed Python routes.

## Rollback

For a Git-managed installation:

```bash
cd "$HERMES_HOME/plugins/sdd"
git log --oneline --decorate -20
git checkout <known-good-tag-or-commit>
hermes sdd ui install --force   # required only for copy mode
hermes gateway restart
```

Project `.sdd/` state changes are intentionally explicit. Back up or commit project state before trying a newer
plugin against important repositories. Forced project reinitialization creates a backup instead of deleting the
old state.

## Uninstall

```bash
hermes sdd ui uninstall
hermes plugins remove sdd
hermes gateway restart
```

Removing the plugin does not delete `.sdd/` directories in projects. Those are normal project artifacts and must
be removed deliberately if no longer wanted.
