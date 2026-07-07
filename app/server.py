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
import os
import threading
import time
from collections import deque
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import memory, prompts
from .agents import art_director as _art, copywriter as _copy, critic as _crit, director, strategist
from .blackboard import Blackboard, Job

_PROMPT_DEFAULTS = {
    "strategist": strategist._SYS,
    "copywriter": _copy._SYS,
    "art_director": _art._SCENE_SYS,
    "critic": _crit._RUBRIC,
}

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "output"
OUTPUT.mkdir(exist_ok=True)

app = FastAPI(title="AdLoop", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def _no_cache_spa(request, call_next):
    """Never let the browser cache the SPA — otherwise code changes silently don't take effect."""
    response = await call_next(request)
    p = request.url.path
    if p == "/" or p.endswith((".js", ".css", ".html")):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    return response
app.mount("/assets", StaticFiles(directory=str(OUTPUT)), name="assets")

# In-process job registry (single-instance MVP; swap for Redis to scale horizontally).
JOBS: dict[str, Job] = {}

# --- Rate limiting -----------------------------------------------------------
# No user login yet, so the public demo endpoint is protected with simple in-memory caps
# that bound DashScope/Apify spend and abuse. Tunable via env. (Per-instance; swap for Redis
# behind a load balancer.) Each generation run burns real model + Apify credits, so this is
# the guardrail on a wide-open URL.
_MAX_CONCURRENT = int(os.getenv("ADLOOP_MAX_CONCURRENT_JOBS", "2"))
_PER_IP_PER_HOUR = int(os.getenv("ADLOOP_PER_IP_PER_HOUR", "6"))
_GLOBAL_PER_HOUR = int(os.getenv("ADLOOP_GLOBAL_PER_HOUR", "40"))
_rl_lock = threading.Lock()
_ip_hits: dict[str, deque] = {}
_global_hits: deque = deque()
_active_jobs = 0


def _client_ip(request: Optional[Request]) -> str:
    if request is None:
        return "unknown"
    fwd = request.headers.get("x-forwarded-for")  # honor proxy/CDN in front of the app
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _rate_check(ip: str) -> Optional[str]:
    """Return an error message if this request should be rejected, else None."""
    now = time.time()
    with _rl_lock:
        if _active_jobs >= _MAX_CONCURRENT:
            return "The society is busy with other campaigns right now — please try again in a minute."
        while _global_hits and now - _global_hits[0] > 3600:
            _global_hits.popleft()
        if len(_global_hits) >= _GLOBAL_PER_HOUR:
            return "AdLoop has hit its hourly generation cap on this demo instance. Please try again later."
        dq = _ip_hits.get(ip)
        if dq:
            while dq and now - dq[0] > 3600:
                dq.popleft()
            if len(dq) >= _PER_IP_PER_HOUR:
                return (f"You've started {_PER_IP_PER_HOUR} campaigns this hour — the demo limit per visitor. "
                        "Please try again later.")
    return None


def _rl_start(ip: str) -> None:
    global _active_jobs
    now = time.time()
    with _rl_lock:
        _active_jobs += 1
        _global_hits.append(now)
        _ip_hits.setdefault(ip, deque()).append(now)


def _rl_done() -> None:
    global _active_jobs
    with _rl_lock:
        _active_jobs = max(0, _active_jobs - 1)


def _asset_url(image_path: Optional[str]) -> Optional[str]:
    """Map a stored image path to a browser URL served by the /assets mount."""
    if not image_path:
        return None
    s = str(image_path).replace("\\", "/")
    if "/output/" in s:
        rel = s.split("/output/", 1)[1]
    elif s.startswith("output/"):
        rel = s[len("output/"):]
    else:
        rel = Path(s).name
    return "/assets/" + rel.lstrip("/")


def _persist_run(job: Job, kit: Optional[dict], channel: str) -> None:
    """Save the full society log + creatives of a finished run so History can replay it."""
    try:
        payload = job.as_dict()
        creatives = payload.get("creatives", []) or []
        scores = [(c.get("scorecard") or {}).get("overall") for c in creatives]
        scores = [s for s in scores if s is not None]
        avg = round(sum(scores) / len(scores), 1) if scores else 0.0
        for c in creatives:
            c["image_url"] = _asset_url(c.get("image_path"))
            for r in c.get("trail") or []:
                r["image_url"] = _asset_url(r.get("image_path"))
        for e in payload.get("log", []) or []:
            d = e.get("data") or {}
            if d.get("image_path"):
                d["image_url"] = _asset_url(d["image_path"])
        memory.save_run(job.id, (kit or {}).get("name", "Untitled"), job.chat_request,
                        channel, job.status, avg, payload)
    except Exception:
        pass  # history is best-effort; never break a run over it


def _friendly_error(e: Exception) -> str:
    """Turn a raw exception into something the operator can act on."""
    s = str(e)
    low = s.lower()
    if "image_quota" in low or "freetieronly" in low or "allocationquota" in low or "free quota" in low:
        return ("Image generation is blocked: the DashScope free image quota is exhausted. "
                "Enable paid billing (or turn off “use free tier only”) in the DashScope console, "
                "or set WANX_T2I_MODEL to a model that still has quota.")
    return f"Run failed: {s[:220]}"


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


@app.get("/creatives")
def get_creatives(brand_kit_id: Optional[str] = None, limit: int = 60) -> dict:
    """Persisted gallery — survives page reloads and reconnects (reads from SQLite)."""
    items = memory.list_creatives(brand_kit_id, limit)
    for it in items:
        it["image_url"] = _asset_url(it.get("image_path"))
        for r in it.get("trail") or []:
            r["image_url"] = _asset_url(r.get("image_path"))
    return {"creatives": items}


class GenerateReq(BaseModel):
    brand_kit_id: str
    objective: str
    channel: str = "instagram"
    n: int = 3
    max_rounds: int = 2


@app.post("/generate")
def generate(req: GenerateReq, request: Request) -> dict:
    kit = memory.get_brand_kit(req.brand_kit_id)
    if not kit:
        return {"error": "unknown brand_kit_id"}
    ip = _client_ip(request)
    limited = _rate_check(ip)
    if limited:
        return {"error": limited, "rate_limited": True}
    job = Job(chat_request=req.objective, brand_kit_id=req.brand_kit_id)
    JOBS[job.id] = job
    bb = Blackboard(job)
    _rl_start(ip)

    def _work() -> None:
        try:
            director.run_campaign(kit, req.objective, req.channel, req.n, req.max_rounds, bb=bb)
        except Exception as e:  # surface failures on the log instead of dying silently
            bb.post("director", "info", _friendly_error(e))
            bb.set_status("error")
        finally:
            _persist_run(job, kit, req.channel)  # record success OR failure
            _rl_done()

    threading.Thread(target=_work, daemon=True).start()
    return {"job_id": job.id}


@app.get("/prompts")
def get_prompts() -> dict:
    """Each editable agent prompt — its current text (default or override) + metadata."""
    out = []
    for key, meta in prompts.REGISTRY.items():
        default = _PROMPT_DEFAULTS.get(key, "")
        out.append({
            "key": key, "label": meta["label"], "vars": meta["vars"],
            "prompt": prompts.get(key, default), "default": default,
            "overridden": prompts.is_overridden(key),
        })
    return {"prompts": out}


class PromptReq(BaseModel):
    prompt: str


@app.put("/prompts/{key}")
def set_prompt(key: str, req: PromptReq) -> dict:
    if key not in prompts.REGISTRY:
        return {"error": "unknown agent"}
    prompts.set_override(key, req.prompt)
    return {"ok": True}


@app.post("/prompts/{key}/reset")
def reset_prompt(key: str) -> dict:
    prompts.reset(key)
    return {"ok": True, "prompt": _PROMPT_DEFAULTS.get(key, "")}


class CampaignReq(BaseModel):
    objective: str
    url: Optional[str] = None
    brand_kit_id: Optional[str] = None
    description: Optional[str] = None
    channel: str = "instagram"
    n: int = 3
    max_rounds: int = 2


@app.post("/campaign")
def campaign(req: CampaignReq, request: Request) -> dict:
    """One-shot: extract the brand fresh from a URL, or RE-STRATEGIZE a saved brand (refresh its
    web research on file), then run the society. A saved brand never skips straight to copywriting —
    the Strategist runs again so research stays current."""
    if not (req.url or req.brand_kit_id):
        return {"error": "Provide a product URL or pick a saved brand."}
    ip = _client_ip(request)
    limited = _rate_check(ip)
    if limited:
        return {"error": limited, "rate_limited": True}
    job = Job(chat_request=req.objective, brand_kit_id=req.brand_kit_id)
    JOBS[job.id] = job
    bb = Blackboard(job)
    _rl_start(ip)

    def _work() -> None:
        kit = None
        try:
            if req.url:
                kit = strategist.run(req.url, docs=req.description, persist=True, bb=bb)
            else:
                saved = memory.get_brand_kit(req.brand_kit_id)
                kit = saved
                if saved and saved.get("url"):
                    # Re-strategize: refresh the web research on the saved brand's URL, keeping its
                    # identity so creatives/runs/memory stay linked. Fall back to the stored kit if it fails.
                    try:
                        kit = strategist.run(saved["url"], docs=req.description, persist=True, bb=bb,
                                             brand_kit_id=saved["id"])
                    except Exception as e:  # noqa: BLE001
                        bb.post("strategist", "info", f"Re-research hit a snag ({str(e)[:80]}); using the saved Brand Kit.")
                        kit = saved
                elif saved:
                    bb.post("strategist", "info", "No URL on file for this brand — using the saved Brand Kit as-is.")
            if not kit:
                bb.post("director", "info", "Could not resolve a brand for this campaign.")
                bb.set_status("error")
                return
            job.brand_kit_id = kit.get("id")
            director.run_campaign(kit, req.objective, req.channel, req.n, req.max_rounds, bb=bb)
        except Exception as e:
            bb.post("director", "info", _friendly_error(e))
            bb.set_status("error")
        finally:
            # Always record the run (success OR failure) so History reflects what happened.
            _persist_run(job, kit, req.channel)
            _rl_done()

    threading.Thread(target=_work, daemon=True).start()
    return {"job_id": job.id}


@app.get("/runs")
def list_runs_ep() -> dict:
    return {"runs": memory.list_runs()}


@app.get("/runs/{run_id}")
def get_run_ep(run_id: str) -> dict:
    r = memory.get_run(run_id)
    return r or {"error": "unknown run"}


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
