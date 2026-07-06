"""
Persistent memory for AdLoop (Track-1 pillar).

SQLite store for:
  - brand_kits   : the extracted brand DNA per business (so we don't re-extract every session)
  - creatives    : every generated ad + its critic scorecard (the performance record)
  - memories     : free-text lessons/preferences, embedded for semantic recall

recall() ranks memories by  cosine(query) × score × recency-decay  — so the most
relevant, highest-performing, freshest context surfaces first and stale low-performers
fade out (Track-1 "timely forgetting"). Embeddings via text-embedding-v3; degrades
gracefully to recency+score ordering if the embedding call is unavailable.
"""
from __future__ import annotations

import json
import math
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

from . import config, qwen_client

_DECAY_TAU_DAYS = 30.0  # memories older than ~a month lose half their recency weight


# ---------------------------------------------------------------- connection

def _connect() -> sqlite3.Connection:
    Path(config.DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _connect() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS brand_kits (
                id         TEXT PRIMARY KEY,
                name       TEXT,
                url        TEXT,
                data       TEXT NOT NULL,
                created_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS creatives (
                id            TEXT PRIMARY KEY,
                brand_kit_id  TEXT NOT NULL,
                brief         TEXT NOT NULL,
                image_path    TEXT,
                channel_size  TEXT,
                scorecard     TEXT,
                overall_score REAL,
                rationale     TEXT,
                status        TEXT,
                created_at    REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS memories (
                id           TEXT PRIMARY KEY,
                brand_kit_id TEXT NOT NULL,
                kind         TEXT NOT NULL,
                text         TEXT NOT NULL,
                embedding    TEXT,
                score        REAL DEFAULT 0.0,
                created_at   REAL NOT NULL,
                last_used    REAL
            );
            CREATE INDEX IF NOT EXISTS idx_creatives_brand ON creatives(brand_kit_id);
            CREATE INDEX IF NOT EXISTS idx_memories_brand  ON memories(brand_kit_id);
            """
        )


# ---------------------------------------------------------------- brand kits

def save_brand_kit(kit: dict[str, Any]) -> str:
    kit_id = kit.get("id") or uuid.uuid4().hex[:12]
    kit["id"] = kit_id
    with _connect() as c:
        c.execute(
            "INSERT OR REPLACE INTO brand_kits (id, name, url, data, created_at) VALUES (?,?,?,?,?)",
            (kit_id, kit.get("name", ""), kit.get("url", ""), json.dumps(kit), time.time()),
        )
    return kit_id


def get_brand_kit(kit_id: str) -> dict[str, Any] | None:
    with _connect() as c:
        row = c.execute("SELECT data FROM brand_kits WHERE id=?", (kit_id,)).fetchone()
    return json.loads(row["data"]) if row else None


def list_brand_kits() -> list[dict[str, Any]]:
    with _connect() as c:
        rows = c.execute("SELECT data FROM brand_kits ORDER BY created_at DESC").fetchall()
    return [json.loads(r["data"]) for r in rows]


# ---------------------------------------------------------------- creatives

def save_creative(creative: dict[str, Any]) -> str:
    cid = creative.get("id") or uuid.uuid4().hex[:12]
    sc = creative.get("scorecard") or {}
    with _connect() as c:
        c.execute(
            """INSERT OR REPLACE INTO creatives
               (id, brand_kit_id, brief, image_path, channel_size, scorecard,
                overall_score, rationale, status, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                cid,
                creative.get("brand_kit_id", ""),
                json.dumps(creative.get("brief", {})),
                creative.get("image_path"),
                creative.get("channel_size"),
                json.dumps(sc),
                float(sc.get("overall", 0.0) or 0.0),
                creative.get("rationale", ""),
                creative.get("status", ""),
                time.time(),
            ),
        )
    return cid


def top_creatives(brand_kit_id: str, k: int = 3) -> list[dict[str, Any]]:
    """The best past ads for a brand — fed back into the Copywriter/Art Director."""
    with _connect() as c:
        rows = c.execute(
            """SELECT brief, scorecard, overall_score, rationale FROM creatives
               WHERE brand_kit_id=? AND overall_score IS NOT NULL
               ORDER BY overall_score DESC LIMIT ?""",
            (brand_kit_id, k),
        ).fetchall()
    return [
        {
            "brief": json.loads(r["brief"]),
            "scorecard": json.loads(r["scorecard"] or "{}"),
            "overall_score": r["overall_score"],
            "rationale": r["rationale"],
        }
        for r in rows
    ]


# ---------------------------------------------------------------- memories

def add_memory(brand_kit_id: str, kind: str, text: str, score: float = 0.0) -> str:
    """Store a lesson/preference. Embeds for semantic recall (best-effort)."""
    emb: list[float] | None = None
    try:
        emb = qwen_client.embed([text])[0]
    except Exception:
        emb = None  # degrade gracefully; recall falls back to recency+score
    mid = uuid.uuid4().hex[:12]
    with _connect() as c:
        c.execute(
            """INSERT INTO memories (id, brand_kit_id, kind, text, embedding, score, created_at, last_used)
               VALUES (?,?,?,?,?,?,?,?)""",
            (mid, brand_kit_id, kind, text, json.dumps(emb) if emb else None, score, time.time(), None),
        )
    return mid


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def recall(brand_kit_id: str, query: str, k: int = 5) -> list[dict[str, Any]]:
    """
    Return the k most relevant memories for this brand, ranked by
    cosine(query) × (0.5 + 0.5·norm_score) × recency_decay.
    Marks recalled rows' last_used so frequently-useful memories stay fresh.
    """
    with _connect() as c:
        rows = c.execute(
            "SELECT id, kind, text, embedding, score, created_at FROM memories WHERE brand_kit_id=?",
            (brand_kit_id,),
        ).fetchall()
    if not rows:
        return []

    q_emb: list[float] | None = None
    try:
        q_emb = qwen_client.embed([query])[0]
    except Exception:
        q_emb = None

    scores = [r["score"] or 0.0 for r in rows]
    max_score = max(scores) or 1.0
    now = time.time()

    ranked: list[tuple[float, sqlite3.Row]] = []
    for r in rows:
        age_days = (now - r["created_at"]) / 86400.0
        recency = math.exp(-age_days / _DECAY_TAU_DAYS)
        norm_score = 0.5 + 0.5 * ((r["score"] or 0.0) / max_score)
        if q_emb and r["embedding"]:
            sim = _cosine(q_emb, json.loads(r["embedding"]))
        else:
            sim = 0.5  # no embedding → lean on recency + score
        ranked.append((sim * norm_score * recency, r))

    ranked.sort(key=lambda t: t[0], reverse=True)
    top = ranked[:k]

    with _connect() as c:
        for _, r in top:
            c.execute("UPDATE memories SET last_used=? WHERE id=?", (now, r["id"]))

    return [{"kind": r["kind"], "text": r["text"], "score": r["score"], "relevance": round(s, 4)} for s, r in top]
