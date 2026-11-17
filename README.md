# chat2pdf

Convert a public ChatGPT share link to a clean A4 PDF — math, code, tables and images included.
No third-party APIs. Everything runs on your own server.

---

## Quick start (local)

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS / Linux:
source .venv/bin/activate

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Install Chromium (once)
python -m playwright install chromium

# 4. Vendor KaTeX (once — requires Node/npm)
# Windows PowerShell:
pwsh scripts/vendor_katex.ps1
# macOS / Linux:
bash scripts/vendor_katex.sh

# 5. Run the server
uvicorn app.main:app --port 8000
```

Open http://localhost:8000 in your browser.

---

## CLI usage

```bash
# From a live share link
python -m app.cli "https://chatgpt.com/share/<id>" out.pdf

# With debug dump (saves page.html + page.png for selector inspection)
python -m app.cli "https://chatgpt.com/share/<id>" out.pdf --debug ./debug

# From a saved HTML file (bypasses bot checks)
python -m app.cli --file saved_page.html out.pdf
```

---

## Run tests

```bash
pytest -q
```

The PDF end-to-end test (`tests/test_pdf.py`) requires Chromium and is skipped automatically
if it is not installed.

---

## Deploy on Render (free, lifetime)

1. Push this repository to GitHub.
2. Go to https://render.com → **New → Blueprint** → connect your repo.
3. Render reads `render.yaml` and creates the service automatically.
4. First deploy takes ~5 min (builds Docker image, installs Chromium and fonts).

**Free-tier limits:**
- 512 MB RAM — keep `MAX_CONCURRENT_JOBS = 1` in `app/config.py`.
- The instance spins down after 15 min of inactivity. The first request after
  spin-down takes ~30 s while Chromium starts. Upgrade to Starter ($7/mo) to
  keep it always-on.

---

## Deploy on Railway (free alternative)

1. Push to GitHub.
2. Go to https://railway.app → **New Project → Deploy from GitHub repo**.
3. Railway auto-detects the Dockerfile and builds it.
4. Set the port in Railway's environment variables: `PORT=8000`.

Railway's free hobby plan gives 500 hours/month — enough for personal use.

---

## Deploy on Fly.io (free alternative)

```bash
# Install flyctl: https://fly.io/docs/hands-on/install-flyctl/
fly launch        # detects Dockerfile, asks for app name and region
fly deploy
```

Fly.io free tier: 3 shared-CPU VMs, 256 MB RAM each.
Use `--vm-memory 512` during `fly launch` to avoid OOM during PDF generation.

---

## Project layout

```
chat2pdf/
├─ app/
│  ├─ main.py            FastAPI routes + lifespan
│  ├─ config.py          constants
│  ├─ models.py          dataclasses + user-facing errors
│  ├─ url_validator.py   SSRF guard / allow-list
│  ├─ browser.py         Chromium manager
│  ├─ fetcher.py         page capture + image download
│  ├─ normalizer.py      HTML cleaning, math, code, images, sanitizing
│  ├─ images.py          resize / recompress with Pillow
│  ├─ renderer.py        Jinja2 → HTML
│  ├─ pdf.py             HTML → PDF via Chromium
│  ├─ pipeline.py        orchestration
│  ├─ jobs.py            job store, rate limit, cleanup
│  ├─ extractor_json.py  fallback: read embedded conversation JSON
│  ├─ cli.py             command-line runner
│  ├─ templates/
│  │  └─ chat.html.j2    PDF chat layout
│  ├─ static/            index.html, style.css, app.js, privacy.html, terms.html
│  └─ vendor/katex/      vendored KaTeX (created by scripts/vendor_katex.*)
├─ scripts/
│  ├─ vendor_katex.sh    vendor KaTeX on macOS / Linux
│  └─ vendor_katex.ps1   vendor KaTeX on Windows
├─ tests/
│  ├─ test_core.py       URL validation, normalizer, renderer
│  ├─ test_pdf.py        end-to-end Chromium PDF test
│  └─ test_json_fallback.py  JSON extractor tests
├─ Dockerfile
├─ render.yaml
├─ requirements.txt
└─ pytest.ini
```

---

## Selector verification (required after first deploy)

ChatGPT's page markup can change. After getting a real share link to work, run:

```bash
python -m app.cli "https://chatgpt.com/share/<id>" out.pdf --debug ./debug
```

Open `debug/page.html` and check:

| What to verify | Expected value | File to edit if wrong |
|---|---|---|
| Message container | `data-message-author-role="user"` / `"assistant"` | `app/config.py` → `MSG_SEL` |
| Assistant body | `<div class="markdown">` inside the message node | `app/fetcher.py` → `JS_EXTRACT` |
| Math | `<span class="katex">` with `<annotation encoding="application/x-tex">` | `app/normalizer.py` → `convert_math` |
| Code | `<pre><code class="language-xxx">` | `app/normalizer.py` → `convert_code` |

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| "No messages were found" | Markup changed → run `--debug`, inspect `page.html`, update `MSG_SEL` |
| "bot-check page" error | Use the **Saved HTML file** tab or retry later |
| Formulas show as `\( … \)` raw text | KaTeX not vendored → run `scripts/vendor_katex.*` |
| `[Image unavailable]` in PDF | Image URL expired or host not in `IMAGE_HOST_SUFFIXES` |
| `NotImplementedError` on Windows | Don't use `--reload` with uvicorn; run plain `uvicorn app.main:app` |
| PDF is very large | Lower `IMAGE_MAX_WIDTH_PX` in `app/config.py` |
| OOM on free Render tier | Set `MAX_CONCURRENT_JOBS = 1` in `app/config.py` |
