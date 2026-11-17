import asyncio
import shutil
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path

from .config import JOB_TTL_SECONDS, RATE_LIMIT_PER_MINUTE


@dataclass
class Job:
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    status: str = "queued"          # queued | working | done | error
    message: str = "Queued…"
    error: str | None = None
    pdf_path: Path | None = None
    created: float = field(default_factory=time.time)
    dir: Path | None = None


_hits: dict[str, deque] = defaultdict(deque)


def rate_limited(ip: str) -> bool:
    now, q = time.time(), _hits[ip]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= RATE_LIMIT_PER_MINUTE:
        return True
    q.append(now)
    return False


async def janitor(jobs: dict[str, Job]) -> None:
    """Delete finished jobs (and their files) after JOB_TTL_SECONDS."""
    while True:
        await asyncio.sleep(60)
        cutoff = time.time() - JOB_TTL_SECONDS
        for jid in [j for j, job in jobs.items() if job.created < cutoff]:
            job = jobs.pop(jid)
            if job.dir:
                shutil.rmtree(job.dir, ignore_errors=True)
