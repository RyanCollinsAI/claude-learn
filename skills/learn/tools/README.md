# tools

Eleven CLI tools for the `learn` skill. Nothing here reaches the network at run time, except the page `podium_page.py` writes, which pulls KaTeX from a CDN.

On Windows use `py`, not `python` - the bare name is a Microsoft Store stub. Elsewhere use `python3`.

## learnlib.py

Not a command. The shared config loader every other Python tool imports.

`config.json`, next to `SKILL.md` one level up, supplies the machine-specific values: `vault_root`, `surface`, `obsidian_vault_name`, `learning_dir`, `course_learning_dir`, `learner_file`, `quiz_log_dir`, `visuals_dir`, `chrome_path`, `terminal_process`. Every key is optional and has a default, so the tools run on a fresh clone with no config file at all. `config.example.json` documents each one.

`surface` is `obsidian` (the default) or `podium`. It changes where the learner reads and answers, never what is written: the markdown note is the record on both. An unrecognised value falls back to `obsidian` rather than failing, so a typo degrades to the surface that needs no extra dependency.

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

Asks one graded question. The question is written **into the session note**, the learner reads it on whichever surface is configured and answers, and the grade is written back into the same note. Nothing opens a window.

```
py quiz.py ask   --spec question.json --note "<learning_dir>/master-theorem"
py quiz.py grade --answer "2"         --note "<learning_dir>/master-theorem"
py quiz.py grade --answer "2" --why "the tree collapses" --note "<learning_dir>/master-theorem"
py quiz.py show  --note "<learning_dir>/master-theorem"
```

The arguments are the same on both surfaces. On `surface: podium`, `ask` and `grade` additionally re-render the page so the question, and later the grade, appear there without anyone reopening anything; the answer comes back through `podium.py poll` rather than being typed. A page that fails to render prints a warning and does not fail the ask - the question is already in the note and already pre-committed to its sidecar, and losing that is worse than losing a repaint.

`show` reprints the pending question and its options in the terminal, read from the answer key's own file. Exit 3 when nothing is pending.

`--note` is vault-relative (to `vault_root`), forward slashes, no `.md`. The note must already exist.

Spec fields for `ask`: `question`, `options` (2 or more, each `{label, value, description}`), `correctAnswer` (an option **value**, or an array of them), `explanation`, and optionally `label` (a heading), `details`, `multiSelect`, `shuffle` (default true).

**The answer key never touches the note.** `ask` writes it to `<quiz_log_dir>/<slug>.pending.json` before the question is visible, so `grade` can only score against what was already on disk. The grade cannot bend to what was picked. That pre-commitment is the point of the tool.

- Write the question, options and explanation in LaTeX wherever maths appears. The note renders it.
- An "I don't know" choice is always offered as `0`. Writing your own is a hard error.
- `correctAnswer` is matched by value, never by position. A value matching no option is a hard error.
- `--answer` accepts `2`, `b`, `2,3` or `2 3` for multi-select, and `0`, `idk`, `?` or `dont know` for a gap. Multi-select grades as an exact-set match.
- Only one question may be pending per note. A second `ask` is refused.
- `--why` is optional free text - whatever reasoning came with the pick. It is written into the note as a folded `[!quote]` callout under that question's grade, and stored as `why` in the log, so a wrong pick's reasoning stays beside the question instead of being pooled at the end of the session.
- Every graded answer appends to `<quiz_log_dir>/<slug>.jsonl`.

`ask` prints a one-line pointer for the terminal and exits 0. `grade` prints the result JSON and exits 0.

Exit 2 means the spec or the answer was rejected, with the reason on stderr; the question stays pending so it can be retyped. Exit 3 on `grade` means nothing was pending for that note.

## podium_page.py

Renders a session note into the page the learner reads. Markdown in, one HTML page out: LaTeX through KaTeX, mermaid fences, tables, Obsidian embeds and folded callouts, and a real answer form whenever a quiz question is pending.

```
py podium_page.py --note "<learning_dir>/master-theorem"
py podium_page.py --note "..." --standalone --out share.html
py podium_page.py --note "..." --no-inline-assets
```

