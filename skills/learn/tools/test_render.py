"""Regression test for render_mermaid.py and render_svg.py.

    py test_render.py

Exits 0 when every case passes, 1 otherwise. Needs Pillow to measure margins;
without it the script says so and skips rather than reporting a false pass.

This exists because three separate crop defects shipped past a "verified"
report in one session, and each was only caught by an input the previous
round did not contain:

  1. A loose crop that looked fine until the PNG was actually read.
  2. Silent clipping - sequence diagrams lost their right-hand participants,
     because the crop offset came from getBBox() user units, which equal CSS
     pixels only when the viewBox origin is "0 0". Flowcharts satisfy that.
     Sequence diagrams do not.
  3. Lopsided margins, because element rectangles under-report what actually
     gets painted.

So the standard here is deliberately mechanical: EVERY side between 10 and 20
CSS px, spread at most 4 device px, and a zero margin on any side counts as a
FAILURE, not a pass, because content touching an edge means content was cut.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
MERMAID = HERE / "render_mermaid.py"
SVG = HERE / "render_svg.py"
SCALE = 2.0
OUT = Path(tempfile.mkdtemp(prefix="learn_render_test_"))

MERMAID_CASES = {
    "graph-TD": """graph TD
  A[known: recurrence relations] --> B[recursion tree]
  A --> C[asymptotic notation]
  B --> D[watershed n^log_b a]
  C --> D
  D --> E[master theorem]
  E --> F[divide and conquer bounds]
""",
    "graph-LR": """graph LR
  A[probe] --> B[map]
  B --> C[teach]
  C --> D[retain]
  D --> A
""",
    "sequenceDiagram": """sequenceDiagram
  participant R as Reader
  participant C as Claude
  R->>C: teach me the master theorem
  C->>R: probe question 1
  R->>C: answer
  C->>R: node 1
""",
    "stateDiagram-v2": """stateDiagram-v2
  [*] --> Probe
  Probe --> Map: edge bracketed
  Map --> Teach: route approved
  Teach --> Teach: next node
  Teach --> Retain: check graded
  Retain --> [*]
""",
    "tree-8-nodes": """graph TD
  R[root] --> A[a]
  R --> B[b]
  A --> C[c]
  A --> D[d]
  B --> E[e]
  B --> F[f]
  C --> G[g]
  F --> H[h]
""",
}

BROKEN_MERMAID = "graph TD\n  A[unclosed bracket --> B{{{ nonsense\n  --> ->\n"

TEST_SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="420" height="300" viewBox="0 0 420 300">
  <rect width="420" height="300" fill="#ffffff"/>
  <polygon points="60,240 340,240 60,60" fill="none" stroke="#1f2933" stroke-width="3"/>
  <path d="M60,215 L85,215 L85,240" fill="none" stroke="#c0392b" stroke-width="3"/>
  <text x="195" y="268" font-family="sans-serif" font-size="18" text-anchor="middle">b</text>
</svg>
"""


def margins(path):
    from PIL import Image
    im = Image.open(path).convert("RGB")
    w, h = im.size
    px = im.load()
    row_blank = lambda y: all(px[x, y] == (255, 255, 255) for x in range(w))
    col_blank = lambda x: all(px[x, y] == (255, 255, 255) for y in range(h))
    return (w, h), {
        "top": next((y for y in range(h) if not row_blank(y)), h),
        "bottom": next((y for y in range(h) if not row_blank(h - 1 - y)), h),
        "left": next((x for x in range(w) if not col_blank(x)), w),
        "right": next((x for x in range(w) if not col_blank(w - 1 - x)), w),
    }


def run(tool, source_path, out_path):
    return subprocess.run(
        [sys.executable, str(tool), "--source", str(source_path), "--out", str(out_path)],
        capture_output=True, text=True,
    )


def check_crop(name, out_path):
    (w, h), m = margins(out_path)
    css = {k: v / SCALE for k, v in m.items()}
    spread = max(m.values()) - min(m.values())
    clipped = any(v == 0 for v in m.values())
    ok = (not clipped) and all(10 <= v <= 20 for v in css.values()) and spread <= 4
    print("%-18s %4dx%-5d t%.1f b%.1f l%.1f r%.1f css  spread %d dev  %s%s" % (
        name, w, h, css["top"], css["bottom"], css["left"], css["right"],
        spread, "PASS" if ok else "FAIL", "  <-- CLIPPED" if clipped else ""))
    return ok


def main():
    try:
        import PIL  # noqa: F401
    except ImportError:
        print("Pillow is not installed, so margins cannot be measured.")
        print("Install it or run this on a box that has it - skipping is not a pass.")
        return 1

    failed = []

    for name, src in MERMAID_CASES.items():
        mmd = OUT / (name + ".mmd")
        png = OUT / (name + ".png")
        mmd.write_text(src, encoding="utf-8")
        proc = run(MERMAID, mmd, png)
        if proc.returncode != 0 or not png.exists():
            print("%-18s RENDER FAILED  %s" % (name, proc.stderr.strip()[:110]))
            failed.append(name)
            continue
        if not check_crop(name, png):
            failed.append(name)

    # A broken source must fail loudly and write nothing. Embedding a picture
    # of mermaid's own error graphic is the worst possible outcome, because it
    # looks like a diagram.
    bad = OUT / "broken.mmd"
    bad_png = OUT / "broken.png"
    bad.write_text(BROKEN_MERMAID, encoding="utf-8")
    proc = run(MERMAID, bad, bad_png)
    ok = proc.returncode != 0 and not bad_png.exists() and "parse error" in proc.stderr.lower()
    print("%-18s %s" % ("mermaid-parse-err", "PASS" if ok else "FAIL"))
    if not ok:
        failed.append("mermaid-parse-err")

    svg_src = OUT / "triangle.svg"
    svg_png = OUT / "triangle.png"
    svg_src.write_text(TEST_SVG, encoding="utf-8")
    proc = run(SVG, svg_src, svg_png)
    ok = proc.returncode == 0 and svg_png.exists()
    print("%-18s %s" % ("svg-renders", "PASS" if ok else "FAIL"))
    if not ok:
        failed.append("svg-renders")

    not_svg = OUT / "notsvg.svg"
    not_svg_png = OUT / "notsvg.png"
    not_svg.write_text("this is not svg at all\n", encoding="utf-8")
    proc = run(SVG, not_svg, not_svg_png)
    ok = proc.returncode != 0 and not not_svg_png.exists()
    print("%-18s %s" % ("svg-bad-input", "PASS" if ok else "FAIL"))
    if not ok:
        failed.append("svg-bad-input")

    print()
    print("artifacts: %s" % OUT)
    print("ALL PASS" if not failed else "FAILED: " + ", ".join(failed))
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
