"""podium_page.py - render a session note into the page the learner reads.

The markdown note stays the durable record. This turns it into one HTML page
that renders LaTeX, mermaid and images, and - when a quiz question is pending -
carries a real answer form, so the learner reads and answers in one place.

    py podium_page.py --note "<learning_dir>/master-theorem"
    py podium_page.py --note "..." --standalone --out share.html

`--note` is vault-relative, forward slashes, no `.md`, exactly as quiz.py takes
it. Three files are written beside the note:

    <slug>-podium.html     the shell: styles, KaTeX, mermaid, the poll loop
    <slug>-podium.js       window.LEARN_SESSION - the rendered body
    <slug>-podium-ver.js   window.LEARN_LATEST - the body's hash, ~50 bytes

The shell loads the tiny version file every 3 s and reloads the payload only
when the hash moved, so a refresh after every node costs the browser almost
nothing. Both are script tags rather than a fetch: Lavish serves the page in a
sandboxed frame whose CSP has no connect-src, so fetch and XHR fail there
silently while a script tag works.

`--standalone --out <file>` writes ONE file instead: the body inlined, mermaid
inlined from `tools/vendor/mermaid.min.js`, no polling. That is the shareable
export. Maths still comes from the KaTeX CDN - the fonts are not vendored, so a
standalone page needs a network for its equations and nothing else.

Images are inlined as data URIs by default, which is what makes the page
portable. `--no-inline-assets` copies them beside the page instead.

Exit 0 wrote the page. Exit 1 means the note does not exist.
"""

import argparse
import base64
import hashlib
import html as htmllib
import json
import mimetypes
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import learnlib

TOOLS = os.path.dirname(os.path.abspath(__file__))
VENDOR = os.path.join(TOOLS, "vendor")
PENDING_MARK = "<!-- quiz:pending -->"

KATEX = "https://cdn.jsdelivr.net/npm/katex@0.16.11/dist"
MERMAID_CDN = "https://cdn.jsdelivr.net/npm/mermaid@11.15.0/dist/mermaid.esm.min.mjs"


# --------------------------------------------------------------------------
# paths
# --------------------------------------------------------------------------

def note_path(rel):
    path = os.path.join(learnlib.VAULT_ROOT, rel.replace("/", os.sep))
    if not path.endswith(".md"):
        path += ".md"
    return path


def slug_of(rel):
    base = os.path.basename(rel)
    if base.endswith(".md"):
        base = base[:-3]
    return re.sub(r"[^a-z0-9-]+", "-", base.lower())


def page_paths(rel):
    """(html, payload js, version js) beside the note."""
    stem = os.path.join(os.path.dirname(note_path(rel)), slug_of(rel) + "-podium")
    return stem + ".html", stem + ".js", stem + "-ver.js"


def pending_path(rel):
    return os.path.join(learnlib.vault_path(learnlib.QUIZ_LOG_DIR),
                        slug_of(rel) + ".pending.json")


# --------------------------------------------------------------------------
# markdown -> html
#
# A small renderer rather than a dependency, for two reasons. A stranger's
# clone has no pip install step, and every off-the-shelf renderer mangles
# LaTeX: `x_1 ... x_2` becomes an <em> the moment underscores are treated as
# emphasis. Maths and code spans are pulled out into placeholders before any
# inline rule runs, so nothing can touch them.
# --------------------------------------------------------------------------

SENTINEL = "\x00"

_MATH_BLOCK = re.compile(r"\$\$(.+?)\$\$", re.S)
_MATH_BRACKET = re.compile(r"\\\[(.+?)\\\]", re.S)
_MATH_PAREN = re.compile(r"\\\((.+?)\\\)", re.S)
# Inline $...$: no space right after the opening $, closes on the same line.
# A lone $ in prose (money, "$LEARN") therefore stays a lone $.
_MATH_INLINE = re.compile(r"(?<![\w$])\$(?!\s)([^\n$]+?)(?<!\s)\$(?![\w$])")
_CODE_SPAN = re.compile(r"`([^`\n]+)`")