Three files are written beside the note: `<slug>-podium.html` (the shell), `<slug>-podium.js` (`window.LEARN_SESSION`, the rendered body) and `<slug>-podium-ver.js` (`window.LEARN_LATEST`, a hash). The shell loads the ~50-byte version file every 3 s and reloads the payload only when the hash moved, so refreshing after every node costs the browser almost nothing.

Both are script tags rather than a `fetch`. Lavish serves the page inside a sandboxed frame whose CSP has no `connect-src`, so `fetch` and `XHR` fail there silently while a script tag works. That is measured on this box, not assumed.

The markdown renderer is hand-written rather than a dependency, for two reasons: a stranger's clone has no `pip install` step, and every off-the-shelf renderer mangles LaTeX the moment it treats `x_1` as emphasis. Maths and code spans are pulled into placeholders before any inline rule runs.

- `--standalone --out <file>` writes ONE file with mermaid inlined from `vendor/mermaid.min.js` and no polling - the shareable export, openable over `file://` with no server and no vault. KaTeX still comes from its CDN; the fonts are not vendored, so a standalone page needs a network for its equations and nothing else.
- Images are inlined as data URIs by default, which is what makes the page portable and what lets Lavish serve it with no copy step. `--no-inline-assets` copies them beside the page instead.
- Two CSS rules exist only to keep a layout checker quiet, and both fix real overlaps: `pre.mermaid svg{height:auto}` (mermaid emits `height="100%"`, which makes the graph overrun the next heading) and an explicit `display:none` wrapper inside a folded `<details>` (Chrome otherwise hands out a zero-size box at the origin, which reads as overlapping text).

Exit 1 means the note does not exist.

## podium.py

Wraps `lavish-axi` so the skill can talk about commands instead of windows.

```
py podium.py open    --note "<learning_dir>/master-theorem"
py podium.py refresh --note "..."
py podium.py poll    --note "..." [--reply "..."]
py podium.py reply   --note "..." --text "..."
py podium.py end     --note "..."
py podium.py url     --note "..."
```

`open` renders the page and opens or resumes the Lavish session, printing the URL. `refresh` re-renders only; the open page picks it up on its own poll. `poll` blocks until the learner sends something - that is `lavish-axi poll`'s design, so run it in the background if the harness caps a foreground command and just re-run it if it dies, because queued feedback is never lost.

`poll` prints one line per event:

```
ANSWER 2 | WHY: the tree collapses geometrically
NOTE <selector> | ...      an annotation on one element
MESSAGE | ...              anything else they typed
LAYOUT 3 warnings          fix the page before involving them again
SESSION ended              they closed it
```

An answer is read from the `data` object the page attaches, with the text shape as a fallback for something queued by hand. Feed the number straight to `quiz.py grade --answer`.

Exit 1 means the note does not exist or `lavish-axi` is not on `PATH`; exit 3 means the poll came back empty, which means the server went away.

## session.py

What is still open, and how the checks are actually going.

```
py session.py check open  --note "<note>" --node 3 --question "derive the leaf-row total"
py session.py check close --note "<note>" --grade partial
py session.py status [--note "<note>"]
py session.py tally --note "<note>"
```

`quiz.py` already tracks its own pending questions; this does the same for the free-response checks, which are most of them. `status` lists both kinds across every note, oldest first, with ages, and exits **4** when anything is open so a session-start hook can branch on it. Exit 4 is a flag, not an error.

`check close` also counts the answer toward `<quiz_log_dir>/<slug>.tally.json`, and so does `quiz.py grade`. `tally` prints the running correct/partial/off count with its own reading when the rate leaves the three-in-four band. A `dontKnow` counts as off here: it is an honest gap rather than a wrong answer, but in both cases the idea did not land. The tally is never allowed to fail a grade - a broken counter is worth less than the answer it is counting.

## run_evals.py

Runs the behaviour evals in `evals/evals.json` and diffs two runs. Use it before and after a change to `SKILL.md`, which is the only way to tell whether an edit to the teaching rules actually changed what an agent does. Nothing ran the eval set before this file existed, which made it a dead feature - a list of expectations nobody checked.

```
py run_evals.py --arm before --skill <old skill dir> --evals evals/evals.json --out runs
py run_evals.py --arm after  --skill <this skill dir> --evals evals/evals.json --out runs
py run_evals.py --compare runs
```

