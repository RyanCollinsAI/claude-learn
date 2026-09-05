"""quiz.py - a graded question, rendered in Obsidian, answered in the terminal.

Obsidian is the reading surface and the terminal is the input surface, so the
question goes in the note and the answer comes back as a typed number. No
popup, no third window, and full LaTeX in the question and the options because
Obsidian renders it.

The point of the tool is the pre-commitment. `ask` writes the answer key to a
sidecar file BEFORE the question is visible, so the grade cannot be decided
after seeing what the learner picked, and `grade` can only score against what
was already on disk.

Usage:
    py quiz.py ask   --spec q.json --note "<learning_dir>/master-theorem"
    py quiz.py grade --answer "2"  --note "<learning_dir>/master-theorem"

`--note` is vault-relative, forward slashes, no `.md`. The vault root and the
sidecar folder come from config.json - see learnlib.py.

Spec (JSON) for `ask`:
    {
      "question":      "required, one question, LaTeX welcome",
      "details":       "optional, italic line under the question",
      "options":       [{"label": "...", "value": "...", "description": "..."}],
      "correctAnswer": "value"  or  ["value", "value"],
      "explanation":   "required, written into the note after they answer",
      "multiSelect":   false,
      "shuffle":       true,
      "label":         "optional heading, e.g. Probe 3 - recursion trees"
    }

`grade --answer` accepts: "2", "b", "2,3" or "2 3" for multi-select, and
"0", "idk", "?" or "dont know" for an honest gap.

`grade --why "<text>"` is optional. It carries whatever reasoning they gave
alongside the pick, and it lands in the note beside that specific question
instead of being pooled into one end-of-session block, so a wrong pick's
reasoning is readable exactly where it happened.

Exit codes:
    0  worked
    2  the spec or the answer is invalid - the reason is on stderr
    3  `grade` found no pending question for that note
"""

import argparse
import json
import os
import random
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import learnlib

VAULT = learnlib.VAULT_ROOT
LOG_DIR = learnlib.vault_path(learnlib.QUIZ_LOG_DIR)
PENDING_MARK = "<!-- quiz:pending -->"
DONT_KNOW = {"0", "idk", "?", "dont know", "don't know", "no idea", "unsure"}


def fail(msg, code=2):
    sys.stderr.write("quiz: " + msg + "\n")
    sys.exit(code)


def note_path(rel):
    path = os.path.join(VAULT, rel.replace("/", os.sep))
    if not path.endswith(".md"):
        path += ".md"
    return path


def slug_of(rel):
    return re.sub(r"[^a-z0-9-]+", "-", os.path.basename(rel).replace(".md", "").lower())


def pending_path(rel):
    return os.path.join(LOG_DIR, slug_of(rel) + ".pending.json")


def log_path(rel):
    return os.path.join(LOG_DIR, slug_of(rel) + ".jsonl")


def append_note(path, text):
    if not os.path.exists(path):
        fail("no such note: %s. Create it before asking a question." % path)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(text)


# --------------------------------------------------------------------------
# ask
# --------------------------------------------------------------------------

