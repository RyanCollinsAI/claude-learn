"""run_evals.py - run the skill's behaviour evals, and diff two runs.

`evals/evals.json` describes what the skill should make an agent DO. Nothing ran
it until this file existed, which made the eval set a dead feature: a list of
expectations nobody checked. This runs it.

One "arm" is one copy of the skill under test. Each arm gets a throwaway project
directory holding that copy under its own name plus its own scratch vault, so a
run can never touch a real vault. Every eval runs one headless `claude -p` turn
budget and the whole stream is captured - assistant text AND every tool call,
because the tool calls are the real signal. A separate grader call scores that
transcript against the eval's `expected_output`.

Typical use is a before/after on a change to SKILL.md:

    # the version you are changing from, e.g. extracted from git
    py run_evals.py --arm before --skill <old skill dir> --evals evals/evals.json --out runs
    # the working copy
    py run_evals.py --arm after  --skill <this skill dir>  --evals evals/evals.json --out runs
    py run_evals.py --compare runs

READ THE OUTPUT WITH CARE. Two limits are real and neither is a bug:

1. **The grader picks its own denominator.** It decides how many requirements an
   `expected_output` contains, and it does not decide the same way twice - the
   same eval can score out of 12 in one arm and out of 11 in the other. A single
   eval moving is usually that, not a regression. Quote the aggregate percentage;
   treat the per-eval column as a pointer to a transcript worth reading.
   A `0/0` means the grader itemised nothing, not a perfect or a failing score.
2. **One headless run is a thin slice of a skill built for a long two-person
   session.** Absolute scores are low and mean little. The comparison between two
   arms of the same suite is the measurement.

An eval whose behaviour does real work - rendering a diagram, driving a browser -
can exceed the per-run timeout. Raise `--timeout` for those rather than reading a
timeout as a failure.

The eval file is `{"skill_name": "...", "evals": [{"id": 0, "name": "...",
"prompt": "...", "expected_output": "..."}]}`. `expected_output` is prose: say
what the agent should do and what it must not do, and be specific enough that a
reader could check it against a transcript.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

CLAUDE = shutil.which("claude") or "claude"

FORCE = ("You have a skill named {name}. For this request, invoke it with the "
         "Skill tool as your first action and then follow it exactly. Do not "
         "invoke any other skill.")

GRADER = """You are grading one transcript of an agent that had a skill available.

The transcript below is everything the agent said and every tool it called.

EXPECTED BEHAVIOUR:
{expected}

TRANSCRIPT:
{transcript}

Score each distinct requirement in EXPECTED BEHAVIOUR (both the "should" items
and the "must NOT" items) as met or not met, judging only from the transcript.
A requirement the transcript gives no evidence either way for is NOT met.
Tool calls count as evidence. A stated intention to do a thing does not.

