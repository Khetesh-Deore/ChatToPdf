"""Turn the HTML ChatGPT rendered into clean, self-contained, safe HTML.

Pipeline per message:
  strip UI chrome -> KaTeX -> TeX delimiters -> highlight code -> inline images -> sanitize
"""
import base64
import html as html_lib
import re

import nh3
from bs4 import BeautifulSoup, NavigableString
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import TextLexer, get_lexer_by_name
from pygments.util import ClassNotFound

from .images import shrink

ALLOWED_TAGS = {
    "p", "br", "hr", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "li",
    "strong", "b", "em", "i", "u", "del", "s", "sup", "sub", "code", "pre",
    "blockquote", "table", "thead", "tbody", "tfoot", "tr", "th", "td",
    "a", "img", "div", "span", "figure", "figcaption",
}
ALLOWED_ATTRS = {
    "*": {"class"},
    "a": {"href"},
    "img": {"src", "alt"},
    "td": {"colspan", "rowspan", "align"},
    "th": {"colspan", "rowspan", "align"},
    "ol": {"start"},
}
LANG_RE = re.compile(r"language-([\w+#.-]+)")
_FORMATTER = HtmlFormatter(nowrap=True)   # token <span class="k"> only; CSS added by template


# ---------------------------------------------------------------- chrome ----
def strip_chrome(soup: BeautifulSoup) -> None:
    for t in soup(["script", "style", "button", "svg", "canvas", "iframe", "form",
                   "input", "video", "audio", "object", "embed", "noscript"]):
        t.decompose()


# ------------------------------------------------------------------ math ----
def _tex_of(node) -> str | None:
    ann = node.find("annotation", attrs={"encoding": "application/x-tex"})
    return ann.get_text() if ann else None


def convert_math(soup: BeautifulSoup) -> None:
    """Replace rendered KaTeX DOM with plain \\( \\) / \\[ \\] TeX; the print page re-renders it."""
    for d in soup.select("span.katex-display"):
        tex = _tex_of(d)
        if tex is None:
            continue
        block = soup.new_tag("div", attrs={"class": "math-block"})
        block.string = f"\\[{tex.strip()}\\]"
        d.replace_with(block)
    for k in soup.select("span.katex"):
        tex = _tex_of(k)
        if tex is None:
            continue
        k.replace_with(NavigableString(f"\\({tex.strip()}\\)"))


# ------------------------------------------------------------------ code ----
def _lexer(lang: str | None):
    if lang:
        try:
            return get_lexer_by_name(lang)
        except ClassNotFound:
            pass
    return TextLexer()


def convert_code(soup: BeautifulSoup) -> None:
    for pre in soup.find_all("pre"):
        code = pre.find("code")
        if code is None:
            continue
        lang = None
        for c in code.get("class", []):
            m = LANG_RE.match(c)
            if m:
                lang = m.group(1)
                break
        if lang is None:          # fallback: header label inside <pre>
            label = pre.find("div")
            txt = label.get_text(strip=True) if label else ""
            if txt and len(txt) < 20 and " " not in txt:
                lang = txt.lower()
        text = code.get_text().rstrip("\n")
        body = highlight(text, _lexer(lang), _FORMATTER)
        label_html = html_lib.escape(lang or "text")
        frag = BeautifulSoup(
            f'<div class="code-block"><div class="code-lang">{label_html}</div>'
            f"<pre><code>{body}</code></pre></div>",
            "html.parser",
        )
        pre.replace_with(frag)


# ---------------------------------------------------------------- images ----
def inline_images(soup: BeautifulSoup, blobs: dict[str, tuple[str, bytes]]) -> None:
    for img in soup.find_all("img"):
        src = img.get("src", "")
        if src.startswith("data:"):
            continue
        blob = blobs.get(src)
        if not blob:
            ph = soup.new_tag("div", attrs={"class": "img-missing"})
            ph.string = "[Image unavailable]"
            img.replace_with(ph)
            continue
        mime, data = shrink(*blob)
        img.attrs = {
            "src": f"data:{mime};base64,{base64.b64encode(data).decode()}",
            "alt": img.get("alt", "Image"),
        }


# ------------------------------------------------------------ entrypoint ----
def normalize_message(
    raw_html: str,
    role: str,
    blobs: dict,
    extra_images: list[str] | None = None,
) -> str:
    if role == "user":
        text = BeautifulSoup(raw_html, "lxml").get_text()
        raw_html = f'<div class="user-text">{html_lib.escape(text.strip())}</div>'
    for u in extra_images or []:
        raw_html += f'<img src="{html_lib.escape(u, quote=True)}" alt="Attachment">'

    soup = BeautifulSoup(raw_html, "lxml")
    strip_chrome(soup)
    convert_math(soup)
    convert_code(soup)
    inline_images(soup, blobs)
    body = soup.body.decode_contents() if soup.body else str(soup)
    return nh3.clean(
        body,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRS,
        url_schemes={"http", "https", "mailto", "data"},
        link_rel="noopener noreferrer",
    )
