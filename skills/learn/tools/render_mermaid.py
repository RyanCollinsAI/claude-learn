"""Render a mermaid diagram to a tightly-cropped PNG using headless Chrome.

Usage:
    py render_mermaid.py --source diagram.mmd --out diagram.png [--width 1400] [--scale 2] [--theme default]
    py render_mermaid.py --stdin --out diagram.png

No network access is used at render time - mermaid.min.js is loaded from the
vendored copy in tools/vendor/.

Exit code 0: diagram.png was written. Prints the absolute output path.
Exit code 1: mermaid failed to parse the source. The mermaid error text is
printed to stderr and no PNG is written.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import learnlib

VENDOR_JS = Path(__file__).resolve().parent / "vendor" / "mermaid.min.js"
MARGIN = 20  # CSS px added around the tight bbox in the final crop

HTML_TEMPLATE = """<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
  html,body {{ margin:0; padding:0; background:#ffffff; }}
  body {{ font-family: "Segoe UI", Arial, sans-serif; }}
  #container {{ display:inline-block; padding:0; }}
</style>
</head>
<body>
<div id="container"></div>
<script src="file:///{vendor_js}"></script>
<script>
  window.__status = "pending";
  async function main() {{
    try {{
      mermaid.initialize({{ startOnLoad:false, theme:{theme_json}, securityLevel:"loose" }});
      const source = {source_json};
      await mermaid.parse(source);
      const {{ svg }} = await mermaid.render("mmd-diagram-svg", source);
      document.getElementById("container").innerHTML = svg;
      const svgEl = document.querySelector("#container svg");
      // Mermaid emits width="100%" and often no height attribute. Inside a
      // shrink-wrapped container that gives the SVG no definite containing
      // block, so the browser falls back to the CSS default replaced-element
      // size (300x150) instead of the diagram's real size. Pin the rendered
      // CSS size to the diagram's own box so the pixels and the measurement
      // agree 1:1.
      const vbAttr = svgEl.getAttribute("viewBox");
      if (vbAttr) {{
        const vb = vbAttr.trim().split(/[\\s,]+/).map(Number);
        svgEl.style.width = vb[2] + "px";
        svgEl.style.height = vb[3] + "px";
      }} else {{
        const aw = parseFloat(svgEl.getAttribute("width"));
        const ah = parseFloat(svgEl.getAttribute("height"));
        if (aw > 0) svgEl.style.width = aw + "px";
        if (ah > 0) svgEl.style.height = ah + "px";
      }}
      svgEl.style.maxWidth = "none";
      svgEl.style.display = "block";

      // Measure the painted content in CSS PIXELS, not SVG user units.
      // getBBox() reports user-space coordinates, which only match CSS pixels
      // when the viewBox origin is "0 0". Flowcharts satisfy that; sequence
      // diagrams emit a non-zero (often negative) origin, so a getBBox-based
      // offset shifted them sideways and sliced the right-hand participants
      // off the screenshot. Client rects are already in CSS pixels, so no
      // viewBox reasoning is involved and every diagram type behaves the same.
      // Union every descendant, not just the direct children. A child <g>'s
      // own rect does not always enclose everything its subtree paints, and
      // under-measuring by a few pixels shows up as a lopsided margin.
      let L = Infinity, T = Infinity, R = -Infinity, B = -Infinity;
      for (const el of svgEl.querySelectorAll("*")) {{
        if (el.tagName === "style" || el.tagName === "defs") continue;
        const r = el.getBoundingClientRect();
        if (r.width <= 0 || r.height <= 0) continue;
        L = Math.min(L, r.left); T = Math.min(T, r.top);
        R = Math.max(R, r.right); B = Math.max(B, r.bottom);
      }}
      if (!isFinite(L)) {{
        const r = svgEl.getBoundingClientRect();
        L = r.left; T = r.top; R = r.right; B = r.bottom;
      }}

      // Shift the diagram so its content box lands MARGIN px from the
      // viewport's top-left corner, in both this measurement pass and the
      // later screenshot pass (both run this same script). A CSS transform
      // changes only where the element paints, not its layout box.
      const MARGIN = {margin};
      svgEl.style.transform = "translate(" + (MARGIN - L) + "px, " + (MARGIN - T) + "px)";
      const w = Math.ceil(R - L) + MARGIN * 2;
      const h = Math.ceil(B - T) + MARGIN * 2;
      document.title = "OK:" + w + "x" + h;
    }} catch (e) {{
      const msg = (e && (e.str || e.message)) ? (e.str || e.message) : String(e);
      document.title = "ERR:" + msg.replace(/[\\r\\n]+/g, " | ");
    }}
  }}
  main();
</script>
</body></html>
"""


def run_chrome(args, timeout=60):
    chrome = learnlib.chrome_path()
    if not chrome:
        print("no Chrome or Chromium found. Set chrome_path in config.json.", file=sys.stderr)
        sys.exit(1)
    proc = subprocess.run(
        [chrome, *args],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=timeout,
    )
    return proc


def build_html(source: str, theme: str) -> str:
    vendor_path = str(VENDOR_JS).replace("\\", "/")
    return HTML_TEMPLATE.format(
        vendor_js=vendor_path,
        theme_json=json.dumps(theme),
        source_json=json.dumps(source),
        margin=MARGIN,
    )


def dump_dom(html_path: Path, width: int, height: int):
    args = [
        "--headless=new", "--disable-gpu", "--hide-scrollbars",
        "--allow-file-access-from-files",
        "--virtual-time-budget=6000",
        f"--window-size={width},{height}",
        "--dump-dom",
        f"file:///{str(html_path).replace(chr(92), '/')}",
    ]
    proc = run_chrome(args)
    if proc.returncode != 0:
        # try legacy --headless flag as a fallback
        args[0] = "--headless"
        proc = run_chrome(args)
    return proc


def screenshot(html_path: Path, out_path: Path, width: int, height: int, scale: float):
    args = [
        "--headless=new", "--disable-gpu", "--hide-scrollbars",
        "--allow-file-access-from-files",
        "--virtual-time-budget=6000",
        f"--screenshot={out_path}",
        f"--window-size={width},{height}",
        f"--force-device-scale-factor={scale}",
        f"file:///{str(html_path).replace(chr(92), '/')}",
    ]
    proc = run_chrome(args)
    if proc.returncode != 0 or not out_path.exists():
        args[0] = "--headless"
        proc = run_chrome(args)
    return proc


def trim_png(path: Path, margin_px: int) -> bool:
    """Crop the screenshot to its true painted box plus an exact margin.

    The in-page estimate predicts the crop from element rectangles, and those
    under-report by a few pixels on some diagram types (mermaid sequence
    diagrams paint about 9px below what their rects claim). Painted pixels are
    the ground truth, so the screenshot is deliberately rendered oversized and
    trimmed back to exact here. Pasting onto a fresh canvas rather than
    cropping means a side that touched the edge gains its margin instead of
    keeping none.

    Pillow is optional. Without it the PNG stays as rendered - a little loose,
    never clipped.
    """
    try:
        from PIL import Image, ImageChops
    except ImportError:
        return False

    im = Image.open(path).convert("RGB")
    white = Image.new("RGB", im.size, (255, 255, 255))
    box = ImageChops.difference(im, white).getbbox()
    if not box:
        return False

    content = im.crop(box)
    cw, ch = content.size
    canvas = Image.new("RGB", (cw + 2 * margin_px, ch + 2 * margin_px), (255, 255, 255))
    canvas.paste(content, (margin_px, margin_px))
    canvas.save(path)
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", help="path to a .mmd mermaid source file")
    ap.add_argument("--stdin", action="store_true", help="read mermaid source from stdin")
    ap.add_argument("--out", required=True, help="output PNG path")
    ap.add_argument("--width", type=int, default=1400, help="pass-1 render window width (default 1400)")
    ap.add_argument("--scale", type=float, default=2, help="device scale factor for the final PNG (default 2)")
    ap.add_argument("--theme", default="default", help="mermaid theme (default, dark, forest, neutral)")
    args = ap.parse_args()

    if not VENDOR_JS.exists():
        print(f"vendored mermaid.min.js not found at {VENDOR_JS}", file=sys.stderr)
        sys.exit(1)

    if args.stdin:
        source = sys.stdin.read()
    elif args.source:
        source = Path(args.source).read_text(encoding="utf-8")
    else:
        print("must pass --source <file> or --stdin", file=sys.stderr)
        sys.exit(2)

    out_path = Path(args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    html = build_html(source, args.theme)

    tmp_dir = Path(tempfile.mkdtemp(prefix="render_mermaid_"))
    html_path = tmp_dir / "page.html"
    html_path.write_text(html, encoding="utf-8")

    try:
        # Pass 1: render off-screen at a tall window, read status + bbox from <title>.
        dump_proc = dump_dom(html_path, args.width, 4000)
        stdout = dump_proc.stdout.decode("utf-8", errors="replace")

        m = re.search(r"<title>(.*?)</title>", stdout, re.S)
        if not m:
            print("could not read render status from headless Chrome output", file=sys.stderr)
            print(dump_proc.stderr.decode("utf-8", errors="replace"), file=sys.stderr)
            sys.exit(1)

        status = m.group(1).strip()

        if status.startswith("ERR:"):
            print("mermaid parse error: " + status[4:], file=sys.stderr)
            sys.exit(1)

        if not status.startswith("OK:"):
            print(f"unexpected render status: {status}", file=sys.stderr)
            sys.exit(1)

        dims = status[3:]
        w_str, h_str = dims.split("x")
        # The reported dimensions already include the MARGIN on every side -
        # the page itself computed and applied that margin (see HTML_TEMPLATE)
        # so it is identical in this measurement pass and the screenshot pass.
        final_w = int(w_str)
        final_h = int(h_str)

        # Pass 2: screenshot with slack on both axes. The in-page figure is an
        # estimate, so shooting it exactly is what sliced the right-hand
        # participants off sequence diagrams. Over-render, then trim to the
        # painted pixels below.
        shot_proc = screenshot(html_path, out_path,
                               final_w + MARGIN * 2, final_h + MARGIN * 2,
                               args.scale)
        if not out_path.exists():
            print("headless Chrome did not produce a screenshot", file=sys.stderr)
            print(shot_proc.stderr.decode("utf-8", errors="replace"), file=sys.stderr)
            sys.exit(1)

        trim_png(out_path, int(round(MARGIN * args.scale)))
        print(str(out_path))
    finally:
        try:
            html_path.unlink(missing_ok=True)
            tmp_dir.rmdir()
        except OSError:
            pass


if __name__ == "__main__":
    main()
