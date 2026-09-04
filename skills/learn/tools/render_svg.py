"""Rasterize an SVG file to PNG using headless Chrome.

Usage:
    py render_svg.py --source diagram.svg --out diagram.png [--width W] [--height H] [--scale 2]

If --width/--height are omitted, they are parsed from the SVG's own
width/height attributes, falling back to its viewBox.

Exit code 0: diagram.png was written. Prints the absolute output path.
Exit code 1: the SVG could not be parsed (no root <svg> element found, or no
usable size could be determined). A clear message is printed to stderr and
no PNG is written.
"""
import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import learnlib

HTML_TEMPLATE = """<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
  html,body {{ margin:0; padding:0; background:#ffffff; }}
  #container {{ display:inline-block; }}
</style>
</head>
<body>
<div id="container">{svg_content}</div>
</body></html>
"""


def run_chrome(args, timeout=60):
    chrome = learnlib.chrome_path()
    if not chrome:
        print("no Chrome or Chromium found. Set chrome_path in config.json.", file=sys.stderr)
        sys.exit(1)
    return subprocess.run(
        [chrome, *args],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=timeout,
    )


def parse_length(val: str):
    """Parse an SVG length like '400', '400px', '400pt' into a CSS px float. Returns None if unparseable."""
    if val is None:
        return None
    m = re.match(r"^\s*([0-9]*\.?[0-9]+)\s*(px)?\s*$", val)
    if not m:
        return None
    return float(m.group(1))


def determine_size(svg_text: str, width_arg, height_arg):
    if width_arg and height_arg:
        return width_arg, height_arg

    root_m = re.search(r"<svg\b[^>]*>", svg_text, re.S)
    if not root_m:
        return None, None
    root = root_m.group(0)

    def attr(name):
        m = re.search(rf'{name}\s*=\s*"([^"]*)"', root)
        return m.group(1) if m else None

    w = width_arg or parse_length(attr("width"))
    h = height_arg or parse_length(attr("height"))

    if w is None or h is None:
        vb = attr("viewBox")
        if vb:
            parts = re.split(r"[\s,]+", vb.strip())
            if len(parts) == 4:
                vb_w, vb_h = float(parts[2]), float(parts[3])
                if w is None:
                    w = vb_w
                if h is None:
                    h = vb_h

    return w, h


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True, help="path to a .svg file")
    ap.add_argument("--out", required=True, help="output PNG path")
    ap.add_argument("--width", type=float, default=None)
    ap.add_argument("--height", type=float, default=None)
    ap.add_argument("--scale", type=float, default=2, help="device scale factor for the final PNG (default 2)")
    args = ap.parse_args()

    src_path = Path(args.source)
    if not src_path.exists():
        print(f"SVG source not found: {src_path}", file=sys.stderr)
        sys.exit(1)

    svg_text = src_path.read_text(encoding="utf-8")

    if "<svg" not in svg_text:
        print("no root <svg> element found - this does not look like an SVG file", file=sys.stderr)
        sys.exit(1)

    width, height = determine_size(svg_text, args.width, args.height)
    if not width or not height:
        print(
            "could not determine SVG dimensions: no width/height or viewBox attribute found. "
            "Pass --width and --height explicitly.",
            file=sys.stderr,
        )
        sys.exit(1)

    width = int(round(width))
    height = int(round(height))

    out_path = Path(args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    html = HTML_TEMPLATE.format(svg_content=svg_text)

    tmp_dir = Path(tempfile.mkdtemp(prefix="render_svg_"))
    html_path = tmp_dir / "page.html"
    html_path.write_text(html, encoding="utf-8")

    try:
        chrome_args = [
            "--headless=new", "--disable-gpu", "--hide-scrollbars",
            "--allow-file-access-from-files",
            f"--screenshot={out_path}",
            f"--window-size={width},{height}",
            f"--force-device-scale-factor={args.scale}",
            f"file:///{str(html_path).replace(chr(92), '/')}",
        ]
        proc = run_chrome(chrome_args)
        if not out_path.exists():
            chrome_args[0] = "--headless"
            proc = run_chrome(chrome_args)

        if not out_path.exists():
            print("headless Chrome did not produce a screenshot", file=sys.stderr)
            print(proc.stderr.decode("utf-8", errors="replace"), file=sys.stderr)
            sys.exit(1)

        print(str(out_path))
    finally:
        try:
            html_path.unlink(missing_ok=True)
            tmp_dir.rmdir()
        except OSError:
            pass


if __name__ == "__main__":
    main()
