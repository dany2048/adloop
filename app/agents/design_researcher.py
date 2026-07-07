"""
Design Researcher agent.

Premise: AI is bad at *inventing* visual creativity, so we don't ask it to. This agent
RETRIEVES real ad/design references (live from Pinterest via Apify), then uses Qwen-VL to
read those references and distill a concrete DESIGN BRIEF — layout, composition, palette
emphasis, mood, type treatment — that constrains the Art Director. Grounded creativity.

Hybrid by design: if the live Pinterest scrape is unavailable (no Apify credit / error),
it falls back to a curated, ad-craft design brief so the pipeline never blocks. The brief
records which source it used.
"""
from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from typing import Any

import requests

from .. import config, qwen_client

_PIN_ENDPOINT = f"https://api.apify.com/v2/acts/{config.PINTEREST_ACTOR}/run-sync-get-dataset-items"
_IMG_RE = re.compile(r"https?://[^\s\"']+?\.(?:jpg|jpeg|png|webp)", re.I)
_PINIMG_RE = re.compile(r"https?://i\.pinimg\.com/[^\s\"']+", re.I)

_LAYOUTS = {"lower", "top", "center"}


def _query(brand_kit: dict[str, Any], objective: str) -> str:
    name = brand_kit.get("product_summary", "") or brand_kit.get("name", "")
    return f"{name} instagram ad creative design layout".strip()


# Only accept large sizes — this drops the tiny 30x30/60x60/236x junk thumbnails
# (placeholder "photo coming soon" images, favicons, logos) that look terrible as references.
_ACCEPT = ["/originals/", "/736x/", "/564x/", "/474x/"]


def _pinterest_search(query: str, limit: int = 6) -> list[str]:
    """Live Pinterest reference URLs via Apify. Raises on any failure (caller falls back)."""
    if not config.APIFY_API_KEY:
        raise RuntimeError("no APIFY_API_KEY")
    r = requests.post(
        _PIN_ENDPOINT,
        params={"token": config.APIFY_API_KEY},
        json={"queries": [query], "limit": max(limit * 3, 18), "type": "all-pins"},
        timeout=220,
    )
    data = r.json()
    if isinstance(data, dict) and data.get("error"):
        raise RuntimeError(data["error"].get("type", "apify error"))

    # Each pin yields the same image at several sizes (…/<size>/<hash>.jpg). Keep the largest
    # ACCEPTED size per unique hash; skip anything only available below 474x (that's the junk).
    best: dict[str, tuple[int, str]] = {}
    for u in _PINIMG_RE.findall(json.dumps(data)):
        key = u.rsplit("/", 1)[-1]  # the hash filename = the unique image
        rank = next((i for i, s in enumerate(_ACCEPT) if s in u), None)
        if rank is None:
            continue  # too small / placeholder → skip
        if key not in best or rank < best[key][0]:
            best[key] = (rank, u)
    urls = [u for _, u in sorted(best.values())]  # best quality first
    if not urls:
        raise RuntimeError("no usable references")
    return urls[:limit]


def _img_to_data_url(content: bytes, mime: str = "image/jpeg") -> str:
    return f"data:{mime};base64,{base64.b64encode(content).decode()}"


def _analyze_references(urls: list[str], brand_kit: dict[str, Any]) -> dict[str, Any]:
    """Qwen-VL reads real reference images → a concrete design brief."""
    parts: list[dict[str, Any]] = []
    for u in urls[:3]:
        try:
            resp = requests.get(u, timeout=30)
            if resp.status_code == 200:
                parts.append({"type": "image_url", "image_url": {"url": _img_to_data_url(resp.content)}})
        except Exception:
            continue
    if not parts:
        raise RuntimeError("could not fetch reference images")
    parts.append({"type": "text", "text": (
        "These are real, high-performing ad/design references. Study their shared design DNA and distill a "
        f"DESIGN BRIEF for a new ad for this brand (tone: {brand_kit.get('tone','')}). "
        "Respond ONLY with JSON: {\"layout\":\"lower|top|center\",\"composition\":\"...\",\"palette_emphasis\":\"...\","
        "\"mood\":\"...\",\"type_style\":\"...\",\"rationale\":\"what the references have in common\"}"
    )})
    raw = qwen_client._client.chat.completions.create(
        model=config.VL_MODEL,
        messages=[{"role": "user", "content": parts}],
        temperature=0.3,
    ).choices[0].message.content or "{}"
    return _parse_json(raw)


def _parse_json(text: str) -> dict[str, Any]:
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, flags=re.DOTALL)
        return json.loads(m.group(0)) if m else {}


def _curated_brief(brand_kit: dict[str, Any], objective: str) -> dict[str, Any]:
    """Fallback: an ad-craft design brief from Qwen when live references aren't available."""
    out = qwen_client.chat_json([
        {"role": "system", "content": "You are an award-winning art director. Output ONLY JSON."},
        {"role": "user", "content": (
            f"Brand tone: {brand_kit.get('tone','')}. Audience: {brand_kit.get('audience','')}. "
            f"Objective: {objective}. Give a concrete design brief grounded in proven direct-response ad design. "
            "JSON keys: layout (lower|top|center), composition, palette_emphasis, mood, type_style, rationale."
        )},
    ], model=config.TEXT_MODEL)
    return out


def run(brand_kit: dict[str, Any], objective: str, channel: str = "instagram", bb=None) -> dict[str, Any]:
    query = _query(brand_kit, objective)
    source, refs, brief = "curated", [], {}
    try:
        if bb:
            bb.post("design_researcher", "info", f"Searching Pinterest for real references: “{query}”")
        refs = _pinterest_search(query)
        brief = _analyze_references(refs, brand_kit)
        source = "pinterest"
        if bb:
            bb.post("design_researcher", "draft", f"Studied {len(refs)} real references → design direction set.", references=refs[:6])
    except Exception as e:
        if bb:
            bb.post("design_researcher", "info", f"Live Pinterest unavailable ({str(e)[:60]}). Using curated design library.")
        brief = _curated_brief(brand_kit, objective)

    layout = (brief.get("layout") or "lower").lower()
    brief["layout"] = layout if layout in _LAYOUTS else "lower"
    brief["source"] = source
    brief["references"] = refs[:6]
    if bb:
        bb.post("design_researcher", "draft",
                f"Design brief ({source}): {brief['layout']} layout · {brief.get('mood','')}", design_brief=brief)
    return brief


if __name__ == "__main__":
    from .. import memory
    memory.init_db()
    kit = memory.list_brand_kits()[0]
    print(json.dumps(run(kit, "Drive first purchases for the summer collection"), indent=2, ensure_ascii=False))
