"""
FastAPI server for AdLoop.

Wraps the agent society behind a small API and streams the blackboard log live so the
frontend can show the team working in real time.

  GET  /healthz                  -> liveness (Alibaba load balancer / deploy proof)
  POST /brand     {url, docs?}    -> extract + persist a BrandKit (Strategist)
  GET  /brands                    -> list known brands (from memory)
  POST /generate  {...}           -> kick off a campaign in the background, returns {job_id}
  GET  /job/{id}                  -> full job snapshot (briefs, creatives, log)
  GET  /job/{id}/stream           -> Server-Sent Events of the agent log as it happens
  GET  /assets/...                -> generated creative PNGs
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import memory
from .agents import director, strategist
from .blackboard import Blackboard, Job

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "output"
OUTPUT.mkdir(exist_ok=True)

app = FastAPI(title="AdLoop", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/assets", StaticFiles(directory=str(OUTPUT)), name="assets")

# In-process job registry (single-instance MVP; swap for Redis to scale horizontally).
JOBS: dict[str, Job] = {}


@app.on_event("startup")
def _startup() -> None:
    memory.init_db()


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True, "service": "adloop"}


class BrandReq(BaseModel):
    url: str
    docs: Optional[str] = None


@app.post("/brand")
def make_brand(req: BrandReq) -> dict:
    kit = strategist.run(req.url, docs=req.docs, persist=True)
    return {"brand_kit": kit}


@app.get("/brands")
def list_brands() -> dict:
    return {"brands": memory.list_brand_kits()}


class GenerateReq(BaseModel):
    brand_kit_id: str
    objective: str
    channel: str = "instagram"
    n: int = 3
    max_rounds: int = 2


@app.post("/generate")
def generate(req: GenerateReq) -> dict:
    kit = memory.get_brand_kit(req.brand_kit_id)
    if not kit:
        return {"error": "unknown brand_kit_id"}
    job = Job(chat_request=req.objective, brand_kit_id=req.brand_kit_id)
    JOBS[job.id] = job
    bb = Blackboard(job)

    def _work() -> None:
        try:
            director.run_campaign(kit, req.objective, req.channel, req.n, req.max_rounds, bb=bb)
        except Exception as e:  # surface failures on the log instead of dying silently
            bb.post("director", "info", f"Run failed: {e}")
            bb.set_status("error")

    threading.Thread(target=_work, daemon=True).start()
    return {"job_id": job.id}


@app.get("/job/{job_id}")
def get_job(job_id: str) -> dict:
    job = JOBS.get(job_id)
    return job.as_dict() if job else {"error": "unknown job"}


@app.get("/job/{job_id}/stream")
def stream_job(job_id: str) -> StreamingResponse:
    job = JOBS.get(job_id)
    if not job:
        return StreamingResponse(iter([f"data: {json.dumps({'error': 'unknown job'})}\n\n"]),
                                 media_type="text/event-stream")

    def gen():
        sent = 0
        while True:
            while sent < len(job.log):
                yield f"data: {json.dumps(job.log[sent].as_dict())}\n\n"
                sent += 1
            if job.status in ("done", "error"):
                yield f"event: end\ndata: {json.dumps({'status': job.status, 'creatives': job.creatives})}\n\n"
                return
            time.sleep(0.4)

    return StreamingResponse(gen(), media_type="text/event-stream")


# Serve the SPA last so API routes win. (frontend/ is built in the next step.)
_FRONTEND = ROOT / "frontend"
if _FRONTEND.exists():
    app.mount("/", StaticFiles(directory=str(_FRONTEND), html=True), name="frontend")
