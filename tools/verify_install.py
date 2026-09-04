"""Smoke test for a fresh claude-learn install.

Runs one real probe question end to end - ask, grade - through the
just-installed quiz.py, plus a two-node mermaid render, against a throwaway
vault under the system temp dir. Nothing here touches the real vault named
in config.json.

    py verify_install.py <installed-skill-dir>

Called by install.ps1 -Verify / install.sh --verify, right after the
dependency report. Prints PASS/FAIL/SKIP per step and a final PASS/FAIL
line. Exit 0 only if every required step passed; a missing Chrome is SKIP,
not FAIL, because the render tools are an optional dependency.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile


def run(cmd, env):
    return subprocess.run(cmd, env=env, capture_output=True, text=True)


def say(status, label, detail=""):
    tag = {"pass": "PASS", "fail": "FAIL", "skip": "SKIP"}[status]
    print("  %s %-8s %s" % (tag, label, detail))
    return status == "pass" or status == "skip"


def main():
    if len(sys.argv) != 2:
        sys.stderr.write("usage: verify_install.py <installed-skill-dir>\n")
        return 2
    dest = os.path.abspath(sys.argv[1])
    tools = os.path.join(dest, "tools")
    if not os.path.isfile(os.path.join(tools, "quiz.py")):
        sys.stderr.write("verify: no quiz.py under %s - install the skill first\n" % tools)
        return 2

    tmp = tempfile.mkdtemp(prefix="learn-verify-")
    ok = True
    print("Verify (throwaway vault: %s)" % tmp)
    try:
        learning = os.path.join(tmp, "Learning")
        os.makedirs(learning, exist_ok=True)
        with open(os.path.join(learning, "verify-smoke.md"), "w", encoding="utf-8") as fh:
            fh.write(
                "---\ntype: learning-note\nsubject: install verify\nstatus: in-progress\n---\n\n"
                "## Anchors\n"
            )

        spec_path = os.path.join(tmp, "verify-spec.json")
        spec = {
            "label": "install verify",
            "question": "2 + 2 = ?",
            "options": [{"label": "4", "value": "four"}, {"label": "5", "value": "five"}],
            "correctAnswer": "four",
            "explanation": "Arithmetic - not a real probe question, just a fixed check.",
            "shuffle": False,
        }
        with open(spec_path, "w", encoding="utf-8") as fh:
            json.dump(spec, fh)

        env = dict(os.environ)
        env["LEARN_VAULT_ROOT"] = tmp
        env["LEARN_LEARNING_DIR"] = "Learning"

        r = run([sys.executable, os.path.join(tools, "quiz.py"), "ask",
                 "--spec", spec_path, "--note", "Learning/verify-smoke"], env)
        step_ok = r.returncode == 0
        ok = say("pass" if step_ok else "fail", "quiz ask",
                 r.stdout.strip() if step_ok else (r.stderr.strip() or r.stdout.strip())) and ok

        r = run([sys.executable, os.path.join(tools, "quiz.py"), "grade",
                 "--answer", "1", "--note", "Learning/verify-smoke"], env)
        graded_ok = r.returncode == 0
        result = None
        if graded_ok:
            try:
                result = json.loads(r.stdout).get("result")
            except json.JSONDecodeError:
                graded_ok = False
        step_ok = graded_ok and result == "correct"
        ok = say("pass" if step_ok else "fail", "quiz grade",
                 ("answered 1, graded %s" % result) if graded_ok
                 else (r.stderr.strip() or r.stdout.strip())) and ok

        sys.path.insert(0, tools)
        import learnlib  # noqa: E402  (needs tools/ on sys.path first)
        chrome = learnlib.chrome_path()
        if not chrome:
            say("skip", "mermaid render", "no Chrome found - optional, see README")
        else:
            mmd = os.path.join(tmp, "verify.mmd")
            png = os.path.join(tmp, "verify.png")
            with open(mmd, "w", encoding="utf-8") as fh:
                fh.write("graph TD\n  A[install] --> B[verified]\n")
            r = run([sys.executable, os.path.join(tools, "render_mermaid.py"),
                     "--source", mmd, "--out", png], env)
            step_ok = r.returncode == 0 and os.path.exists(png)
            ok = say("pass" if step_ok else "fail", "mermaid render",
                     png if step_ok else (r.stderr.strip() or r.stdout.strip())) and ok
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    print("PASS - install verified" if ok else "FAIL - see above")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