def normalise(spec):
    question = (spec.get("question") or "").strip()
    if not question:
        fail("question is required")

    explanation = (spec.get("explanation") or "").strip()
    if not explanation:
        fail("explanation is required - say why the correct answer is correct")

    options, seen = [], set()
    for opt in spec.get("options") or []:
        if isinstance(opt, str):
            opt = {"label": opt}
        label = (opt.get("label") or "").strip()
        if not label:
            continue
        value = (opt.get("value") or label).strip()
        if value in seen:
            fail('duplicate option value "%s"' % value)
        seen.add(value)
        if label.lower().rstrip(".!?") in (
            "i don't know", "i dont know", "not sure", "i'm not sure",
            "im not sure", "unsure", "no idea",
        ):
            fail('do not write your own "I don\'t know" option - one is always offered')
        options.append({
            "label": label,
            "value": value,
            "description": (opt.get("description") or "").strip(),
        })

    if len(options) < 2:
        fail("give at least 2 real options")

    correct = spec.get("correctAnswer")
    if correct is None:
        fail("correctAnswer is required - pass the option value, not a position")
    if isinstance(correct, str):
        correct = [correct]
    correct = [str(c).strip() for c in correct]
    unknown = [c for c in correct if c not in seen]
    if unknown:
        fail("correctAnswer %s matches no option value. Values are: %s"
             % (unknown, sorted(seen)))

    multi = bool(spec.get("multiSelect"))
    if not multi and len(correct) > 1:
        fail("several correct answers given - set multiSelect: true")

    if spec.get("shuffle", True):
        random.shuffle(options)

    return {
        "question": question,
        "details": (spec.get("details") or "").strip(),
        "label": (spec.get("label") or "").strip(),
        "options": options,
        "correct": correct,
        "explanation": explanation,
        "multi": multi,
    }


def render_question(q):
    out = ["\n"]
    if q["label"]:
        out.append("### %s\n\n" % q["label"])
    out.append("%s\n\n" % q["question"])
    if q["details"]:
        out.append("*%s*\n\n" % q["details"])
    for i, opt in enumerate(q["options"], start=1):
        out.append("%d. %s\n" % (i, opt["label"]))
        if opt["description"]:
            out.append("   - %s\n" % opt["description"])
    out.append("\n**0.** I don't know - an honest gap, not a wrong answer.\n\n")
    hint = "Type every correct number in the terminal, comma separated." if q["multi"] \
        else "Type the number in the terminal."
    # The marker plus the one-line hint under it is the pending region.
    # Grading replaces exactly that and keeps whatever follows, because a
    # sidebar callout may be appended after it while the question is open.
    out.append("%s\n> %s\n" % (PENDING_MARK, hint))
    return "".join(out)


def do_ask(args):
    raw = sys.stdin.read() if args.stdin else open(args.spec, encoding="utf-8").read()
    try:
        spec = json.loads(raw)
    except json.JSONDecodeError as exc:
        fail("the spec is not valid JSON: %s" % exc)

    q = normalise(spec)
    path = note_path(args.note)

    os.makedirs(LOG_DIR, exist_ok=True)
    pending = pending_path(args.note)
    if os.path.exists(pending):
        fail("a question is already pending for this note. Grade it first.")

    append_note(path, render_question(q))
    with open(pending, "w", encoding="utf-8") as fh:
        json.dump({**q, "note": args.note, "asked": time.strftime("%Y-%m-%dT%H:%M:%S")},
                  fh, ensure_ascii=False)

    # The terminal gets a pointer only. The question itself lives in the note,
    # so they read it on the left and answer on the right.
    n = len(q["options"])
    print("%s -> 1-%d, or 0 for I don't know. Say why too, if you want."
          % (q["label"] or "Question", n))


# --------------------------------------------------------------------------
# grade
# --------------------------------------------------------------------------

def parse_answer(text, count, multi):
    text = text.strip().lower()
    if text in DONT_KNOW:
        return "dontKnow", []
    picks = [p for p in re.split(r"[\s,]+", text) if p]
    if not picks:
        fail("no answer given")
    idx = []
    for p in picks:
        if p.isdigit():
            n = int(p)
        elif len(p) == 1 and p.isalpha():
            n = ord(p) - ord("a") + 1
        else:
            fail('cannot read "%s" as an answer' % p)
        if n == 0:
            return "dontKnow", []
        if not 1 <= n <= count:
            fail("answer %d is out of range - there are %d options" % (n, count))
        idx.append(n)
    if not multi and len(idx) > 1:
        fail("this question takes one answer, got %d" % len(idx))
    return "answered", sorted(set(idx))


