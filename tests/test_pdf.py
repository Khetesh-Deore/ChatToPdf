"""End-to-end check of the HTML -> PDF pipeline.

Skipped automatically if Chromium is not installed.
"""
import pytest
from pypdf import PdfReader

from app.browser import BrowserManager
from app.models import Conversation, Message
from app.normalizer import normalize_message
from app.pdf import html_to_pdf
from app.renderer import render_html

MATH = (
    '<span class="katex-display"><span class="katex">'
    '<math><semantics><mrow/>'
    '<annotation encoding="application/x-tex">E = mc^2</annotation>'
    '</semantics></math></span></span>'
)

TABLE = """
<table>
  <thead><tr><th>Name</th><th>Value</th></tr></thead>
  <tbody>
    <tr><td>alpha</td><td>1</td></tr>
    <tr><td>beta</td><td>2</td></tr>
  </tbody>
</table>
"""

CODE = '<pre><code class="language-python">def hello():\n    return "world"</code></pre>'


async def test_pdf_is_created(tmp_path):
    bm = BrowserManager()
    try:
        await bm.start()
    except Exception as e:
        pytest.skip(f"Chromium unavailable: {e}")

    try:
        body = "<p>Einstein:</p>" + MATH + TABLE + CODE
        conv = Conversation(
            title="Test chat",
            source_url="https://chatgpt.com/share/x",
            created_at="2024-01-01 00:00 UTC",
            messages=[
                Message("user", '<div class="user-text">What is E?</div>'),
                Message("assistant", normalize_message(body, "assistant", {})),
            ],
        )
        html = tmp_path / "index.html"
        html.write_text(render_html(conv), encoding="utf-8")
        pdf = tmp_path / "out.pdf"
        await html_to_pdf(bm, html, pdf, conv.title)

        assert pdf.exists()
        assert pdf.stat().st_size > 1000       # non-trivial file

        reader = PdfReader(str(pdf))
        assert len(reader.pages) >= 1
        text = "".join(p.extract_text() or "" for p in reader.pages)
        assert "Einstein" in text
        assert "You" in text
        assert "ChatGPT" in text
    finally:
        await bm.stop()


async def test_pdf_with_title_escaping(tmp_path):
    bm = BrowserManager()
    try:
        await bm.start()
    except Exception as e:
        pytest.skip(f"Chromium unavailable: {e}")

    try:
        conv = Conversation(
            title='Chat <with> "special" & chars',
            source_url="https://chatgpt.com/share/x",
            created_at="now",
            messages=[
                Message("user", '<div class="user-text">Hello</div>'),
                Message("assistant", "<p>Hi there.</p>"),
            ],
        )
        html = tmp_path / "index.html"
        html.write_text(render_html(conv), encoding="utf-8")
        pdf = tmp_path / "escaped.pdf"
        # Should not raise even with special chars in title
        await html_to_pdf(bm, html, pdf, conv.title)
        assert pdf.exists()
    finally:
        await bm.stop()
