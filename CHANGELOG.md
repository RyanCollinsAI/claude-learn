# Changelog

## 0.3.0 - 2026-09-04

Three changes taken from a side-by-side comparison with Eero Alvar's learning
system, which arrived at a near-identical teaching philosophy through a
different architecture. These are the parts his had that this did not.

### Changed

- **The main teaching agent no longer draws.** Every diagram now goes to a
  subagent that owns the whole author - render - look - fix loop and hands back
  only a finished diagram. It calls `render_mermaid.py` / `render_svg.py`
  itself, `Read`s the PNG, iterates up to four renders, and reports an
  outstanding flaw plainly rather than shipping it silently. Calling a render
  tool from the main thread is now an anti-pattern: a retry loop there dumps
  every failed attempt into the teaching context and never leaves it.
- **Research subagents have one fixed return shape** - `## Summary`,
  `## Findings` (numbered, each with its source), `## Sources` (kept and
  dropped, with why), `## Gaps`. An ad hoc paragraph hides what was checked and
  what was not; a fixed shape makes two research calls comparable, and `Gaps`
  turns "could not verify this" into something the lesson has to say out loud.

### Added

- **`tools/run_evals.py`** - runs a set of behaviour evals against two copies of the skill and
  diffs them, which is the only way to tell whether an edit to `SKILL.md` changed what an agent
  actually does. Each arm is a throwaway project dir with its own scratch vault and a stubbed
  `layout.ps1` / `open_note.ps1`, so a suite of headless runs cannot touch a real vault or tile a
  real desktop. Two limits are documented rather than hidden: the grader picks its own denominator
  per run, so a single eval moving is usually that and not a regression, and one headless run is a
  thin slice of a skill built for a long two-person session. Quote the aggregate, not a row.
  No eval file ships - an eval set encodes what its author wants, so write your own.
- **`quiz.py grade --why "<text>"`** - optional free text carrying the reasoning
  that came with the pick. It lands in the note as a folded callout under that
  question's grade, and as `why` in the log. Reasoning for a wrong answer is now
  readable where it happened instead of pooled into one block at the end of the
  session. `ask` now says so in its pointer line.

## 0.2.0 - 2026-09-04

Fixes from a fresh-eyes install audit against a stranger who has never seen the skill before.

### Added

- **`commands/learn.md`** - the README has always promised `/learn <anything>`; there was no
  `commands/` directory in the repo, so it never fired. Both installers now copy it to
  `~/.claude/commands/learn.md`.
- **`install.ps1 -Verify` / `install.sh --verify`** - runs one real probe question (ask, grade)
  plus a mermaid render against a throwaway vault right after install, and prints PASS/FAIL per
  step. The new `tools/verify_install.py` does the work; both installers just call it.
- **`uninstall.ps1` / `uninstall.sh`** - removes exactly what the installer put down:
  `~/.claude/skills/learn` and `~/.claude/commands/learn.md`. There was no way to remove a test
  install before this.
- Both installers now check for **Obsidian**, which the README already calls required, and print
  a clear MISS with the download URL instead of a clean bill of health on five other dependencies
  while the one the skill is built around goes unchecked.

### Fixed

- `skills/learn/courses/README.md` was installed into the folder the skill globs for pre-built
  courses, so the "ships empty" claim was false and the file could surface as a fake course. It is
  deleted; its guidance moved into this README's Pre-built courses section.

## 0.1.0 - 2026-09-04

First public release. The skill had been running against one person's vault for weeks; this is that
same skill with every machine-specific and personal value lifted out into config.

### Added

- **`config.json`** - `vault_root`, `obsidian_vault_name`, `learning_dir`, `course_learning_dir`,
  `learner_file`, `quiz_log_dir`, `visuals_dir`, `chrome_path`, `terminal_process`. Every key is
  optional and has a default derived from the current directory, so the skill runs on a fresh clone
  with no config file at all. Every key is also overridable for a single run with `LEARN_<KEY>`.
- **`tools/learnlib.py`** - the shared config loader the Python tools import. Both PowerShell tools
  read the same `config.json` and honour the same environment variables.
- **`install.ps1` / `install.sh`** - copy the skill, write a `config.json` from flags or prompts,
  seed the notes folder and a `LEARNER.md`, and report which dependencies are present and what
  still works without the missing ones. An existing `config.json` is never overwritten.
- **`templates/LEARNER.md`** - the learner profile, with a `## Who you are teaching` section. That
  is where anything about a specific person now lives.
- **Chrome is found, not hardcoded.** `chrome_path` if set, then the usual per-platform install
  paths, then `chrome`/`chromium` on `PATH`. When nothing is found the render tools exit 1 naming
  the config key rather than failing inside `subprocess`.

### Changed

- **`SKILL.md` names no person and no absolute path.** Paths are written as `$LEARN/tools/...` and
  `<config key>`, and the learner is "the learner" or "they". The bio that used to sit in the skill
  moved to the learner profile, where it belongs and where it gets updated.
- **`quiz.py`** reads its vault root and its sidecar folder from the config instead of two module
  constants.
- **`open_note.ps1`** defaults `-Vault` and `-VaultRoot` from the config; **`layout.ps1`** takes
  `terminal_process` from it.
- **Pre-built courses are globbed, not listed.** `courses/*.md` each states its own triggers at the
  top, so adding one needs no edit to `SKILL.md`. The folder ships empty.

### Not included

The author's own course files, evals and vault notes. They name real classes and a real person, and
none of it would run anywhere else.