class Protector:
    """Holds maths and code spans out of the inline pass, then puts them back."""

    def __init__(self):
        self.items = []

    def stash(self, html_text):
        self.items.append(html_text)
        return "%sP%d%s" % (SENTINEL, len(self.items) - 1, SENTINEL)

    def protect_math(self, text):
        def block(m):
            return self.stash("$$" + m.group(1).strip() + "$$")

        def paren(m):
            return self.stash("\\(" + m.group(1).strip() + "\\)")

        text = _MATH_BLOCK.sub(block, text)
        text = _MATH_BRACKET.sub(block, text)
        text = _MATH_PAREN.sub(paren, text)
        text = _MATH_INLINE.sub(lambda m: self.stash("\\(" + m.group(1) + "\\)"), text)
        return text

    def protect_code(self, text):
        return _CODE_SPAN.sub(
            lambda m: self.stash("<code>" + htmllib.escape(m.group(1)) + "</code>"), text)

    def restore(self, text):
        # Nested placeholders are impossible - each stash is a leaf - so one
        # pass in reverse index order is enough.
        for i in range(len(self.items) - 1, -1, -1):
            text = text.replace("%sP%d%s" % (SENTINEL, i, SENTINEL), self.items[i])
        return text


class Renderer:
    def __init__(self, resolve_asset):
        self.prot = Protector()
        self.resolve_asset = resolve_asset

    # ---- inline -----------------------------------------------------------

    def inline(self, text):
        text = self.prot.protect_math(text)
        text = self.prot.protect_code(text)
        text = htmllib.escape(text, quote=False)

        # Obsidian embeds first, so ![[x.svg|500]] never falls through to the
        # wikilink rule below and render as a broken link.
        text = re.sub(r"!\[\[([^\]|]+?)(?:\|(\d+))?\]\]", self._embed, text)
        text = re.sub(r"!\[([^\]]*)\]\(([^)\s]+)\)", self._image, text)
        text = re.sub(r"\[\[([^\]|]+?)\|([^\]]+?)\]\]", r'<span class="wl">\2</span>', text)
        text = re.sub(r"\[\[([^\]]+?)\]\]", r'<span class="wl">\1</span>', text)
        text = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)",
                      r'<a href="\2" target="_blank" rel="noopener">\1</a>', text)

        text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
        text = re.sub(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])", r"<em>\1</em>", text)
        # Dataview inline fields on review cards: [rung:: 1] -> a small chip.
        text = re.sub(r"\[(\w+)::\s*([^\]]*)\]",
                      r'<span class="fld">\1 \2</span>', text)
        return self.prot.restore(text)

    def _embed(self, m):
        src = self.resolve_asset(m.group(1).strip())
        width = (' width="%s"' % m.group(2)) if m.group(2) else ""
        if src is None:
            return '<span class="missing">missing: %s</span>' % htmllib.escape(m.group(1))
        return '<img class="fig" src="%s"%s alt="">' % (src, width)

    def _image(self, m):
        src = self.resolve_asset(m.group(2).strip())
        if src is None:
            return '<span class="missing">missing: %s</span>' % htmllib.escape(m.group(2))
        return '<img class="fig" src="%s" alt="%s">' % (src, m.group(1))

    # ---- blocks -----------------------------------------------------------

    def render(self, md):
        lines = md.split("\n")
        out, i, n = [], 0, len(lines)
        while i < n:
            line = lines[i]
            stripped = line.strip()

            if not stripped:
                i += 1
                continue

            if stripped.startswith("```"):
                lang = stripped[3:].strip()
                body, i = [], i + 1
                while i < n and not lines[i].strip().startswith("```"):
                    body.append(lines[i])
                    i += 1
                i += 1
                code = "\n".join(body)
                if lang == "mermaid":
                    out.append('<pre class="mermaid">%s</pre>' % htmllib.escape(code))
                else:
                    out.append('<pre class="code"><code>%s</code></pre>'
                               % htmllib.escape(code))
                continue

            m = re.match(r"^(#{1,6})\s+(.*)$", stripped)
            if m:
                lvl = len(m.group(1))
                out.append("<h%d>%s</h%d>" % (lvl, self.inline(m.group(2)), lvl))
                i += 1
                continue

            if re.match(r"^(-{3,}|\*{3,}|_{3,})$", stripped):
                out.append("<hr>")
                i += 1
                continue

            if stripped.startswith(">"):
                block, i = [], i
                while i < n and lines[i].strip().startswith(">"):
                    block.append(re.sub(r"^\s*>\s?", "", lines[i]))
                    i += 1
                out.append(self.quote(block))
                continue

            if stripped.startswith("|") and stripped.endswith("|"):
                block, i = [], i
                while i < n and lines[i].strip().startswith("|"):
                    block.append(lines[i].strip())
                    i += 1
                out.append(self.table(block))
                continue

            if re.match(r"^([-*+]|\d+\.)\s+", stripped):
                block, i = [], i
                while i < n and (lines[i].strip() and
                                 (re.match(r"^\s*([-*+]|\d+\.)\s+", lines[i]) or
                                  lines[i].startswith(("  ", "\t")))):
                    block.append(lines[i])
                    i += 1
                out.append(self.list_block(block))
                continue

            para, i = [], i
            while i < n and lines[i].strip() and not re.match(
                    r"^\s*(#{1,6}\s|```|>|\||[-*+]\s|\d+\.\s|-{3,}$)", lines[i]):
                para.append(lines[i].strip())
                i += 1
            if para:
                out.append("<p>%s</p>" % self.inline(" ".join(para)))
            else:
                i += 1
        return "\n".join(out)

    def quote(self, block):
        """A blockquote, or an Obsidian callout when it opens with [!kind]."""
        head = block[0] if block else ""
        m = re.match(r"^\s*\[!(\w+)\]([+-]?)\s*(.*)$", head)
        if not m:
            return '<blockquote>%s</blockquote>' % self.render("\n".join(block))
        kind, fold, title = m.group(1).lower(), m.group(2), m.group(3).strip()
        body = self.render("\n".join(block[1:]))
        title_html = self.inline(title) if title else kind.title()
        if fold == "-":
            # The body is wrapped and hidden with display:none rather than left
            # to the browser's own <details> hiding, which still hands out a
            # zero-size box at the origin - a layout checker reads that as
            # overlapping text and puts a blocking overlay on the page.
            return ('<details class="cal cal-%s"><summary>%s</summary>'
                    '<div class="cb">%s</div></details>' % (kind, title_html, body))
        return ('<div class="cal cal-%s"><div class="cal-t">%s</div>%s</div>'
                % (kind, title_html, body))

    def table(self, block):
        rows = [[c.strip() for c in r.strip().strip("|").split("|")] for r in block]
        rows = [r for r in rows if not all(re.match(r"^:?-{2,}:?$", c or "-") for c in r)]
        if not rows:
            return ""
        head, body = rows[0], rows[1:]
        out = ['<div class="tw"><table>', "<thead><tr>"]
        out += ["<th>%s</th>" % self.inline(c) for c in head]
        out.append("</tr></thead><tbody>")
        for r in body:
            out.append("<tr>" + "".join("<td>%s</td>" % self.inline(c) for c in r) + "</tr>")
        out.append("</tbody></table></div>")
        return "".join(out)

    def list_block(self, block):
        ordered = bool(re.match(r"^\s*\d+\.\s", block[0]))
        items, cur, base = [], None, None
        for line in block:
            m = re.match(r"^(\s*)([-*+]|\d+\.)\s+(.*)$", line)
            if m:
                indent = len(m.group(1).replace("\t", "  "))
                if base is None:
                    base = indent
                if indent > base and cur is not None:
                    cur.append(line[base:])
                    continue
                cur = [m.group(3)]
                items.append(cur)
            elif cur is not None:
                cur.append(line.strip())
        html_items = []
        for it in items:
            first, rest = it[0], it[1:]
            cls = ""
            m = re.match(r"^\[([ xX])\]\s*(.*)$", first)
            if m:
                done = m.group(1).lower() == "x"
                cls = ' class="task%s"' % (" done" if done else "")
                first = ('<span class="box">%s</span> ' % ("&#10003;" if done else "&#9633;")
                         ) + self.inline(m.group(2))
            else:
                first = self.inline(first)
            inner = first
            if rest:
                inner += self.render("\n".join(rest))
            html_items.append("<li%s>%s</li>" % (cls, inner))
        tag = "ol" if ordered else "ul"
        return "<%s>%s</%s>" % (tag, "".join(html_items), tag)


