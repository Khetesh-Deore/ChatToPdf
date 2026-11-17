"""Command-line runner for chat2pdf.

Usage:
    python -m app.cli <share-url> out.pdf [--debug DIR]
    python -m app.cli --file saved_page.html out.pdf

The --debug flag dumps page.html and page.png to the given directory so you can
inspect the raw page and verify/adjust selectors in fetcher.py.
"""
import argparse
import asyncio
import shutil
import tempfile
from pathlib import Path

from .browser import BrowserManager
from .pipeline import build_pdf, build_pdf_from_html


async def main() -> None:
    ap = argparse.ArgumentParser(description="Convert a ChatGPT share link to PDF.")
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("url", nargs="?", help="Public ChatGPT share URL")
    group.add_argument("--file", type=Path, metavar="HTML", help="Saved HTML file (bypass bot checks)")
    ap.add_argument("out", help="Output PDF path")
    ap.add_argument("--debug", type=Path, metavar="DIR", help="Dump page.html + page.png here")
    a = ap.parse_args()

    bm = BrowserManager()
    await bm.start()
    try:
        job_dir = Path(tempfile.mkdtemp())
        if a.file:
            html_content = a.file.read_text(encoding="utf-8", errors="replace")
            pdf, conv = await build_pdf_from_html(html_content, bm, job_dir, print)
        else:
            pdf, conv = await build_pdf(a.url, bm, job_dir, print, a.debug)
        shutil.copy(pdf, a.out)
        print(f"\n{len(conv.messages)} messages → {a.out}")
    finally:
        await bm.stop()


if __name__ == "__main__":
    asyncio.run(main())
