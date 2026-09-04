# claude-learn

A Claude Code skill that teaches you one thing at a time, at the exact edge of what you already know.

Ask it to teach you something and it does three things in order. It **probes** - graded multiple-choice questions that binary-search until every prerequisite strand has both a floor (something at that level you get right) and a ceiling (something you get wrong or honestly do not know), because one side alone measures nothing. It **maps** - a mermaid dependency DAG of the concepts, roots stress-tested so the lesson is never founded on a disguised theorem, presented for your approval before a word is taught. Then it **teaches**, one reasoning step per turn, motivating every move so nothing appears from nowhere, and checking each step with a free-response question you have to produce the answer to. Everything lands in a Markdown note in your vault, which renders the LaTeX and the diagrams, while you answer in the terminal. Missed checks become spaced-repetition cards written straight into the note as you go.

## Install

**Windows**

```powershell
git clone https://github.com/RyanCollinsAI/claude-learn.git
cd claude-learn
.\install.ps1 -VaultRoot C:\path\to\your\vault
```

**macOS / Linux**

```bash
git clone https://github.com/RyanCollinsAI/claude-learn.git
cd claude-learn
./install.sh --vault-root /path/to/your/vault
```

The installer copies the skill to `~/.claude/skills/learn`, copies `commands/learn.md` to `~/.claude/commands/learn.md` so `/learn` exists, writes a `config.json` for your machine, and reports which dependencies are present. An existing `config.json` is never overwritten.

Then, in Claude Code: **"teach me the master theorem"**, or `/learn <anything>`.

## What you need