# --------------------------------------------------------------------------
# assets
# --------------------------------------------------------------------------

def asset_resolver(note_dir, page_dir, inline):
    """Turn a note-relative or vault-relative asset name into an <img src>.

    Inlined as a data URI by default - that is what makes the page portable and
    what lets `lavish-axi` serve it without a copy step. With --no-inline-assets
    the file is copied beside the page and referenced relatively, because a
    Lavish page can only reach assets in its own directory.
    """
    searched = [note_dir,
                learnlib.vault_path(learnlib.VISUALS_DIR),
                learnlib.VAULT_ROOT]

    def resolve(name):
        if re.match(r"^[a-z]+://", name):
            return name
        cand = None
        for root in searched:
            p = os.path.join(root, name.replace("/", os.sep))
            if os.path.isfile(p):
                cand = p
                break
        if cand is None:
            return None
        if inline:
            mime = mimetypes.guess_type(cand)[0] or "application/octet-stream"
            with open(cand, "rb") as fh:
                return "data:%s;base64,%s" % (mime, base64.b64encode(fh.read()).decode())
        dest = os.path.join(page_dir, os.path.basename(cand))
        if os.path.abspath(dest) != os.path.abspath(cand):
            shutil.copyfile(cand, dest)
        return os.path.basename(cand)

    return resolve


