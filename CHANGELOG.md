# Changelog

All notable changes follow [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project uses semantic versioning.

## [Unreleased]

### Fixed

- Use Hermes' qualified `sdd:sdd-*` namespace in the Agent tool guidance and guard it with a registration regression test.
- Harden canonical state handling against symlink traversal, malformed JSON/JSONL and collection payloads, unsafe
  stale-lock reclamation, and non-authoritative source-registry failures; require explicit roots for remote terminals.
- Validate required project schema fields and roll back new or forced initialization if initial rendering fails.

## [0.1.0] - 2026-08-01

### Added

- Adaptive `quick`, `standard`, `deep`, and `program` SDD modes.
- Durable `.sdd/` project state, milestones, tasks, requirements, ADRs, evidence, and events.
- Dependency- and file-scope-aware parallel wave scheduler.
- Context checkpoints, file-hash deltas, and bounded context packs.
- One compact Hermes Agent tool, slash commands, CLI command, and five skills.
- Hermes Dashboard and native Desktop adapters sharing one backend API.
- Desktop adapter installation, synchronization, status, and removal commands.
- Unit, integration, concurrency, compatibility, and packaging validation.