def render_feedback(q, result):
    mark = {"correct": "**Correct.**",
            "incorrect": "**Not quite.**",
            "dontKnow": "**Noted - an honest gap.**"}[result["result"]]
    lines = ["\n%s" % mark]
    if result["result"] == "incorrect":
        lines.append(" You picked %s." % ", ".join(str(i) for i in result["selectedIndexes"]))
    correct_nums = [str(i) for i, o in enumerate(q["options"], start=1)
                    if o["value"] in set(q["correct"])]
    lines.append(" The answer is %s: %s.\n\n"
                 % (", ".join(correct_nums), "; ".join(result["correctLabels"])))
    lines.append("> %s\n" % q["explanation"].replace("\n", "\n> "))
    # Their own reasoning, if they gave any, sits with the question it belongs
    # to rather than in one pooled block at the end of the session.
    if result.get("why"):
        lines.append("\n> [!quote]- Your reasoning\n> %s\n"
                     % result["why"].replace("\n", "\n> "))
    return "".join(lines)


def do_grade(args):
    pending = pending_path(args.note)
    if not os.path.exists(pending):
        fail("no pending question for %s" % args.note, code=3)
    with open(pending, encoding="utf-8") as fh:
        q = json.load(fh)

    kind, idx = parse_answer(args.answer, len(q["options"]), q["multi"])
    correct = set(q["correct"])
    values = [q["options"][i - 1]["value"] for i in idx]

    if kind == "dontKnow":
        outcome = "dontKnow"
    elif set(values) == correct:
        outcome = "correct"
    else:
        outcome = "incorrect"

    result = {
        "result": outcome,
        "question": q["question"],
        "label": q["label"],
        "selected": values,
        "selectedLabels": [q["options"][i - 1]["label"] for i in idx],
        "selectedIndexes": idx,
        "correctAnswer": q["correct"],
        "correctLabels": [o["label"] for o in q["options"] if o["value"] in correct],
        "displayOrder": [{"index": i, "label": o["label"], "value": o["value"]}
                         for i, o in enumerate(q["options"], start=1)],
        "multiSelect": q["multi"],
        "why": (args.why or "").strip(),
        "raw": args.answer,
        "asked": q.get("asked"),
        "graded": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }

    path = note_path(args.note)
    body = open(path, encoding="utf-8").read()
    block = render_feedback(q, result)
    if PENDING_MARK in body:
        head, _, tail = body.rpartition(PENDING_MARK)
        # Drop only the marker and its one-line "type the number" hint.
        # Anything after that (a sidebar callout appended while the
        # question was open) must survive the grade - on 2026-09-01 two
        # sidebars were silently wiped because this replaced to end of file.
        tail = re.sub(r"^\n?> [^\n]*\n?", "", tail, count=1)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(head.rstrip("\n") + "\n" + block + (("\n" + tail.lstrip("\n")) if tail.strip() else ""))
    else:
        append_note(path, block)

    with open(log_path(args.note), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(result, ensure_ascii=False) + "\n")
    os.remove(pending)

    print(json.dumps(result, ensure_ascii=False, indent=2))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("ask", help="write a graded question into the note")
    a.add_argument("--spec", help="path to a JSON spec file")
    a.add_argument("--stdin", action="store_true", help="read the spec from stdin")
    a.add_argument("--note", required=True, help="vault-relative note path")
    a.set_defaults(func=do_ask)

    g = sub.add_parser("grade", help="grade the typed answer and write the result")
    g.add_argument("--answer", required=True, help='what they typed, e.g. "2" or "2,3" or "idk"')
    g.add_argument("--why", default="", help="optional - their reasoning, kept beside this question")
    g.add_argument("--note", required=True, help="vault-relative note path")
    g.set_defaults(func=do_grade)

    args = ap.parse_args()
    if args.cmd == "ask" and not args.spec and not args.stdin:
        fail("ask needs --spec <file.json> or --stdin")
    args.func(args)


if __name__ == "__main__":
    main()