# --------------------------------------------------------------------------
# the pending question
# --------------------------------------------------------------------------

def split_pending(md):
    """(body without the pending block, the raw pending region or None).

    quiz.py appends a fixed shape: the question, an optional italic detail
    line, a numbered option list, the `**0.**` line, the marker, and a one-line
    hint. The option list and everything under it is dropped here, because the
    answer form below re-renders the options from the sidecar - which is the
    authoritative order. The question text itself is kept, so the note and the
    page read the same.
    """
    if PENDING_MARK not in md:
        return md, False
    head = md.rsplit(PENDING_MARK, 1)[0]
    lines = head.split("\n")
    cut = len(lines)
    # Walk back over the trailing "**0.** I don't know" line and the numbered
    # option list above it. Anything that is not one of those stops the walk.
    i = len(lines) - 1
    seen_options = False
    while i >= 0:
        s = lines[i].strip()
        if not s:
            i -= 1
            continue
        if s.startswith("**0.**"):
            cut = i
            i -= 1
            continue
        if re.match(r"^\d+\.\s", s) or s.startswith("- "):
            seen_options = True
            cut = i
            i -= 1
            continue
        break
    if not seen_options:
        cut = len(lines)          # shape did not match; keep the note as written
    return "\n".join(lines[:cut]).rstrip() + "\n", True


def question_card(q, renderer):
    """The answer form, built from the pending sidecar.

    Option labels go through the same inline renderer the note body uses, so
    maths in an option renders here exactly as it does anywhere else. The
    sidecar's order is authoritative - it is the shuffled order the note was
    written in, and the one the numbers refer to.
    """
    rows = []
    kind = "checkbox" if q.get("multi") else "radio"
    for i, opt in enumerate(q.get("options") or [], start=1):
        desc = ('<span class="od">%s</span>' % renderer.inline(opt["description"])
                if opt.get("description") else "")
        rows.append(
            '<li><label><input type="%s" name="pick" value="%d">'
            '<span class="ol"><b>%d.</b> %s%s</span>'
            "</label></li>" % (kind, i, i, renderer.inline(opt["label"]), desc))
    rows.append(
        '<li class="idk"><label><input type="%s" name="pick" value="0">'
        '<span class="ol"><b>0.</b> I do not know - an honest gap, not a wrong answer.'
        "</span></label></li>" % kind)
    hint = ("Tick every correct one." if q.get("multi") else "Pick one.")
    return (
        '<form class="card q" id="answer-form" data-learn-question="%s">'
        '<div class="qh"><span class="num">Answer</span>%s</div>'
        '<ul class="opts">%s</ul>'
        '<textarea name="why" rows="2" placeholder="Why? Optional, and it lands '
        'in the note beside this question."></textarea>'
        '<div class="row"><button type="submit">Send answer</button>'
        '<span class="queued">sent</span></div></form>'
        % (htmllib.escape(q.get("label") or "Question"), hint, "".join(rows)))