| | | |
|---|---|---|
| **Claude Code** | required | The skill is a `SKILL.md` it reads. |
| **Python 3.9+** | required for `quiz.py` | Standard library only. No pip installs. |
| **A Markdown vault** | required | Any folder. [Obsidian](https://obsidian.md) is what it is built around, because it renders LaTeX and mermaid natively and reloads a file the moment it changes on disk. Any editor that does both works. |
| **Chrome or Chromium** | optional | Only the two render tools drive it, headless, to check a diagram before it is embedded. Found automatically; set `chrome_path` if it is somewhere unusual. |
| **Pillow** | optional | Tightens the diagram crop. Without it the PNG is a little loose, never clipped. |
| **PowerShell** | optional, Windows | `layout.ps1` and `open_note.ps1` tile and raise the two windows. The skill works without them; you just switch windows yourself. |

## The two panes

Obsidian on the left renders everything - the node text, the question, the options, the grade, the LaTeX and the diagrams. The terminal on the right takes every answer. Nothing opens a third window: a popup would steal focus from the pane you type in, and it could not render maths.

That split is why `quiz.py` exists rather than the skill just asking in prose. `ask` writes the question into the note **and the answer key to a sidecar file, before the question is visible**. You type a number in the terminal, `grade` scores it against what was already on disk, and the result is written back into the note. The grade cannot bend to what you picked. A targeted wrong option also tells the teacher *which* misconception you hold, which is far faster than asking you to explain your reasoning.

## Why it is shaped like this

Nothing here is decorative. Each rule is in the skill because leaving it out produced a worse session:

- **The probe has no question cap.** A cap makes the probe stop to feel fast and costs the whole session instead. It stops on the bracket - every strand with both sides found - and nothing else.
- **A run of correct answers is not "done".** It is a floor with no ceiling, which means the questions were too easy. Escalate until something breaks.
- **One wrong answer is not "done" either.** One miss is a single coordinate. It could be a slip, an isolated gap, or a systematic misconception, and only the third has to be dislodged rather than topped up.
- **Unconditional truths first.** The brain will not commit to a fact that something deeper might contradict, so start from ground that can be accepted at face value with no caveats.
- **"How could I have discovered this?"** A fact with no visible reason it had to be this way feels arbitrary, and arbitrary facts do not stick. Every step gets motivated.
- **Side questions go to a subagent.** A tangent answered in the main thread breaks the teaching thread and leaves its research in the window for the rest of the session. It lands in the note under its own heading instead, and the pending question is re-asked verbatim.
- **A rung advances only on two correct answers on two different days.** Relearning across separate sessions is what makes it stick; one correct answer holds the interval.
- **Nothing is published until somebody looked at the render.** Reading SVG or mermaid source back is not looking at it. A reversed arrow asserts something false about the subject and is invisible in the markup.

## Configuration

`config.example.json` documents every key. All of them are optional - with no `config.json` at all the vault is the current directory and everything else derives from it.

| Key | Default | What it does |
|---|---|---|
| `vault_root` | the current directory | Absolute root. Every path below is relative to it. |
| `obsidian_vault_name` | basename of `vault_root` | The vault's name inside Obsidian, for `obsidian://` URIs. |
| `learning_dir` | `Learning` | Session notes that do not belong to a course. |
| `course_learning_dir` | *(empty - feature off)* | Pattern for a course's notes. `{course}` is the folder name on disk. |
| `learner_file` | `<learning_dir>/LEARNER.md` | Who is being taught, and what they have demonstrated. Read before every probe. |
| `quiz_log_dir` | `<learning_dir>/.quiz-log` | Answer-key sidecars and the graded-answer log. A dot folder, so Obsidian ignores it. |
| `visuals_dir` | `<learning_dir>/visuals` | SVGs embedded in session notes. |
| `chrome_path` | first install path that exists | The browser the render tools drive headless. |
| `terminal_process` | first of WindowsTerminal, wezterm-gui, alacritty, conhost | Which window `layout.ps1` puts on the right. |

Any key can be overridden for one run with an environment variable: `LEARN_VAULT_ROOT`, `LEARN_LEARNING_DIR`, and so on.

## The learner profile

`<learner_file>` is the one file that makes the probe get shorter every session. It records what you have **demonstrated** - answered a graded question on, not claimed - which analogies landed, and which needed rewording. The skill appends to it at the end of every session and reads it before the next probe, skipping anything already answered.

It is also where anything personal belongs. `SKILL.md` says nothing about any particular learner on purpose, so the same skill file works for everybody. Write who you are, what you already know, and how you like to be taught into the profile instead.

A fresh probe outranks the profile. If you miss something the file says you demonstrated, the probe wins and the file gets corrected. Knowledge decays.

## Pre-built courses

`skills/learn/courses/*.md` is one vetted curriculum each - a real reading path in a real order, not a generated outline. The skill globs the folder and skips the probe when the ask matches one. The folder ships empty; drop your own in, and state at the top of the file what it covers and what should trigger it.

## The tools

`skills/learn/tools/README.md` documents all seven in full. In short:

```
quiz.py           ask/grade one question: key to disk first, question into the note, number in the terminal
render_mermaid.py mermaid source -> tightly-cropped PNG, so a diagram is looked at before it is embedded
render_svg.py     the same for a hand-written SVG
test_render.py    regression test for both renderers; margins are measured, not asserted
learnlib.py       the shared config loader
layout.ps1        tiles Obsidian left, terminal right (Windows)
open_note.ps1     opens a note in Obsidian and actually raises the window (Windows)
```

None of them touch the network at run time. `mermaid.min.js` is vendored for exactly that reason.

## What it does not do

- It does not install any Python package, call any API of its own, or send anything anywhere.
- It does not manage a review schedule outside your notes. Cards are Obsidian Tasks lines in the session note, due dates edited in place, and they are asked when you next open that topic rather than by a daemon.
- It does not submit anything, anywhere. It teaches; the work stays yours.

## Layout

```
README.md
install.ps1 / install.sh     copy the skill, write config.json, check dependencies
commands/learn.md            the /learn slash command the installer copies to ~/.claude/commands/
config.example.json          every key, documented
tools/write_config.py        one helper install.sh calls
skills/learn/
  SKILL.md                   what the teaching session actually reads
  tools/                     the seven CLI tools, plus vendored mermaid
  courses/                   pre-built curricula; ships empty
CHANGELOG.md
```

## License

MIT. See LICENSE.
