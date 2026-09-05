"""podium.py - the learner's page: open it, refresh it, read what they sent.

Podium is the Lavish editor (`lavish-axi`) showing one page per session. This
wraps it so SKILL.md can say "run `podium.py refresh`" after every node instead
of describing a window.

    py podium.py open    --note "<learning_dir>/master-theorem"
    py podium.py refresh --note "..."
    py podium.py poll    --note "..." [--reply "graded - node 4 is up"]
    py podium.py reply   --note "..." --text "..."     (poll, having spoken first)
    py podium.py end     --note "..."
    py podium.py url     --note "..."

`--note` is vault-relative, forward slashes, no `.md` - the same argument
quiz.py takes.

`poll` blocks until they send something. That is `lavish-axi poll`'s whole
design, so never kill it: run it as a background task if the harness caps a
foreground command, and re-run it if it dies. Queued feedback is never lost.
It prints one line per event:

    ANSWER 2 | WHY: the tree collapses geometrically
    NOTE <selector> | ...        an annotation on one element
    MESSAGE | ...                anything else they typed
    LAYOUT 3 warnings            fix the page before involving them again
    SESSION ended                they closed it

Exit codes:
    0  worked
    1  the note does not exist, or `lavish-axi` is not on PATH
    3  `poll` came back with nothing - the server went away
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import learnlib
import podium_page

NOISE = ("Still waiting", "Long-polling", "[lavish-axi]", "dom_snapshot:", "next_step:")
CTX_RE = re.compile(r"Context data:\s*(\{.*\})", re.S)


def fail(msg, code=1):
    sys.stderr.write("podium: " + msg + "\n")
    sys.exit(code)


def lavish(*args):
    """`lavish-axi` is an npm .CMD shim on Windows; CreateProcess cannot launch
    one directly (WinError 193), so a .cmd/.bat goes through cmd /c."""
    exe = shutil.which("lavish-axi")
    if not exe:
        fail("lavish-axi is not on PATH. Install it, or set surface to obsidian "
             "in config.json.")
    if os.name == "nt" and exe.lower().endswith((".cmd", ".bat")):
        return ["cmd", "/c", exe, *args]
    return [exe, *args]


def page_for(rel, refresh=True):
    if refresh:
        html, _ = podium_page.write_pages(rel)
        return html
    html = podium_page.page_paths(rel)[0]
    if not os.path.isfile(html):
        fail("no page yet for %s - run `podium.py open` first." % rel)
    return html


# --------------------------------------------------------------------------
# poll output -> one line per event
# --------------------------------------------------------------------------

def split_row(line):
    """One `"a","b",c` row -> fields. json handles the escapes lavish uses
    inside quoted fields; an unquoted field runs to the next comma."""
    out, i, n = [], 0, len(line)
    dec = json.JSONDecoder()
    while i < n:
        while i < n and line[i] in " \t":
            i += 1
        if i < n and line[i] == '"':
            try:
                val, i = dec.raw_decode(line, i)
            except ValueError:
                out.append(line[i:].strip('"'))
                break
            out.append(val)
        else:
            j = line.find(",", i)
            j = n if j < 0 else j
            out.append(line[i:j].strip())
            i = j
        while i < n and line[i] in " \t":
            i += 1
        if i < n and line[i] == ",":
            i += 1
    return out


def parse(out):
    """-> (prompts, layout warning count, session ended?)"""
    prompts, warns, ended = [], 0, False
    fields, in_prompts = [], False
    for line in out.splitlines():
        if any(m in line for m in NOISE):
            continue
        head = re.match(r"^(\w+)\[(\d+)\](?:\{([^}]*)\})?:", line.strip())
        if head:
            key, count = head.group(1), int(head.group(2))
            in_prompts = key == "prompts"
            fields = (head.group(3) or "").split(",") if in_prompts else []
            if key == "layout_warnings":
                warns = count
            continue
        if re.match(r"^\s*status:\s*ended", line):
            ended = True
        if line.strip().startswith("layout_warnings:") and "0" not in line:
            warns = max(warns, 1)
        if in_prompts and line.startswith(("  ", "\t")) and line.strip():
            if line.strip()[0] not in '"0123456789':
                in_prompts = False
                continue
            prompts.append(dict(zip(fields, split_row(line.strip()))))
    return prompts, warns, ended


def emit(p):
    """One prompt -> one line. The `data` the page attaches is the reliable
    path; the text shape is the fallback for something typed by hand."""
    text = (p.get("prompt") or p.get("text") or "").strip()
    m = CTX_RE.search(text)
    if m:
        try:
            d = json.loads(m.group(1))
            if d.get("kind") == "learn-answer":
                why = (d.get("why") or "").strip()
                print("ANSWER %s%s" % (d.get("answer", ""), (" | WHY: " + why) if why else ""),
                      flush=True)
                return
        except ValueError:
            pass
    body = text.split("\n\nContext data:")[0].strip()
    m = re.match(r"^ANSWER\s+([\d, ]+)(?:\s*\|\s*WHY:\s*(.*))?$", body, re.S)
    if m:
        why = (m.group(2) or "").strip()
        print("ANSWER %s%s" % (m.group(1).strip(), (" | WHY: " + why) if why else ""),
              flush=True)
        return
    sel = (p.get("selector") or "").strip()
    if sel:
        print("NOTE %s | %s" % (sel, body), flush=True)
    else:
        print("MESSAGE | %s" % body, flush=True)


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------

def cmd_open(a):
    html = page_for(a.note)
    r = subprocess.run(lavish(html), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=180)
    out = (r.stdout or "") + (r.stderr or "")
    m = re.search(r"""https?://[^\s"']+""", out)
    print(html)
    if m:
        print("URL: " + m.group(0))
    else:
        print(out.strip()[:800])
    return 0