# --------------------------------------------------------------------------
# the page
# --------------------------------------------------------------------------

CSS = """
:root{--bg:#f7f7f5;--card:#fff;--ink:#1a1a1a;--mute:#6b6b6b;--line:#e4e2dd;
--ask:#b45309;--askbg:#fff7ed;--ok:#15803d;--okbg:#f0fdf4;--bad:#b91c1c;
--badbg:#fef2f2;--blue:#1d4ed8;--bluebg:#eff6ff}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.6 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
.wrap{max-width:880px;margin:0 auto;padding:22px 18px 90px}
header{margin-bottom:18px;padding-bottom:12px;border-bottom:1px solid var(--line)}
header h1{font-size:21px;margin:0 0 4px}
header .meta{color:var(--mute);font-size:13px}
h2{font-size:12px;letter-spacing:.09em;text-transform:uppercase;color:var(--mute);
margin:30px 0 10px;padding-top:8px;border-top:1px solid var(--line)}
h3{font-size:16px;margin:20px 0 8px}
h4{font-size:14px;margin:16px 0 6px;color:var(--mute)}
p{margin:9px 0}
ul,ol{margin:9px 0;padding-left:22px}
li{margin:4px 0}
li.task{list-style:none;margin-left:-18px}
li.task .box{color:var(--mute);margin-right:5px}
li.task.done{color:var(--mute);text-decoration:line-through}
a{color:var(--blue)}
.wl{color:var(--blue);border-bottom:1px dotted var(--blue)}
.fld{font-size:11px;color:var(--mute);background:#f0efec;border-radius:4px;
padding:1px 6px;margin-left:4px;white-space:nowrap}
.missing{color:var(--bad);font-size:13px}
code{background:#f0efec;border-radius:4px;padding:1px 5px;
font:13px ui-monospace,Consolas,monospace}
pre.code{background:#1c1b19;color:#f2efe9;border-radius:9px;padding:12px 14px;
overflow-x:auto;font:13px/1.5 ui-monospace,Consolas,monospace}
pre.code code{background:none;padding:0;color:inherit}
pre.mermaid{background:transparent;text-align:center;overflow-x:auto;margin:14px 0;
white-space:normal;line-height:0}
/* mermaid emits height="100%" on its svg, which in an auto-height parent makes
   the picture overrun whatever follows it. Pinning height:auto stops the graph
   sitting on top of the next heading. Its own inline max-width is left alone -
   overriding that scales a small diagram up to the full column. */
pre.mermaid svg{height:auto!important;display:block;margin:0 auto}
blockquote{margin:10px 0;padding:2px 14px;border-left:3px solid var(--line);
color:var(--mute)}
.cal{border:1px solid var(--line);border-left:4px solid var(--blue);
background:var(--bluebg);border-radius:8px;padding:10px 14px;margin:10px 0}
.cal-t,details.cal>summary{font-weight:600;cursor:pointer}
details.cal{border:1px solid var(--line);border-left:4px solid var(--blue);
background:var(--bluebg);border-radius:8px;padding:10px 14px;margin:10px 0}
details.cal > .cb{display:none}
details.cal[open] > .cb{display:block}
.cal-question,details.cal-question{border-left-color:var(--ask);background:var(--askbg)}
.cal-quote,details.cal-quote{border-left-color:var(--mute);background:#fff}
.cal p:first-child,details.cal p:first-child{margin-top:6px}
.tw{overflow-x:auto;margin:10px 0}
table{border-collapse:collapse;font-size:14px;min-width:100%}
th,td{border:1px solid var(--line);padding:6px 12px;text-align:left;background:#fff}
th{color:var(--mute);font-size:12px;font-weight:600;white-space:nowrap}
img.fig{display:block;background:#fff;border:1px solid var(--line);border-radius:8px;
margin:12px 0;max-width:100%;height:auto}
hr{border:none;border-top:1px solid var(--line);margin:20px 0}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;
padding:14px 16px;margin:16px 0}
/* Deliberately NOT sticky. A pinned answer card covers the material they need
   to read in order to answer it. */
.card.q{border-left:4px solid var(--ask);background:var(--askbg)}
.qh{font-weight:600;margin-bottom:8px}
.qh .num{display:inline-block;font-weight:700;color:var(--ask);margin-right:8px}
ul.opts{list-style:none;padding:0;margin:8px 0}
ul.opts li{margin:5px 0}
ul.opts label{display:flex;gap:9px;align-items:flex-start;cursor:pointer;
padding:8px 11px;border:1px solid var(--line);border-radius:8px;background:#fff}
ul.opts label:hover{border-color:var(--ask)}
ul.opts input{margin-top:4px;flex:none}
.od{display:block;color:var(--mute);font-size:13px;margin-top:2px}
textarea{font:inherit;width:100%;border:1px solid var(--line);border-radius:8px;
padding:7px 10px;background:#fff;margin-top:8px}
button{font:inherit;border:1px solid var(--ask);background:var(--ask);color:#fff;
border-radius:8px;padding:7px 14px;cursor:pointer}
.row{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-top:10px}
.queued{font-size:12px;color:var(--ok);display:none;font-weight:600}
.small{font-size:12px;color:var(--mute)}
.katex-display{margin:10px 0;overflow-x:auto;overflow-y:hidden;padding:3px 0}
.katex-mathml{display:none}
footer{margin-top:34px;color:var(--mute);font-size:12px;
border-top:1px solid var(--line);padding-top:12px}
"""

