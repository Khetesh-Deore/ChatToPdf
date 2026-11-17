import asyncio
import logging
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, UploadFile, File
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .browser import BrowserManager
from .config import JOB_TIMEOUT_SECONDS, MAX_CONCURRENT_JOBS, STATIC_DIR
from .jobs import Job, janitor, rate_limited
from .models import ConvertError
from .pipeline import build_pdf, build_pdf_from_html
from .url_validator import validate_share_url

log = logging.getLogger("chat2pdf")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.browser = BrowserManager()
    await app.state.browser.start()
    app.state.jobs: dict[str, Job] = {}
    app.state.sem = asyncio.Semaphore(MAX_CONCURRENT_JOBS)
    app.state.root = Path(tempfile.mkdtemp(prefix="chat2pdf_"))
    cleaner = asyncio.create_task(janitor(app.state.jobs))
    yield
    cleaner.cancel()
    await app.state.browser.stop()


app = FastAPI(title="ChatGPT Share → PDF", lifespan=lifespan)


class ConvertRequest(BaseModel):
    url: str


def _client_ip(request: Request) -> str:
    # Trust X-Forwarded-For when behind Render/Vercel proxy
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def _run_job(app: FastAPI, job: Job, url: str) -> None:
    async with app.state.sem:
        job.status = "working"
        try:
            def progress(msg: str) -> None:
                job.message = msg

            pdf, _ = await asyncio.wait_for(
                build_pdf(url, app.state.browser, job.dir, progress),
                JOB_TIMEOUT_SECONDS,
            )
            job.pdf_path = pdf
            job.status = "done"
            job.message = "Your PDF is ready."
        except ConvertError as e:
            job.status = "error"
            job.error = str(e)
        except asyncio.TimeoutError:
            job.status = "error"
            job.error = "Timed out while fetching the conversation. Please try again."
        except Exception:
            log.exception("job %s failed", job.id)
            job.status = "error"
            job.error = "Something went wrong while building the PDF."


async def _run_file_job(app: FastAPI, job: Job, html_content: str) -> None:
    async with app.state.sem:
        job.status = "working"
        try:
            def progress(msg: str) -> None:
                job.message = msg

            pdf, _ = await asyncio.wait_for(
                build_pdf_from_html(html_content, app.state.browser, job.dir, progress),
                JOB_TIMEOUT_SECONDS,
            )
            job.pdf_path = pdf
            job.status = "done"
            job.message = "Your PDF is ready."
        except ConvertError as e:
            job.status = "error"
            job.error = str(e)
        except asyncio.TimeoutError:
            job.status = "error"
            job.error = "Timed out while processing the file. Please try again."
        except Exception:
            log.exception("file job %s failed", job.id)
            job.status = "error"
            job.error = "Something went wrong while building the PDF."


def _new_job(request: Request) -> Job:
    job = Job()
    job.dir = request.app.state.root / job.id
    request.app.state.jobs[job.id] = job
    return job


@app.post("/api/convert")
async def convert(req: ConvertRequest, request: Request):
    ip = _client_ip(request)
    if rate_limited(ip):
        raise HTTPException(429, "Too many requests. Please wait a minute.")
    try:
        url = validate_share_url(req.url)
    except ConvertError as e:
        raise HTTPException(400, str(e))
    job = _new_job(request)
    asyncio.create_task(_run_job(request.app, job, url))
    return {"job_id": job.id}


@app.post("/api/convert-file")
async def convert_file(request: Request, file: UploadFile = File(...)):
    ip = _client_ip(request)
    if rate_limited(ip):
        raise HTTPException(429, "Too many requests. Please wait a minute.")
    if not file.filename or not file.filename.lower().endswith(".html"):
        raise HTTPException(400, "Please upload an HTML file saved from your browser.")
    raw = await file.read()
    if len(raw) > 20 * 1024 * 1024:
        raise HTTPException(413, "File too large (max 20 MB).")
    try:
        html_content = raw.decode("utf-8", errors="replace")
    except Exception:
        raise HTTPException(400, "Could not read the file. Make sure it is an HTML file.")
    job = _new_job(request)
    asyncio.create_task(_run_file_job(request.app, job, html_content))
    return {"job_id": job.id}


def _get_job(request: Request, job_id: str) -> Job:
    job = request.app.state.jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found or expired.")
    return job


@app.get("/api/jobs/{job_id}")
async def job_status(job_id: str, request: Request):
    j = _get_job(request, job_id)
    return {"status": j.status, "message": j.message, "error": j.error}


@app.get("/api/jobs/{job_id}/download")
async def download(job_id: str, request: Request):
    j = _get_job(request, job_id)
    if j.status != "done" or not j.pdf_path:
        raise HTTPException(409, "PDF is not ready yet.")
    return FileResponse(
        j.pdf_path,
        media_type="application/pdf",
        filename=j.pdf_path.name,
    )


@app.get("/api/health")
async def health():
    return {"status": "ok"}


# Must be last: serves index.html at "/"
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
