"""
Single-agent baseline — the naive "just prompt an LLM + image model" approach.

ONE model call writes N ad concepts (headline/subhead/CTA + scene prompt); each is generated
and rendered once. No copy doctrine, no design research, no critic, no revision, no memory.
This is the control we benchmark the agent society against (Track-3 efficiency-gain proof).
"""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from . import config, qwen_client, render

_OUT = Path(__file__).resolve().parent.parent / "output" / "baseline"

_SYS = "You are an assistant that writes social ad concepts. Output ONLY JSON."


def generate_baseline(brand_kit: dict[str, Any], objective: str, channel: str = "instagram", n: int = 3) -> list[dict[str, Any]]:
    spec = qwen_client.chat_json(
        [
            {"role": "system", "content": _SYS},
            {"role": "user", "content": (
                f"Brand: {brand_kit.get('name','')} — {brand_kit.get('product_summary','')}. "
                f"Objective: {objective}. Write {n} ad concepts. JSON: "
                '{"ads":[{"headline":"...","subhead":"...","cta":"...","scene_prompt":"a vivid image scene, no text"}]}'
            )},
        ],
        model=config.PLAN_MODEL,
    )
    ads = (spec.get("ads") or [])[:n] if isinstance(spec, dict) else []

    creatives = []
    for ad in ads:
        cid = "base_" + uuid.uuid4().hex[:8]
        scene = _OUT / f"{cid}_scene.png"
        try:
            qwen_client.generate_image(ad.get("scene_prompt", ""), out_path=scene,
                                       size="1080*1350", negative_prompt="text, words, watermark, logo")
            ad_path = _OUT / f"{cid}.png"
            render.render_ad(bg_image_path=scene, out_path=ad_path,
                             headline=ad.get("headline", ""), subhead=ad.get("subhead", ""),
                             cta=ad.get("cta", ""), palette=brand_kit.get("palette"),
                             fonts=brand_kit.get("fonts"), layout="lower", channel=channel)
            creatives.append({"id": cid, "brief": ad, "image_path": str(ad_path), "channel_size": channel, "source": "baseline"})
        except Exception as e:
            print("baseline gen failed:", e)
    return creatives
