#!/usr/bin/env bash
# Remove exactly what install.sh put down: the skill folder and the /learn command.
#
#   ./uninstall.sh [--force]
#
# Deletes ~/.claude/skills/learn (the skill, its tools, config.json, and any courses you
# dropped in) and ~/.claude/commands/learn.md. Your vault - session notes, the learner
# profile, review cards - is never touched, because none of it lives under ~/.claude.
set -euo pipefail

CLAUDE="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
DEST="$CLAUDE/skills/learn"
CMD="$CLAUDE/commands/learn.md"
FORCE=0

while [ $# -gt 0 ]; do
  case "$1" in
    --force) FORCE=1; shift ;;
    -h|--help) sed -n '2,9p' "$0"; exit 0 ;;
    *) echo "unknown flag: $1" >&2; exit 2 ;;
  esac
done

echo "claude-learn uninstaller"
echo "  skill folder   $DEST"
echo "  command        $CMD"
echo

if [ ! -e "$DEST" ] && [ ! -e "$CMD" ]; then
  echo "Nothing installed at either path. Nothing to do."
  exit 0
fi

if [ "$FORCE" != "1" ]; then
  printf "Remove both? This deletes config.json and any courses you dropped in. [y/N]: "
  read -r REPLY
  case "$REPLY" in
    [Yy]*) ;;
    *) echo "Cancelled."; exit 1 ;;
  esac
fi

if [ -e "$DEST" ]; then rm -rf "$DEST"; echo "Removed $DEST"; else echo "Not present: $DEST"; fi
if [ -e "$CMD" ]; then rm -f "$CMD"; echo "Removed $CMD"; else echo "Not present: $CMD"; fi

echo
echo "Done. Your vault - session notes, the learner profile, review cards - was never touched."
