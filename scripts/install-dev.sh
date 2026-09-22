#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
PLUGIN_TARGET="$HERMES_HOME/plugins/sdd"
BACKUP_ROOT="$HERMES_HOME/plugin-backups/sdd"
DESKTOP_DIR="$HERMES_HOME/desktop-plugins/sdd"
DESKTOP_TARGET="$DESKTOP_DIR/plugin.js"
STAMP="$(date +%Y%m%d-%H%M%S)"

backup_or_remove() {
  local target="$1"
  local desired="$2"
  if [[ -L "$target" ]] && [[ "$(readlink -f "$target")" == "$(readlink -f "$desired")" ]]; then
    return 0
  fi
  if [[ -e "$target" || -L "$target" ]]; then
    local backup="$BACKUP_ROOT/$(basename "$target").backup-$STAMP"
    mkdir -p "$BACKUP_ROOT"
    mv "$target" "$backup"
    printf 'Backed up %s -> %s\n' "$target" "$backup"
  fi
}

mkdir -p "$HERMES_HOME/plugins" "$DESKTOP_DIR"
backup_or_remove "$PLUGIN_TARGET" "$ROOT"
ln -sfn "$ROOT" "$PLUGIN_TARGET"
backup_or_remove "$DESKTOP_TARGET" "$ROOT/desktop/plugin.js"
ln -sfn "$ROOT/desktop/plugin.js" "$DESKTOP_TARGET"

cat <<MSG
Hermes SDD development links installed:
  Agent/Dashboard: $PLUGIN_TARGET -> $ROOT
  Desktop:        $DESKTOP_TARGET -> $ROOT/desktop/plugin.js

Enable and reload:
  hermes plugins enable sdd
  hermes gateway restart
  hermes sdd doctor
MSG
