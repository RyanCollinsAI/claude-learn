"""session.py - what is still open, and how the checks are actually going.

Two things the skill used to hold only in its head, and therefore lost.

**A pending check.** Three of five real sessions died on a question nobody ever
came back to. A check is now written to disk when it is asked and cleared when
it is graded, so `session.py status` at the start of the next session surfaces
it before anything else. `quiz.py` already does this for graded questions; this
does it for the free-response checks, which are most of them.

**The running tally.** "Aim for about three checks in four correct" is a rule
you cannot follow from memory. Every graded check is counted, so the tally is a
number you can read out every four or five nodes instead of a vibe.

    py session.py check open  --note "<dir>/master-theorem" --node 3 \\
                              --question "derive the leaf-row total"
    py session.py check close --note "<dir>/master-theorem" --grade partial
    py session.py status                      everything open, oldest first
    py session.py status --note "<dir>/master-theorem"
    py session.py tally --note "<dir>/master-theorem"

`--note` is vault-relative, forward slashes, no `.md` - the same argument
quiz.py takes. State lives in `<quiz_log_dir>/`, a dot folder, beside the quiz
sidecars.

Exit codes:
    0  worked
    2  bad arguments
    3  `check close` found nothing open
    4  `status` found at least one pending item - so a session-start hook can
       branch on it. Nothing is wrong; it is a flag, not an error.
"""

import argparse
import glob
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import learnlib

LOG_DIR = learnlib.vault_path(learnlib.QUIZ_LOG_DIR)
GRADES = ("correct", "partial", "off")


def fail(msg, code=2):
    sys.stderr.write("session: " + msg + "\n")
    sys.exit(code)


def slug_of(rel):
    base = os.path.basename(rel)
    if base.endswith(".md"):
        base = base[:-3]
    return re.sub(r"[^a-z0-9-]+", "-", base.lower())


def check_path(rel):
    return os.path.join(LOG_DIR, slug_of(rel) + ".check.json")


def tally_path(rel):
    return os.path.join(LOG_DIR, slug_of(rel) + ".tally.json")


def read(path, default):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def write(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2)


def age_of(stamp):
    """A human age from an ISO stamp, or "" when it cannot be read."""
    try:
        then = time.mktime(time.strptime(stamp, "%Y-%m-%dT%H:%M:%S"))
    except (ValueError, TypeError):
        return ""
    secs = max(0, int(time.time() - then))
    if secs < 3600:
        return "%dm" % (secs // 60)
    if secs < 86400:
        return "%dh" % (secs // 3600)
    return "%dd" % (secs // 86400)


# --------------------------------------------------------------------------
# the tally
# --------------------------------------------------------------------------

def bump(rel, grade):
    """Count one graded check. Never raises - a tally is worth less than the
    grade it is counting, so a broken tally must not kill a session."""
    try:
        t = read(tally_path(rel), {})
        t[grade] = int(t.get(grade, 0)) + 1
        t["last"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        write(tally_path(rel), t)
        return t
    except Exception:
        return {}


def tally_line(rel):
    t = read(tally_path(rel), {})
    c, p, o = int(t.get("correct", 0)), int(t.get("partial", 0)), int(t.get("off", 0))
    n = c + p + o
    if not n:
        return "tally: nothing graded yet"
    line = "tally: %d correct, %d partial, %d off  (%d checks, %.0f%% correct)" % (
        c, p, o, n, 100.0 * c / n)
    # The interpretation, so the number is not just a number. These are the
    # skill's own thresholds: about three in four is the target band.
    if n >= 4:
        rate = c / float(n)
        if rate > 0.9:
            line += "  -> too easy, merge nodes"
        elif rate < 0.5:
            line += "  -> the map is likely missing a prerequisite"
    return line


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------

def cmd_check(a):
    if a.action == "open":
        if not a.question:
            fail("check open needs --question")
        write(check_path(a.note), {
            "note": a.note,
            "node": str(a.node or ""),
            "question": a.question,
            "opened": time.strftime("%Y-%m-%dT%H:%M:%S"),
        })
        print("check open: %s node %s" % (a.note, a.node or "?"))
        return 0

    path = check_path(a.note)
    if not os.path.isfile(path):
        fail("no open check for %s" % a.note, code=3)
    if a.grade not in GRADES:
        fail("--grade must be one of: %s" % ", ".join(GRADES))
    state = read(path, {})
    os.remove(path)
    t = bump(a.note, a.grade)
    del t
    print("check closed %s: %s (open %s)"
          % (a.grade, state.get("node") or "?", age_of(state.get("opened")) or "?"))
    print(tally_line(a.note))
    return 0


def cmd_status(a):
    """Everything still waiting on the learner, oldest first."""
    rows = []
    if a.note:
        candidates = [check_path(a.note),
                      os.path.join(LOG_DIR, slug_of(a.note) + ".pending.json")]
    else:
        candidates = sorted(glob.glob(os.path.join(LOG_DIR, "*.check.json")) +
                            glob.glob(os.path.join(LOG_DIR, "*.pending.json")))
    for path in candidates:
        if not os.path.isfile(path):
            continue
        d = read(path, {})
        quiz = path.endswith(".pending.json")
        rows.append({
            "kind": "quiz" if quiz else "check",
            "note": d.get("note") or os.path.basename(path).split(".")[0],
            "node": d.get("label") if quiz else d.get("node"),
            "text": (d.get("question") or "").replace("\n", " ")[:90],
            "opened": d.get("asked") if quiz else d.get("opened"),
        })
    rows.sort(key=lambda r: r.get("opened") or "")

    if not rows:
        print("nothing open.")
        if a.note:
            print(tally_line(a.note))
        return 0

    print("%d open, oldest first:" % len(rows))
    for r in rows:
        age = age_of(r["opened"])
        print("  %-5s %-42s %-6s %s%s"
              % (r["kind"], r["note"], age or "?",
                 ("[%s] " % r["node"]) if r["node"] else "", r["text"]))
    print()
    print("Answer or clear the oldest before opening anything new.")
    if a.note:
        print(tally_line(a.note))
    return 4


def cmd_tally(a):
    print(tally_line(a.note))
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("check", help="open or close a free-response check")
    c.add_argument("action", choices=["open", "close"])
    c.add_argument("--note", required=True, help="vault-relative note path, no .md")
    c.add_argument("--node", default="", help="the node number or name it belongs to")
    c.add_argument("--question", default="", help="the check, for the reminder")
    c.add_argument("--grade", default="", help="correct | partial | off")
    c.set_defaults(func=cmd_check)

    s = sub.add_parser("status", help="everything still waiting on the learner")
    s.add_argument("--note", default="", help="just this note")
    s.set_defaults(func=cmd_status)

    t = sub.add_parser("tally", help="the running correct/partial/off count")
    t.add_argument("--note", required=True)
    t.set_defaults(func=cmd_tally)

    a = ap.parse_args()
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
