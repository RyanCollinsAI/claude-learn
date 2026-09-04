# Changelog

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
