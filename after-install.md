# Hermes SDD installed

The Agent tool, slash commands, skills, CLI command, and Dashboard adapter are now installed globally in the
active Hermes profile. You do not need to install SDD again for each project.

The repository is public. The one-time installation command is:

```bash
hermes plugins install mindwired/hermes-sdd --enable
```

1. Restart the gateway so Python routes and commands are reloaded:

   ```bash
   hermes gateway restart
   ```

2. Install the native Desktop adapter once. This is separate because Hermes Desktop discovers native UI plugins
   from a different global directory:

   ```bash
   hermes sdd ui install
   ```

3. Restart or reload the Dashboard and Desktop once after installation. In Desktop, open the command palette and
   run **Reload desktop plugins**. In Dashboard, restart the Dashboard process (or reload the browser page after
   the process has restarted). The SDD entry then appears in the sidebar at `/sdd`.

4. Open any project and initialize its local SDD state. This is project data, not another plugin installation:

   ```bash
   hermes sdd init auto "Describe the project goal"
   ```

Run `hermes sdd doctor` to verify the global installation. From then on, use SDD in any project with:

```bash
hermes sdd status
```

or `/sdd status` in a Hermes chat. The project-specific `.sdd/` directory stores requirements, roadmap, tasks,
evidence, and checkpoints; the plugin itself remains globally available under the active Hermes home.
