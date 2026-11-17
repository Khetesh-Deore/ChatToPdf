from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from playwright.async_api import TimeoutError as PWTimeout

from .browser import BrowserManager
from .config import (IMAGE_HOST_SUFFIXES, MAX_IMAGE_BYTES, MAX_IMAGES, MSG_SEL,
                     NAV_TIMEOUT_MS, SELECTOR_TIMEOUT_MS, USER_AGENT)
from .models import ConvertError, NoMessagesFound, PageBlocked, RawCapture, RawMessage

# Scroll every scrollable container once so lazy content/images get requested.
JS_SCROLL = r"""
async () => {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const els = [document.scrollingElement, ...document.querySelectorAll('*')]
    .filter(e => e && e.scrollHeight > e.clientHeight + 50);
  for (const el of els) {
    for (let y = 0; y < el.scrollHeight; y += 700) { el.scrollTop = y; await sleep(60); }
    el.scrollTop = 0;
  }
}
"""

# Collect role + inner HTML of every message. <img src> are rewritten to absolute URLs.
JS_EXTRACT = r"""
() => {
  const out = [];
  document.querySelectorAll('[data-message-author-role]').forEach(node => {
    const md = node.querySelector('.markdown');
    const src = md || node;
    const clone = src.cloneNode(true);
    const orig = src.querySelectorAll('img');
    clone.querySelectorAll('img').forEach((c, i) => {
      const o = orig[i];
      c.setAttribute('src', (o && (o.currentSrc || o.src)) || c.getAttribute('src') || '');
    });
    const turn = node.closest('article') || node.parentElement;
    const extra = [...turn.querySelectorAll('img')]
      .filter(i => !node.contains(i)).map(i => i.currentSrc || i.src).filter(Boolean);
    out.push({ role: node.getAttribute('data-message-author-role'),
               html: clone.innerHTML, extra });
  });
  return { title: document.title, messages: out };
}
"""


def _image_allowed(url: str) -> bool:
    p = urlparse(url)
    host = (p.hostname or "").lower()
    return p.scheme == "https" and any(
        host == s or host.endswith("." + s) for s in IMAGE_HOST_SUFFIXES
    )


def _collect_srcs(messages: list[RawMessage]) -> list[str]:
    srcs: list[str] = []
    for m in messages:
        soup = BeautifulSoup(m.html, "lxml")
        srcs += [i.get("src") for i in soup.find_all("img") if i.get("src")]
        srcs += m.extra_images
    return [s for s in dict.fromkeys(srcs) if s and not s.startswith("data:")]


async def _download_images(ctx, srcs: list[str]) -> dict[str, tuple[str, bytes]]:
    blobs: dict[str, tuple[str, bytes]] = {}
    for src in srcs[:MAX_IMAGES]:
        if not _image_allowed(src):
            continue
        try:
            # ctx.request shares cookies + UA with the page that loaded the share link
            r = await ctx.request.get(src, timeout=20_000)
            if not r.ok:
                continue
            body = await r.body()
            if len(body) > MAX_IMAGE_BYTES:
                continue
            mime = r.headers.get("content-type", "image/png").split(";")[0].strip()
            if mime.startswith("image/"):
                blobs[src] = (mime, body)
        except Exception:
            continue          # a missing image must never kill the whole job
    return blobs


async def _dump(page, debug_dir: Path | None) -> None:
    if not debug_dir:
        return
    debug_dir.mkdir(parents=True, exist_ok=True)
    (debug_dir / "page.html").write_text(await page.content(), encoding="utf-8")
    await page.screenshot(path=str(debug_dir / "page.png"), full_page=True)


async def capture(browser: BrowserManager, url: str, debug_dir: Path | None = None) -> RawCapture:
    ctx = await browser.new_context(
        user_agent=USER_AGENT, viewport={"width": 1100, "height": 900}, locale="en-US"
    )
    try:
        page = await ctx.new_page()
        resp = await page.goto(url, wait_until="domcontentloaded", timeout=NAV_TIMEOUT_MS)
        if resp is not None and resp.status == 404:
            raise ConvertError(
                "This shared link was not found. It may be deleted or no longer public."
            )
        try:
            await page.wait_for_selector(MSG_SEL, timeout=SELECTOR_TIMEOUT_MS)
        except PWTimeout:
            await _dump(page, debug_dir)
            page_html = await page.content()
            title = (await page.title()).lower()
            page_text = page_html.lower()

            # Detect bot / challenge pages
            bot_signals = (
                "just a moment" in title,
                "attention required" in title,
                "verify you are human" in page_text,
                "enable javascript" in page_text,
                "checking your browser" in page_text,
                "cf-browser-verification" in page_text,
                "challenge-form" in page_text,
            )
            if any(bot_signals):
                raise PageBlocked(
                    "ChatGPT served a bot-check page. "
                    "Try again in a few minutes, or use the 'Saved HTML file' tab: "
                    "open the share link in your browser, save the page "
                    "(File → Save Page As…), and upload it here."
                )

            # Try JSON fallback before giving up
            from .extractor_json import extract_from_html
            try:
                title_str, items = extract_from_html(page_html)
                return RawCapture(
                    title=title_str,
                    messages=[RawMessage(role=r, html=h) for r, h in items],
                    blobs={},
                )
            except (ValueError, Exception):
                pass

            raise NoMessagesFound(
                "No messages were found on that page. "
                "Make sure the link is set to 'Public' in ChatGPT, "
                "or use the 'Saved HTML file' tab."
            )

        await page.evaluate(JS_SCROLL)
        try:
            await page.wait_for_load_state("networkidle", timeout=10_000)
        except PWTimeout:
            pass
        await _dump(page, debug_dir)

        data = await page.evaluate(JS_EXTRACT)
        messages = [
            RawMessage(role=m["role"], html=m["html"], extra_images=m["extra"])
            for m in data["messages"]
        ]
        blobs = await _download_images(ctx, _collect_srcs(messages))
        return RawCapture(title=data["title"], messages=messages, blobs=blobs)
    finally:
        await ctx.close()


async def capture_from_html(browser: BrowserManager, html_content: str) -> RawCapture:
    """Load saved HTML directly — bypasses bot checks entirely."""
    ctx = await browser.new_context(
        user_agent=USER_AGENT, viewport={"width": 1100, "height": 900}, locale="en-US"
    )
    try:
        page = await ctx.new_page()
        await page.set_content(html_content, wait_until="domcontentloaded")
        try:
            await page.wait_for_selector(MSG_SEL, timeout=5_000)
        except PWTimeout:
            # Try JSON fallback on the uploaded HTML
            from .extractor_json import extract_from_html
            try:
                title_str, items = extract_from_html(html_content)
                return RawCapture(
                    title=title_str,
                    messages=[RawMessage(role=r, html=h) for r, h in items],
                    blobs={},
                )
            except (ValueError, Exception):
                pass
            raise NoMessagesFound(
                "No messages were found in the uploaded file. "
                "Make sure you saved the full page from your browser."
            )

        await page.evaluate(JS_SCROLL)
        data = await page.evaluate(JS_EXTRACT)
        messages = [
            RawMessage(role=m["role"], html=m["html"], extra_images=m["extra"])
            for m in data["messages"]
        ]
        # Images in uploaded HTML are likely expired; skip download silently
        blobs = await _download_images(ctx, _collect_srcs(messages))
        return RawCapture(title=data["title"], messages=messages, blobs=blobs)
    finally:
        await ctx.close()
