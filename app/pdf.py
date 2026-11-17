import html as html_lib
from pathlib import Path

from .browser import BrowserManager

# A4 minus 15 mm side margins = ~680 css px. Using that as the viewport width makes the
# on-screen layout (where we measure wide equations) identical to the print layout.
CONTENT_WIDTH_PX = 680
MARGIN = {"top": "18mm", "bottom": "16mm", "left": "15mm", "right": "15mm"}


async def html_to_pdf(
    browser: BrowserManager, html_path: Path, pdf_path: Path, title: str
) -> None:
    ctx = await browser.new_context(viewport={"width": CONTENT_WIDTH_PX, "height": 1000})
    try:
        page = await ctx.new_page()

        async def guard(route):
            # The print page may not touch the network — only file:// and data: are allowed.
            if route.request.url.startswith(("file://", "data:")):
                await route.continue_()
            else:
                await route.abort()

        await page.route("**/*", guard)
        await page.goto(html_path.as_uri(), wait_until="load")
        await page.wait_for_function("window.__ready === true", timeout=30_000)
        await page.emulate_media(media="print")

        safe_title = html_lib.escape(title[:90])
        header = (
            f'<div style="font-size:8px;color:#8a8f98;width:100%;padding:0 15mm;'
            f'display:flex;justify-content:space-between;">'
            f'<span>{safe_title}</span><span>ChatGPT conversation</span></div>'
        )
        footer = (
            '<div style="font-size:8px;color:#8a8f98;width:100%;text-align:center;">'
            '<span class="pageNumber"></span> / <span class="totalPages"></span></div>'
        )

        await page.pdf(
            path=str(pdf_path),
            format="A4",
            print_background=True,
            margin=MARGIN,
            display_header_footer=True,
            header_template=header,
            footer_template=footer,
        )
    finally:
        await ctx.close()
