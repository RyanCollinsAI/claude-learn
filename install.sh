#!/usr/bin/env bash
# Install the learn skill into ~/.claude/skills/learn (macOS / Linux).
#
#   ./install.sh [--vault-root DIR] [--vault-name NAME] [--learning-dir DIR]
#                [--course-learning-dir PATTERN] [--no-prompt]
#
# Nothing is overwritten without being told to: an existing config.json is left alone.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
DEST="$CLAUDE/skills/learn"
VAULT=""
VAULT_NAME=""
LEARNING=""
COURSE=""
PROMPT=1

while [ $# -gt 0 ]; do
  case "$1" in
    --vault-root) VAULT="$2"; shift 2 ;;
    --vault-name) VAULT_NAME="$2"; shift 2 ;;
    --learning-dir) LEARNING="$2"; shift 2 ;;
    --course-learning-dir) COURSE="$2"; shift 2 ;;
    --no-prompt) PROMPT=0; shift ;;
    -h|--help) sed -n '2,9p' "$0"; exit 0 ;;
    *) echo "unknown flag: $1" >&2; exit 2 ;;
  esac
done

say() {  # say <ok|miss|opt> <label> <detail>
  case "$1" in ok) tag="OK  ";; miss) tag="MISS";; *) tag="--  ";; esac
  printf "  %s %-16s %s\n" "$tag" "$2" "$3"
}

# The first candidate that actually RUNS, not the first one on PATH. Windows ships a `python3`
# shim that resolves fine and then exits 9009 telling you to visit the Microsoft Store, so
# `command -v` alone picks a binary that cannot execute a single line.
PY=""
pick_python() {
  for c in python3 python py; do
    command -v "$c" >/dev/null 2>&1 || continue
    if [ "$c" = "py" ]; then
      if py -3 -c 'pass' >/dev/null 2>&1; then PY="py -3"; return 0; fi
    elif "$c" -c 'pass' >/dev/null 2>&1; then
      PY="$c"; return 0
    fi
  done
  return 1
}
pick_python || true

echo "claude-learn installer"
echo "  repo   $REPO"
echo "  target $DEST"
echo