One "arm" is one copy of the skill. Each gets a throwaway project dir holding that copy under its own name plus its own scratch vault, so a run can never touch a real vault, and `layout.ps1` / `open_note.ps1` are stubbed in both arms so a suite of headless runs cannot tile the actual desktop. Every eval runs one headless `claude -p` turn budget; the transcript captures assistant text **and every tool call**, because the tool calls are the real signal. A separate grader call scores it against `expected_output`.

The eval file is `{"skill_name": "...", "evals": [{"id": 0, "name": "...", "prompt": "...", "expected_output": "..."}]}`, where `expected_output` is prose saying what the agent should do and what it must not do, specific enough that a reader could check it against a transcript. The public repo does not ship one - an eval set encodes what its author wants the skill to do, so write your own rather than inherit somebody else's.

`--only 3,10` runs specific eval ids. `--timeout` is seconds per run (default 1200) - raise it for an eval whose behaviour renders a diagram or drives a browser, because that work is slow and a timeout is not a failure.

**Two limits, both real, neither a bug:**

- **The grader picks its own denominator.** It decides how many requirements an `expected_output` contains and does not decide the same way twice, so the same eval scores out of 12 in one arm and 11 in the other. One eval moving is usually that, not a regression. Quote the aggregate percentage; use the per-eval column only to pick a transcript worth reading. `0/0` means the grader itemised nothing, not a perfect or a failing score.
- **One headless run is a thin slice** of a skill built for a long two-person session, so absolute scores are low and mean little on their own. The comparison between two arms is the measurement.

An eval that checks work the skill now delegates to a subagent will read as unmet: the parent transcript shows the spawn, not the subagent's own tool calls. That is a stale eval, not a regression - fix the eval.

`CLAUDE_CONFIG_DIR` is deliberately not used to isolate an arm. On Windows the OAuth token lives in the credential store tied to the default config dir, so `claude -p` under a throwaway config dir reports `Not logged in` and every run scores zero.

## layout.ps1

Tiles the two panes a session needs: the reading surface on the left, the terminal on the right. Windows only.

```
pwsh -File layout.ps1 [-Surface podium|obsidian] [-Split 0.5] [-TerminalProcess WindowsTerminal] [-TitleMatch Podium]
```

`-Surface` defaults to `surface` in `config.json`, falling back to `obsidian`. On `obsidian` it finds the Obsidian process; on `podium` it finds the browser window by title (`-TitleMatch`, default `Podium`, which is what the patched `lavish-axi` puts in the titlebar), falling back to any Chrome, Edge, Firefox or Brave window so an unpatched install still gets placed rather than silently skipped.

Uses the primary monitor's **working area**, so nothing ends up under the taskbar, and restores a maximised window first because `MoveWindow` is ignored otherwise. Focus is left in the terminal, which is where the session is driven from. `-Split` is the fraction given to the left pane; raise it for a diagram-heavy session.

The placement line is printed with `Write-Host`, not `Write-Output`: the caller assigns the function's result, so `Write-Output` was being captured into that variable and the script reported nothing at all on success.

The terminal is found by process name: `terminal_process` from `config.json` if set, otherwise `WindowsTerminal`, `wezterm-gui`, `alacritty`, then `conhost`. Override with `-TerminalProcess`.

Exit 0 means both were placed. Exit 1 means one was not running - it names which, and still places the other.

## open_note.ps1

Opens a vault note in Obsidian and raises the window past the terminal. Windows only, and only for `surface: obsidian` - on a podium session use `podium.py open`, and do not raise Obsidian at all.

```
pwsh -File open_note.ps1 -Note "<learning_dir>/master-theorem"
```

`-Note` is vault-relative, forward slashes, no `.md`. `-Vault` and `-VaultRoot` default to `obsidian_vault_name` and `vault_root` from `config.json`. The script escapes the path, so spaces and slashes survive, and it pairs `SetForegroundWindow` with `AttachThreadInput` because Windows otherwise refuses a background process the foreground.

Exit 0 means the window title confirms the note is open and in front. Exit 1 means the note file does not exist - **create it first**, the `obsidian://` URI navigates but never creates. Exit 2 means Obsidian never reported the note in its title within `-TimeoutSec` (default 25).