Reply with ONLY a JSON object, no prose and no code fence:
{{"met": <int>, "total": <int>, "failed": ["<short label>", ...]}}
"""

STUB = ("param([Parameter(ValueFromRemainingArguments)]$Rest)\n"
        "Write-Output '%s'\nexit 0\n")


def build_arm(skill_src, arm_dir, skill_name, stub_windows_tools=True):
    """A throwaway project dir holding this arm's copy of the skill.

    CLAUDE_CONFIG_DIR is deliberately not used to isolate the arm. On at least
    one platform the OAuth token lives in the OS credential store tied to the
    default config dir, so `claude -p` under a throwaway config dir reports
    "Not logged in" and every run scores zero. A project-level skill isolates
    just as well and keeps the login.

    The skill is installed under a per-arm NAME so two arms cannot collide with
    each other, or with a copy of the same skill already installed on the
    machine.
    """
    proj = os.path.join(arm_dir, "proj")
    vault = os.path.join(proj, "vault")
    skills = os.path.join(proj, ".claude", "skills", skill_name)
    os.makedirs(os.path.join(vault, "Learning"), exist_ok=True)
    os.makedirs(os.path.dirname(skills), exist_ok=True)
    if os.path.isdir(skills):
        shutil.rmtree(skills)
    shutil.copytree(skill_src, skills,
                    ignore=shutil.ignore_patterns("__pycache__", "evals", "courses"))

    md = os.path.join(skills, "SKILL.md")
    with open(md, encoding="utf-8") as fh:
        body = fh.read()
    with open(md, "w", encoding="utf-8") as fh:
        fh.write(body.replace("\nname: learn\n", "\nname: %s\n" % skill_name, 1))

    with open(os.path.join(skills, "config.json"), "w", encoding="utf-8") as fh:
        json.dump({
            "vault_root": vault.replace("\\", "/"),
            "obsidian_vault_name": "scratch",
            "learning_dir": "Learning",
            "course_learning_dir": "",
            "learner_file": "Learning/LEARNER.md",
            "quiz_log_dir": "Learning/.quiz-log",
            "visuals_dir": "Learning/visuals",
        }, fh, indent=2)
    with open(os.path.join(vault, "Learning", "LEARNER.md"), "w", encoding="utf-8") as fh:
        fh.write("# Learner\n\nA CS undergraduate. Holds big-O and basic recursion.\n")

    # layout.ps1 and open_note.ps1 drive real windows. A suite of headless runs
    # would tile the actual desktop and open notes in the real Obsidian, so both
    # arms get identical stubs. The CALL still appears in the transcript, which
    # is what the grader reads, and nothing outside this folder moves.
    if stub_windows_tools:
        for stub, says in (("layout.ps1", "layout: panes tiled (stubbed for eval)"),
                           ("open_note.ps1", "open_note: note raised (stubbed for eval)")):
            path = os.path.join(skills, "tools", stub)
            if os.path.exists(path):
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(STUB % says)
    return proj


def child_env():
    env = dict(os.environ)
    env.pop("CLAUDECODE", None)          # let claude -p nest inside claude
    env.pop("CLAUDE_CODE_ENTRYPOINT", None)
    return env


def transcript_of(stream):
    """Flatten stream-json into readable text plus every tool call."""
    out = []
    for line in stream.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if ev.get("type") != "assistant":
            continue
        for block in ev.get("message", {}).get("content", []) or []:
            if block.get("type") == "text" and block.get("text", "").strip():
                out.append(block["text"])
            elif block.get("type") == "tool_use":
                arg = json.dumps(block.get("input", {}), ensure_ascii=False)
                out.append("[TOOL %s] %s" % (block.get("name"), arg[:1500]))
    return "\n\n".join(out)


def run_one(ev, proj, out_dir, turns, skill_name, model, timeout):
    name = "%02d-%s" % (ev["id"], ev["name"])
    # A network blip mid-run truncates a transcript and scores it near zero for
    # reasons that have nothing to do with the skill. Retry those.
    text = ""
    for attempt in range(3):
        proc = subprocess.run(
            [CLAUDE, "-p", ev["prompt"], "--model", model,
             "--append-system-prompt", FORCE.format(name=skill_name),
             "--max-turns", str(turns), "--permission-mode", "bypassPermissions",
             "--output-format", "stream-json", "--verbose"],
            cwd=proj, env=child_env(), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout,
        )
        text = transcript_of(proc.stdout) or "(no assistant output)\n" + proc.stderr[:2000]
        if "API Error" not in text and "Not logged in" not in text:
            break
        print("  %-36s retry %d (API error)" % (ev["name"], attempt + 1), flush=True)
    with open(os.path.join(out_dir, name + ".transcript.txt"), "w", encoding="utf-8") as fh:
        fh.write(text)

    grade = subprocess.run(
        [CLAUDE, "-p", GRADER.format(expected=ev["expected_output"],
                                     transcript=text[:60000]),
         "--model", model, "--max-turns", "1"],
        cwd=proj, env=child_env(), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=600,
    )
    raw = grade.stdout.strip()
    start, end = raw.find("{"), raw.rfind("}")
    try:
        parsed = json.loads(raw[start:end + 1])
        score = {"met": int(parsed["met"]), "total": int(parsed["total"]),
                 "failed": parsed.get("failed", [])}
    except Exception:
        score = {"met": 0, "total": 0, "failed": ["GRADER UNPARSEABLE: " + raw[:200]]}
    score.update(id=ev["id"], name=ev["name"], loaded=skill_name in text)
    print("  %-36s %2d/%-2d" % (ev["name"], score["met"], score["total"]), flush=True)
    return score


def do_run(a):
    arm_dir = os.path.join(a.out, a.arm)
    os.makedirs(arm_dir, exist_ok=True)
    skill_name = "learn-" + a.arm
    proj = build_arm(a.skill, arm_dir, skill_name)

    with open(a.evals, encoding="utf-8") as fh:
        evals = json.load(fh)["evals"]
    if a.only:
        keep = {int(x) for x in a.only.split(",")}
        evals = [e for e in evals if e["id"] in keep]

    print("arm %s (%s) - %d evals" % (a.arm, skill_name, len(evals)), flush=True)
    results = []
    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        futures = {pool.submit(run_one, ev, proj, arm_dir, a.turns, skill_name,
                               a.model, a.timeout): ev for ev in evals}
        for fut in as_completed(futures):
            ev = futures[fut]
            try:
                results.append(fut.result())
            except Exception as exc:
                results.append({"id": ev["id"], "name": ev["name"], "met": 0,
                                "total": 0, "failed": ["RUN ERROR: %s" % exc],
                                "loaded": False})
                print("  %-36s ERROR %s" % (ev["name"], exc), flush=True)

    results.sort(key=lambda r: r["id"])
    met = sum(r["met"] for r in results)
    total = sum(r["total"] for r in results)
    summary = {"arm": a.arm, "skill": skill_name, "met": met, "total": total,
               "pct": round(100.0 * met / total, 1) if total else 0.0,
               "loaded": sum(1 for r in results if r["loaded"]),
               "results": results}
    with open(os.path.join(a.out, a.arm + ".json"), "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)
    print("ARM %s: %d/%d (%.1f%%), skill loaded in %d/%d"
          % (a.arm, met, total, summary["pct"], summary["loaded"], len(results)))
    return 0


def do_compare(out):
    b = json.load(open(os.path.join(out, "before.json"), encoding="utf-8"))
    a = json.load(open(os.path.join(out, "after.json"), encoding="utf-8"))
    bi = {r["id"]: r for r in b["results"]}
    ai = {r["id"]: r for r in a["results"]}

    print("| # | eval | before | after | |")
    print("|---|---|---|---|---|")
    better = worse = same = 0
    for i in sorted(set(bi) & set(ai)):
        rb, ra = bi[i], ai[i]
        pb = rb["met"] / rb["total"] if rb["total"] else 0.0
        pa = ra["met"] / ra["total"] if ra["total"] else 0.0
        if pa > pb + 0.001:
            mark, better = "up", better + 1
        elif pa < pb - 0.001:
            mark, worse = "down", worse + 1
        else:
            mark, same = "", same + 1
        print("| %d | %s | %d/%d | %d/%d | %s |"
              % (i, rb["name"], rb["met"], rb["total"], ra["met"], ra["total"], mark))
    print()
    print("before %d/%d (%.1f%%)  after %d/%d (%.1f%%)"
          % (b["met"], b["total"], b["pct"], a["met"], a["total"], a["pct"]))
    print("per-eval: better %d, worse %d, unchanged %d" % (better, worse, same))
    print()
    print("The grader sets its own denominator per run, so a single eval moving is "
          "usually that rather than a regression. Quote the aggregate; use the "
          "per-eval column to pick a transcript worth reading.")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--compare", metavar="OUT_DIR",
                    help="print a before/after table from OUT_DIR and exit")
    ap.add_argument("--arm", help="a name for this run, e.g. before or after")
    ap.add_argument("--skill", help="the skill directory to test (holds SKILL.md)")
    ap.add_argument("--evals", help="path to evals.json")
    ap.add_argument("--out", help="directory for transcripts and results")
    ap.add_argument("--only", help="comma-separated eval ids to run")
    ap.add_argument("--model", default="sonnet")
    ap.add_argument("--turns", type=int, default=12)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--timeout", type=int, default=1200,
                    help="seconds per run; raise it for evals that render or browse")
    a = ap.parse_args()

    if a.compare:
        return do_compare(a.compare)
    missing = [f for f in ("arm", "skill", "evals", "out") if not getattr(a, f)]
    if missing:
        ap.error("need --" + ", --".join(missing) + " (or --compare)")
    return do_run(a)


if __name__ == "__main__":
    sys.exit(main())