# ---------------------------------------------------------------- 1. copy the skill
mkdir -p "$DEST/tools/vendor" "$DEST/courses"
cp "$REPO/skills/learn/SKILL.md"          "$DEST/"
cp "$REPO"/skills/learn/tools/*.py        "$DEST/tools/"
cp "$REPO"/skills/learn/tools/*.ps1       "$DEST/tools/"
cp "$REPO/skills/learn/tools/README.md"   "$DEST/tools/"
cp "$REPO"/skills/learn/tools/vendor/*    "$DEST/tools/vendor/"
if compgen -G "$REPO/skills/learn/courses/*.md" > /dev/null; then
  cp "$REPO"/skills/learn/courses/*.md    "$DEST/courses/"
fi
cp "$REPO/config.example.json"            "$DEST/"
echo "Skill copied."

# ---------------------------------------------------------------- 1b. the /learn command
mkdir -p "$CLAUDE/commands"
cp "$REPO/commands/learn.md" "$CLAUDE/commands/learn.md"
echo "Command copied: $CLAUDE/commands/learn.md - /learn now works."

# ---------------------------------------------------------------- 2. config.json
CONFIG="$DEST/config.json"
if [ -f "$CONFIG" ]; then
  echo "config.json already exists - left untouched. Delete it to regenerate."
else
  if [ -z "$VAULT" ] && [ "$PROMPT" = "1" ]; then
    echo
    echo "Where do session notes go? Any Markdown folder; Obsidian is what it is built around."
    printf "  vault root [%s]: " "$(pwd)"
    read -r VAULT
  fi
  [ -z "$VAULT" ] && VAULT="$(pwd)"

  if [ -z "$LEARNING" ] && [ "$PROMPT" = "1" ]; then
    printf "  notes folder inside the vault [Learning]: "
    read -r LEARNING
  fi
  [ -z "$LEARNING" ] && LEARNING="Learning"

  if [ -z "$COURSE" ] && [ "$PROMPT" = "1" ]; then
    echo "  Organise some notes by course? Give a pattern with {course} in it, or press enter to skip."
    printf "  course notes pattern []: "
    read -r COURSE
  fi

  echo
  if [ -z "$PY" ]; then
    echo "No working python found - cannot write config.json." >&2
    echo "Install Python 3.9+ and re-run, or copy config.example.json to $CONFIG by hand." >&2
    exit 1
  fi
  $PY "$REPO/tools/write_config.py" "$CONFIG" "$VAULT" "$VAULT_NAME" "$LEARNING" "$COURSE"
  echo "Wrote $CONFIG"

  # The notes folder and the learner profile have to exist before the first session: quiz.py
  # refuses to write into a note that is not there, and the profile is read before every probe.
  # Create before resolving: `cd` into a vault that does not exist yet is a hard failure, and
  # pointing the installer at a folder you have not made yet is the normal first run.
  mkdir -p "$VAULT/$LEARNING"
  FULL="$(cd "$VAULT" && pwd)"
  if [ ! -f "$FULL/$LEARNING/LEARNER.md" ]; then
    cp "$REPO/templates/LEARNER.md" "$FULL/$LEARNING/LEARNER.md"
    echo "  seeded $FULL/$LEARNING/LEARNER.md - fill in who you are before the first session"
  fi
fi

# ---------------------------------------------------------------- 3. dependencies
echo
echo "Dependencies"
if [ -n "$PY" ]; then
  V="$($PY -c 'import sys;print("%d.%d" % sys.version_info[:2])')"
  if $PY -c 'import sys;sys.exit(0 if sys.version_info>=(3,9) else 1)'; then
    say ok python "$V via '$PY'"
  else
    say miss python "$V - needs 3.9 or newer"
  fi
else
  say miss python "no working python found - quiz.py and both render tools need one"
fi

if command -v claude >/dev/null; then
  say ok claude "$(command -v claude)"
else
  say miss claude "not on PATH - this is a Claude Code skill"
fi

OBSIDIAN=""
for c in "/Applications/Obsidian.app" /usr/bin/obsidian /opt/Obsidian/obsidian /snap/bin/obsidian; do
  [ -e "$c" ] && OBSIDIAN="$c" && break
done
if [ -z "$OBSIDIAN" ] && command -v obsidian >/dev/null 2>&1; then
  OBSIDIAN="$(command -v obsidian)"
fi
if [ -n "$OBSIDIAN" ]; then
  say ok obsidian "$OBSIDIAN"
else
  say miss obsidian "required - not found. Get it at https://obsidian.md/download. Any Markdown editor that renders LaTeX and mermaid live also works."
fi

CHROME=""
for c in "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
         "/Applications/Chromium.app/Contents/MacOS/Chromium" \
         /usr/bin/google-chrome /usr/bin/chromium-browser /usr/bin/chromium; do
  [ -x "$c" ] && CHROME="$c" && break
done
if [ -n "$CHROME" ]; then
  say ok chrome "$CHROME"
else
  say opt chrome "optional - only the two render tools need it. Set chrome_path if installed elsewhere."
fi

if [ -n "$PY" ] && $PY -c 'import PIL' 2>/dev/null; then
  say ok pillow "diagram crops will be exact"
else
  say opt pillow "optional - without it a rendered diagram keeps a little slack, never clipped"
fi

say opt pwsh "layout.ps1 and open_note.ps1 are Windows only - switch windows yourself elsewhere"

# ---------------------------------------------------------------- 4. done
echo
echo "Installed. In Claude Code, try:"
echo '  "teach me the master theorem"'
echo "Read $DEST/tools/README.md for what each tool does."