SHELL_JS = """
var LEARN_VER = null;

function paint(){
  var s = window.LEARN_SESSION; if(!s) return;
  LEARN_VER = s.version;
  document.getElementById('doc').innerHTML = s.body;
  document.title = s.title;
  document.getElementById('h1').textContent = s.title;
  document.getElementById('meta').textContent = s.meta;
  typeset();
}

function typeset(){
  var doc = document.getElementById('doc');
  // KaTeX and mermaid both call this once they load, and paint() calls it on
  // every refresh. Rendering the same content twice nests spans and is what a
  // layout checker reports as overlapping text, so each pass is stamped.
  var ver = (window.LEARN_SESSION || {}).version || '-';
  if(window.renderMathInElement && doc.dataset.tex !== ver){
    doc.dataset.tex = ver;
    renderMathInElement(doc,{delimiters:[
      {left:'$$',right:'$$',display:true},
      {left:'\\\\(',right:'\\\\)',display:false}],
      ignoredClasses:['katex'],throwOnError:false});
  }
  if(window.__mermaid){
    var nodes = document.querySelectorAll('#doc pre.mermaid');
    for(var i=0;i<nodes.length;i++){ nodes[i].removeAttribute('data-processed'); }
    if(nodes.length){ window.__mermaid.run({nodes:nodes}).catch(function(){}); }
  }
}

// The form is injected with innerHTML, so it gets a delegated listener rather
// than an inline handler. One submit sends one prompt through Lavish; the note
// is still the record, this is only the channel.
document.addEventListener('submit', function(ev){
  var f = ev.target; if(!f.hasAttribute('data-learn-question')) return;
  ev.preventDefault();
  var picks = [].slice.call(f.querySelectorAll('input[name=pick]:checked'))
                .map(function(i){return i.value;});
  if(!picks.length){ alert('Pick an option, or 0 if you do not know.'); return; }
  var why = (f.querySelector('textarea[name=why]')||{}).value || '';
  var label = f.getAttribute('data-learn-question');
  var text = 'ANSWER ' + picks.join(',') + (why ? ' | WHY: ' + why : '');
  if(!window.lavish){ alert('No Lavish session - reopen with podium.py open.'); return; }
  window.lavish.queuePrompt(text, {tag:'answer', text:text, element:f,
    data:{kind:'learn-answer', label:label, answer:picks.join(','), why:why}});
  // Only one question is ever open, so there is nothing to batch: send it
  // rather than leaving it queued behind a second click nobody knows to make.
  if(window.lavish.sendQueuedPrompts){ window.lavish.sendQueuedPrompts(); }
  f.querySelector('.queued').style.display='inline';
  f.querySelector('button').disabled = true;
});

// The page is served inside a sandboxed frame whose CSP has no connect-src, so
// fetch and XHR both fail silently here. Script tags are allowed, which is why
// the version check is a tiny .js file rather than a plain text file read with
// fetch: the small one is polled, the big payload only reloads when it moved.
function load(src, then){
  var s = document.createElement('script');
  s.src = src + '?t=' + Date.now();
  s.onload = function(){ s.remove(); then(); };
  s.onerror = function(){ s.remove(); };
  document.body.appendChild(s);
}

function poll(){
  load(VER_FILE, function(){
    var v = window.LEARN_LATEST;
    if(!v || v === LEARN_VER) return;
    LEARN_VER = v;
    load(JS_FILE, paint);
  });
}
"""


