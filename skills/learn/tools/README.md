# tools

Seven CLI tools for the `learn` skill. Nothing here reaches the network at run time.

On Windows use `py`, not `python` - the bare name is a Microsoft Store stub. Elsewhere use `python3`.

## learnlib.py

Not a command. The shared config loader every other Python tool imports.

`config.json`, next to `SKILL.md` one level up, supplies the machine-specific values: `vault_root`, `obsidian_vault_name`, `learning_dir`, `course_learning_dir`, `learner_file`, `quiz_log_dir`, `visuals_dir`, `chrome_path`, `terminal_process`. Every key is optional and has a default, so the tools run on a fresh clone with no config file at all. `config.example.json` documents each one.

Any key can be overridden for a single run with `LEARN_<KEY>`, e.g. `LEARN_VAULT_ROOT`. The two PowerShell tools read the same file and honour the same environment variables.

`chrome_path` is resolved lazily: the config value if set, then the usual per-platform install paths, then `chrome`/`chromium` on `PATH`. When nothing is found the render tools exit 1 naming the key, rather than failing inside `subprocess`.

## render_mermaid.py

Turns mermaid source into a tightly-cropped PNG. Uses the vendored `vendor/mermaid.min.js` - no network access at render time.

```
py render_mermaid.py --source diagram.mmd --out diagram.png [--width 1400] [--scale 2] [--theme default]
py render_mermaid.py --stdin --out diagram.png
```

- `--width` - pass-1 render window width in CSS px (default 1400). Only affects layout of diagram types that wrap to their container; most flowcharts ignore it.
- `--scale` - device scale factor baked into the final PNG (default 2, so text stays sharp at 2x).
- `--theme` - mermaid theme name: `default`, `dark`, `forest`, `neutral`.

Cropping is measured from painted pixels, not predicted. The page reports an estimated crop, Chrome screenshots it with slack on both axes, and the PNG is then trimmed to its true content box plus exactly 20 CSS px on every side. The estimate alone was not safe: element rectangles under-report on some diagram types, and shooting the estimate exactly sliced the right-hand participants off sequence diagrams.

Pillow does the trim and is **optional**. Without it the PNG keeps the slack - a little loose, never clipped.

Verified at 20.0 CSS px per side, zero spread, on `graph TD`, `graph LR`, `sequenceDiagram`, `stateDiagram-v2`, and an 8-node tree.

On success: prints the absolute PNG path to stdout, exits 0.

On a mermaid parse error: prints the mermaid parser's error text to stderr, exits 1, and writes no PNG. The tool never hands back a picture of mermaid's own error graphic - a non-zero exit always means "look at stderr, not the PNG," because there is no PNG.

Any other failure (Chrome missing, no render status recovered, Chrome produced no screenshot) also exits 1 with the reason on stderr.

## render_svg.py

Rasterizes an SVG file to PNG.

```
py render_svg.py --source diagram.svg --out diagram.png [--width W] [--height H] [--scale 2]
```

- `--width` / `--height` - output size in px. If omitted, parsed from the SVG's own `width`/`height` attributes, falling back to `viewBox`.
- `--scale` - device scale factor baked into the final PNG (default 2).

On success: prints the absolute PNG path to stdout, exits 0.

On failure (no `<svg>` root element, or no usable width/height/viewBox and none passed explicitly, or Chrome could not produce a screenshot): prints a clear reason to stderr, exits 1, writes no PNG.

## test_render.py

Regression test for both renderers. Run it after any change to either.

```
py test_render.py
```

Renders five mermaid diagram types (`graph TD`, `graph LR`, `sequenceDiagram`, `stateDiagram-v2`, an 8-node tree), plus the mermaid parse-error path and both SVG paths. Exits 0 only when every case passes.

The crop standard is mechanical on purpose: every side between 10 and 20 CSS px, spread at most 4 device px, and **a zero margin on any side is a failure**, because content touching an edge means content was cut off. Three separate crop defects shipped past a "verified" report before this existed, and each was caught only by an input the previous round did not contain.

Needs Pillow to measure margins. Without it the script says so and exits 1 - skipping is not a pass.

## quiz.py

Asks one graded question. The question is written **into an Obsidian note**, the learner reads it there and types the number in the terminal, and the grade is written back into the same note. Nothing opens a window.

```
py quiz.py ask   --spec question.json --note "<learning_dir>/master-theorem"
py quiz.py grade --answer "2"         --note "<learning_dir>/master-theorem"
```

`--note` is vault-relative (to `vault_root`), forward slashes, no `.md`. The note must already exist.

Spec fields for `ask`: `question`, `options` (2 or more, each `{label, value, description}`), `correctAnswer` (an option **value**, or an array of them), `explanation`, and optionally `label` (a heading), `details`, `multiSelect`, `shuffle` (default true).

**The answer key never touches the note.** `ask` writes it to `<quiz_log_dir>/<slug>.pending.json` before the question is visible, so `grade` can only score against what was already on disk. The grade cannot bend to what was picked. That pre-commitment is the point of the tool.

- Write the question, options and explanation in LaTeX wherever maths appears. The note renders it.
- An "I don't know" choice is always offered as `0`. Writing your own is a hard error.
- `correctAnswer` is matched by value, never by position. A value matching no option is a hard error.
- `--answer` accepts `2`, `b`, `2,3` or `2 3` for multi-select, and `0`, `idk`, `?` or `dont know` for a gap. Multi-select grades as an exact-set match.
- Only one question may be pending per note. A second `ask` is refused.
- Every graded answer appends to `<quiz_log_dir>/<slug>.jsonl`.

`ask` prints a one-line pointer for the terminal and exits 0. `grade` prints the result JSON and exits 0.

Exit 2 means the spec or the answer was rejected, with the reason on stderr; the question stays pending so it can be retyped. Exit 3 on `grade` means nothing was pending for that note.

## layout.ps1

Tiles the two panes a session needs: Obsidian on the left, the terminal on the right. Windows only.

```
pwsh -File layout.ps1 [-Split 0.5] [-TerminalProcess WindowsTerminal]
```

Uses the primary monitor's **working area**, so nothing ends up under the taskbar, and restores a maximised window first because `MoveWindow` is ignored otherwise. Focus is left in the terminal, which is where the answers are typed. `-Split` is the fraction given to Obsidian; raise it for a diagram-heavy session.

The terminal is found by process name: `terminal_process` from `config.json` if set, otherwise `WindowsTerminal`, `wezterm-gui`, `alacritty`, then `conhost`. Override with `-TerminalProcess`.

Exit 0 means both were placed. Exit 1 means one was not running - it names which, and still places the other.

## open_note.ps1

Opens a vault note in Obsidian and raises the window past the terminal. Windows only.

```
pwsh -File open_note.ps1 -Note "<learning_dir>/master-theorem"
```

`-Note` is vault-relative, forward slashes, no `.md`. `-Vault` and `-VaultRoot` default to `obsidian_vault_name` and `vault_root` from `config.json`. The script escapes the path, so spaces and slashes survive, and it pairs `SetForegroundWindow` with `AttachThreadInput` because Windows otherwise refuses a background process the foreground.

Exit 0 means the window title confirms the note is open and in front. Exit 1 means the note file does not exist - **create it first**, the `obsidian://` URI navigates but never creates. Exit 2 means Obsidian never reported the note in its title within `-TimeoutSec` (default 25).
