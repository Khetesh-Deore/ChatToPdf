import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .browser import BrowserManager
from .fetcher import capture, capture_from_html
from .models import Conversation, Message, NoMessagesFound
from .normalizer import normalize_message
from .pdf import html_to_pdf
from .renderer import render_html
from .url_validator import validate_share_url


def clean_title(t: str) -> str:
    t = re.sub(r"^\s*ChatGPT\s*[-\u2013\u2014|:]\s*", "", t or "").strip()
    return t or "ChatGPT conversation"


def slugify(s: str) -> str:
    s = re.sub(r"[^\w\- ]+", "", s, flags=re.ASCII).strip().replace(" ", "_")
    return (s or "chat")[:60]


def build_conversation(raw, url: str) -> Conversation:
    msgs: list[Message] = []
    for rm in raw.messages:
        if rm.role not in ("user", "assistant"):
            continue          # system / tool steps are not shown
        html = normalize_message(rm.html, rm.role, raw.blobs, rm.extra_images)
        if html.strip():
            msgs.append(Message(role=rm.role, html=html))
    if not msgs:
        raise NoMessagesFound("The page loaded, but no readable messages were found.")
    return Conversation(
        title=clean_title(raw.title),
        source_url=url,
        messages=msgs,
        created_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    )


async def build_pdf(
    url: str,
    browser: BrowserManager,
    job_dir: Path,
    progress: Callable[[str], None] = lambda s: None,
    debug_dir: Path | None = None,
) -> tuple[Path, Conversation]:
    url = validate_share_url(url)
    progress("Fetching conversation…")
    raw = await capture(browser, url, debug_dir)
    progress("Processing messages…")
    conv = build_conversation(raw, url)
    progress("Generating PDF…")
    job_dir.mkdir(parents=True, exist_ok=True)
    html_path = job_dir / "index.html"
    html_path.write_text(render_html(conv), encoding="utf-8")
    pdf_path = job_dir / f"{slugify(conv.title)}.pdf"
    await html_to_pdf(browser, html_path, pdf_path, conv.title)
    return pdf_path, conv


async def build_pdf_from_html(
    html_content: str,
    browser: BrowserManager,
    job_dir: Path,
    progress: Callable[[str], None] = lambda s: None,
) -> tuple[Path, Conversation]:
    """Build a PDF from a user-uploaded saved HTML file (bypasses bot checks)."""
    progress("Parsing uploaded file…")
    raw = await capture_from_html(browser, html_content)
    source_url = "uploaded file"
    progress("Processing messages…")
    conv = build_conversation(raw, source_url)
    progress("Generating PDF…")
    job_dir.mkdir(parents=True, exist_ok=True)
    html_path = job_dir / "index.html"
    html_path.write_text(render_html(conv), encoding="utf-8")
    pdf_path = job_dir / f"{slugify(conv.title)}.pdf"
    await html_to_pdf(browser, html_path, pdf_path, conv.title)
    return pdf_path, conv