def shell_html(title, js_file, ver_file):
    return """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>%(title)s</title>
<link rel="stylesheet" href="%(katex)s/katex.min.css">
<style>%(css)s</style>
</head>
<body>
<div class="wrap">
  <header><h1 id="h1">%(title)s</h1><div class="meta" id="meta"></div></header>
  <div id="doc"></div>
  <footer>Podium - the page is generated from the session note, which stays the
  record. Answers you send here are graded and written back into it.</footer>
</div>
<script>var JS_FILE=%(js)s, VER_FILE=%(ver)s;</script>
<script>%(shell)s</script>
<script defer src="%(katex)s/katex.min.js"></script>
<script defer src="%(katex)s/contrib/auto-render.min.js" onload="typeset()"></script>
<script type="module">
  import mermaid from "%(mermaid)s";
  mermaid.initialize({startOnLoad:false, theme:"neutral", securityLevel:"strict"});
  window.__mermaid = mermaid; typeset();
</script>
<script src="%(jsrel)s"></script>
<script>paint(); setInterval(poll, 3000);</script>
</body>
</html>
""" % {"title": htmllib.escape(title), "css": CSS, "shell": SHELL_JS,
       "katex": KATEX, "mermaid": MERMAID_CDN,
       "js": json.dumps(js_file), "ver": json.dumps(ver_file), "jsrel": js_file}


def standalone_html(title, meta, body):
    mermaid_src = os.path.join(VENDOR, "mermaid.min.js")
    if os.path.isfile(mermaid_src):
        with open(mermaid_src, encoding="utf-8") as fh:
            block = "<script>%s</script>\n<script>mermaid.initialize({startOnLoad:true," \
                    'theme:"neutral",securityLevel:"strict"});</script>' % fh.read()
    else:
        block = ('<script type="module">import mermaid from "%s";'
                 'mermaid.initialize({startOnLoad:true,theme:"neutral",'
                 'securityLevel:"strict"});</script>' % MERMAID_CDN)
    return """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>%(title)s</title>
<link rel="stylesheet" href="%(katex)s/katex.min.css">
<style>%(css)s</style>
</head>
<body>
<div class="wrap">
  <header><h1>%(title)s</h1><div class="meta">%(meta)s</div></header>
  <div id="doc">%(body)s</div>
  <footer>Exported from a learn session note.</footer>
</div>
%(mermaid)s
<script defer src="%(katex)s/katex.min.js"></script>
<script defer src="%(katex)s/contrib/auto-render.min.js"
 onload="renderMathInElement(document.body,{delimiters:[{left:'$$',right:'$$',display:true},{left:'\\\\(',right:'\\\\)',display:false}],throwOnError:false})"></script>
</body>
</html>
""" % {"title": htmllib.escape(title), "meta": htmllib.escape(meta), "css": CSS,
       "body": body, "katex": KATEX, "mermaid": block}


