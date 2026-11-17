import base64
from io import BytesIO

import pytest
from PIL import Image

from app.models import Conversation, InvalidUrl, Message
from app.normalizer import normalize_message
from app.renderer import render_html
from app.url_validator import validate_share_url

# A minimal KaTeX snippet: one inline and one display formula.
KATEX = (
    '<p>Energy: <span class="katex"><span class="katex-mathml"><math><semantics><mrow>'
    '<mi>E</mi></mrow>'
    '<annotation encoding="application/x-tex">E=mc^2</annotation>'
    '</semantics></math></span>'
    '<span class="katex-html" aria-hidden="true">E=mc\u00b2</span></span></p>'
    '<span class="katex-display"><span class="katex">'
    '<span class="katex-mathml"><math><semantics><mrow/>'
    '<annotation encoding="application/x-tex">'
    r'x = \frac{-b \pm \sqrt{b^2-4ac}}{2a}'
    '</annotation></semantics></math></span>'
    '<span class="katex-html">x=\u2026</span></span></span>'
)


# ---------------------------------------------------------------- URL ----

def test_url_ok():
    u = validate_share_url(
        "https://chatgpt.com/share/123e4567-e89b-12d3-a456-426614174000?x=1"
    )
    assert u == "https://chatgpt.com/share/123e4567-e89b-12d3-a456-426614174000"


def test_url_ok_www():
    u = validate_share_url(
        "https://www.chatgpt.com/share/123e4567-e89b-12d3-a456-426614174000"
    )
    assert u == "https://chatgpt.com/share/123e4567-e89b-12d3-a456-426614174000"


def test_url_ok_openai():
    u = validate_share_url(
        "https://chat.openai.com/share/123e4567-e89b-12d3-a456-426614174000"
    )
    assert u == "https://chatgpt.com/share/123e4567-e89b-12d3-a456-426614174000"


@pytest.mark.parametrize("bad", [
    "http://chatgpt.com/share/123e4567-e89b-12d3-a456-426614174000",
    "https://evil.com/share/123e4567-e89b-12d3-a456-426614174000",
    "https://chatgpt.com.evil.com/share/123e4567-e89b-12d3-a456-426614174000",
    "https://chatgpt.com/c/123e4567-e89b-12d3-a456-426614174000",
    "https://169.254.169.254/latest/meta-data",
    "",
    "not a url",
    "javascript:alert(1)",
])
def test_url_rejected(bad):
    with pytest.raises(InvalidUrl):
        validate_share_url(bad)


# ---------------------------------------------------------------- math ----

def test_math_inline_and_display():
    out = normalize_message(KATEX, "assistant", {})
    assert r"\(E=mc^2\)" in out
    assert r"\[x = \frac{-b \pm \sqrt{b^2-4ac}}{2a}\]" in out
    assert "katex" not in out
    assert "math-block" in out


# ---------------------------------------------------------------- code ----

def test_code_is_highlighted_and_escaped():
    raw = (
        '<pre><div>python</div>'
        '<code class="language-python">if a &lt; b:\n    print("&amp;")</code></pre>'
    )
    out = normalize_message(raw, "assistant", {})
    assert "code-block" in out
    assert "code-lang" in out
    assert "python" in out
    assert "&lt;" in out
    assert "<script" not in out


def test_code_without_language_label():
    raw = '<pre><code>plain text here</code></pre>'
    out = normalize_message(raw, "assistant", {})
    assert "code-block" in out
    assert "plain text here" in out


# ---------------------------------------------------------------- user ----

def test_user_text_is_escaped_and_preserved():
    raw = '<div class="whitespace-pre-wrap">a &lt;b&gt;x&lt;/b&gt;\nline2</div>'
    out = normalize_message(raw, "user", {})
    assert "user-text" in out
    assert "&lt;b&gt;" in out
    assert "line2" in out


def test_user_html_tags_are_stripped():
    out = normalize_message("<p><b>bold</b> text</p>", "user", {})
    # Raw tags gone, plain text preserved
    assert "<b>" not in out
    assert "bold" in out
    assert "text" in out


# ---------------------------------------------------------------- XSS ----

def test_xss_and_junk_removed():
    raw = (
        '<p onclick="x()">hi'
        '<script>alert(1)</script>'
        '<button>Copy</button>'
        '<img src="https://evil.com/x.png"></p>'
    )
    out = normalize_message(raw, "assistant", {})
    assert "script" not in out
    assert "onclick" not in out
    assert "Copy" not in out
    assert "evil.com" not in out
    assert "Image unavailable" in out


# -------------------------------------------------------------- images ----

def test_image_inlined_as_data_uri():
    buf = BytesIO()
    Image.new("RGB", (40, 30), "red").save(buf, "PNG")
    url = "https://files.oaiusercontent.com/file-abc"
    out = normalize_message(
        f'<p><img src="{url}"></p>',
        "assistant",
        {url: ("image/png", buf.getvalue())},
    )
    assert "data:image/png;base64," in out
    payload = out.split("base64,")[1].split('"')[0]
    assert Image.open(BytesIO(base64.b64decode(payload))).size == (40, 30)


def test_missing_image_shows_placeholder():
    out = normalize_message(
        '<img src="https://files.oaiusercontent.com/file-missing">',
        "assistant",
        {},
    )
    assert "Image unavailable" in out
    assert "<img" not in out


def test_extra_user_images_are_added():
    url = "https://files.oaiusercontent.com/file-up"
    buf = BytesIO()
    Image.new("RGB", (10, 10), "blue").save(buf, "PNG")
    out = normalize_message(
        "<div>look</div>",
        "user",
        {url: ("image/png", buf.getvalue())},
        [url],
    )
    assert "data:image/png" in out


# -------------------------------------------------------------- render ----

def test_render_html_contains_everything():
    conv = Conversation(
        title="Quadratic <test>",
        source_url="https://chatgpt.com/share/x",
        created_at="now",
        messages=[
            Message("user", '<div class="user-text">Solve it</div>'),
            Message("assistant", normalize_message(KATEX, "assistant", {})),
        ],
    )
    html = render_html(conv)
    assert "Quadratic &lt;test&gt;" in html          # title is escaped
    assert "katex.min.css" in html
    assert "auto-render.min.js" in html
    assert "turn user" in html
    assert "turn assistant" in html
    assert ".code-block" in html                     # pygments CSS present


def test_render_html_escapes_source_url():
    conv = Conversation(
        title="Test",
        source_url='"><script>alert(1)</script>',
        created_at="now",
        messages=[Message("user", '<div class="user-text">hi</div>')],
    )
    html = render_html(conv)
    assert "<script>alert" not in html