def cmd_refresh(a):
    html, has_q = podium_page.write_pages(a.note)
    print(html + ("  [question open]" if has_q else ""))
    return 0


def cmd_url(a):
    html = page_for(a.note, refresh=False)
    r = subprocess.run(lavish(), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=60)
    for line in ((r.stdout or "") + (r.stderr or "")).splitlines():
        if os.path.basename(html) in line:
            m = re.search(r"""https?://[^\s"']+""", line)
            if m:
                print(m.group(0))
                return 0
    fail("no open Podium session for %s - run `podium.py open`." % a.note)


def cmd_poll(a):
    html = page_for(a.note, refresh=False)
    args = ["poll", html] + (["--agent-reply", a.reply] if a.reply else [])
    r = subprocess.run(lavish(*args), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    out = (r.stdout or "") + (r.stderr or "")
    if not out.strip():
        sys.stderr.write("podium: poll returned empty - is lavish-axi still up?\n")
        return 3
    prompts, warns, ended = parse(out)
    if warns:
        print("LAYOUT %d warnings" % warns, flush=True)
    for p in prompts:
        emit(p)
    if ended:
        print("SESSION ended", flush=True)
    if not prompts and not warns and not ended:
        print("MESSAGE | poll returned with nothing new", flush=True)
    return 0


def cmd_end(a):
    html = page_for(a.note, refresh=False)
    r = subprocess.run(lavish("end", html), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=120)
    print(((r.stdout or "") + (r.stderr or "")).strip()[:400] or "ended")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn, helptext in (
            ("open", cmd_open, "render the page and open or resume the session"),
            ("refresh", cmd_refresh, "re-render the page; the open browser picks it up"),
            ("poll", cmd_poll, "block until they send something, then print it"),
            ("reply", cmd_poll, "speak on the page, then block like poll"),
            ("end", cmd_end, "end the Lavish session"),
            ("url", cmd_url, "print the session URL")):
        p = sub.add_parser(name, help=helptext)
        p.add_argument("--note", required=True, help="vault-relative note path, no .md")
        if name in ("poll", "reply"):
            p.add_argument("--reply", "--agent-reply", "--text", dest="reply", default="",
                           help="shown on the page before the wait starts")
        p.set_defaults(func=fn)

    a = ap.parse_args()
    if a.cmd == "reply" and not a.reply:
        fail("reply needs --text (or --reply)")
    if learnlib.SURFACE != "podium":
        sys.stderr.write("podium: note - surface is '%s' in config.json. "
                         "Running anyway.\n" % learnlib.SURFACE)
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