# --------------------------------------------------------------------------

def frontmatter(md):
    """(dict, body). Only the flat `key: value` shape the skill writes."""
    if not md.startswith("---"):
        return {}, md
    end = md.find("\n---", 3)
    if end < 0:
        return {}, md
    fm = {}
    for line in md[3:end].split("\n"):
        if ":" in line and not line.strip().startswith("#"):
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip()
    return fm, md[end + 4:].lstrip("\n")


def build(rel, inline_assets=True):
    """-> (title, meta line, body html, has_pending)."""
    path = note_path(rel)
    if not os.path.isfile(path):
        sys.stderr.write("podium_page: no such note: %s\n" % path)
        sys.exit(1)
    with open(path, encoding="utf-8") as fh:
        md = fh.read()

    fm, body_md = frontmatter(md)
    body_md, has_mark = split_pending(body_md)

    html_path = page_paths(rel)[0]
    renderer = Renderer(asset_resolver(os.path.dirname(path),
                                       os.path.dirname(html_path), inline_assets))
    body = renderer.render(body_md)

    pending = None
    pend_file = pending_path(rel)
    if os.path.isfile(pend_file):
        try:
            with open(pend_file, encoding="utf-8") as fh:
                pending = json.load(fh)
        except ValueError:
            pending = None
    if pending:
        body += question_card(pending, renderer)
    elif has_mark:
        body += ('<div class="card q"><div class="qh">A question is open in the note '
                 'but its answer key is gone. Ask it again.</div></div>')

    title = fm.get("subject") or os.path.basename(rel).replace("-", " ").title()
    bits = [b for b in (fm.get("mode"), fm.get("status"),
                        ("updated " + fm["updated"]) if fm.get("updated") else None,
                        ("due " + fm["deadline"]) if fm.get("deadline") else None) if b]
    return title, "  |  ".join(bits), body, bool(pending)


def write_pages(rel, inline_assets=True):
    title, meta, body, has_q = build(rel, inline_assets)
    html_path, js_path, ver_path = page_paths(rel)
    ver = hashlib.sha1((title + meta + body).encode("utf-8")).hexdigest()[:16]

    payload = "window.LEARN_SESSION=%s;\n" % json.dumps(
        {"version": ver, "title": title, "meta": meta, "body": body}, ensure_ascii=False)

    shell = shell_html(title, os.path.basename(js_path), os.path.basename(ver_path))
    # The shell only changes when the title does, so leave it alone otherwise -
    # rewriting it would make the browser refetch a page it already has.
    if not os.path.isfile(html_path) or open(html_path, encoding="utf-8").read() != shell:
        with open(html_path, "w", encoding="utf-8") as fh:
            fh.write(shell)
    with open(js_path, "w", encoding="utf-8") as fh:
        fh.write(payload)
    with open(ver_path, "w", encoding="utf-8") as fh:
        fh.write('window.LEARN_LATEST=%s;\n' % json.dumps(ver))
    return html_path, has_q


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--note", required=True, help="vault-relative note path, no .md")
    ap.add_argument("--standalone", action="store_true",
                    help="write ONE shareable file instead of the live page")
    ap.add_argument("--out", help="where --standalone writes")
    ap.add_argument("--no-inline-assets", dest="inline", action="store_false",
                    default=True, help="copy images beside the page instead of inlining")
    a = ap.parse_args()

    if a.standalone:
        title, meta, body, _ = build(a.note, a.inline)
        out = a.out or os.path.join(os.path.dirname(note_path(a.note)),
                                    slug_of(a.note) + "-export.html")
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(standalone_html(title, meta, body))
        print(out)
        return 0

    html_path, has_q = write_pages(a.note, a.inline)
    print(html_path + ("  [question open]" if has_q else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
