"""
Art Director agent.

Takes one ad angle/brief and produces a finished creative:
  1. writes a text-to-image prompt for the BACKGROUND scene only (no words/logos),
     following the brand's visual rules and leaving clean negative space for the type,
  2. generates the scene with Wanxiang,
  3. composites the real headline/subhead/CTA on top via render.py.

On a Critic rejection it ingests the structured `required_changes` and revises —
re-prompting the scene and/or switching layout — then re-renders.
"""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from .. import config, qwen_client, render

_OUT = Path(__file__).resolve().parent.parent.parent / "output" / "creatives"

_REGION = {"lower": "lower third", "top": "upper third", "center": "edges, keeping the middle calm"}

_SCENE_SYS = """You write prompts for a text-to-image model that generates AD BACKGROUNDS.
Output ONLY the prompt text, nothing else. Hard requirements:
- The scene contains NO text, NO words, NO letters, NO logos, NO typography of any kind.
- Leave clean, uncluttered negative space in the {region} so a headline can be overlaid later.
- Photographic, commercial advertising quality, strong single focal point.
- Obey the brand's visual rules and palette. Match the angle's mood."""


def _scene_prompt(brief: dict[str, Any], brand_kit: dict[str, Any], layout: str, extra: str = "", design_brief: dict[str, Any] | None = None) -> str:
    region = _REGION.get(layout, "lower third")
    user = (
        f"BRAND: {brand_kit.get('name','')} — {brand_kit.get('product_summary','')}\n"
        f"VISUAL RULES: {brand_kit.get('rules', [])}\n"
        f"PALETTE: {brand_kit.get('palette', [])}\n"
        f"AD ANGLE: {brief.get('angle_name','')} — {brief.get('dream_outcome','')}\n"
        f"ART DIRECTION HINT: {brief.get('visual_idea','')}\n"
    )
    if design_brief:
        user += (
            f"DESIGN DIRECTION (from real references, follow it): composition: {design_brief.get('composition','')}; "
            f"mood: {design_brief.get('mood','')}; palette emphasis: {design_brief.get('palette_emphasis','')}.\n"
        )
    if extra:
        user += f"REVISION NOTES (must address): {extra}\n"
    return qwen_client.chat(
        [{"role": "system", "content": _SCENE_SYS.format(region=region)}, {"role": "user", "content": user}],
        model=config.TEXT_MODEL, temperature=0.7,
    ).strip()


def _build(brief, brand_kit, channel, layout, scene_prompt, cid) -> dict[str, Any]:
    scene_path = _OUT / f"{cid}_scene.png"
    qwen_client.generate_image(scene_prompt, out_path=scene_path,
                               size="1080*1350" if channel == "instagram" else "1024*1024",
                               negative_prompt="text, words, letters, watermark, logo, caption")
    ad_path = _OUT / f"{cid}.png"
    render.render_ad(
        bg_image_path=scene_path, out_path=ad_path,
        eyebrow=brand_kit.get("name", ""),
        headline=brief.get("headline", ""), subhead=brief.get("subhead", ""), cta=brief.get("cta", ""),
        palette=brand_kit.get("palette"), fonts=brand_kit.get("fonts"),
        layout=layout, channel=channel,
    )
    return {
        "id": cid, "brand_kit_id": brand_kit.get("id"), "brief": brief,
        "image_path": str(ad_path), "scene_path": str(scene_path),
        "channel_size": channel, "layout": layout, "scene_prompt": scene_prompt,
    }


def run(brief, brand_kit, channel="instagram", layout="lower", bb=None, design_brief=None) -> dict[str, Any]:
    cid = uuid.uuid4().hex[:10]
    if design_brief and design_brief.get("layout") in _REGION:
        layout = design_brief["layout"]
    if bb:
        bb.post("art_director", "info", f"Designing “{brief.get('angle_name','')}” — generating scene + composing type.")
    sp = _scene_prompt(brief, brand_kit, layout, design_brief=design_brief)
    creative = _build(brief, brand_kit, channel, layout, sp, cid)
    if bb:
        bb.post("art_director", "render", f"Creative {cid} rendered.", creative_id=cid, image_path=creative["image_path"])
    return creative


def revise(creative, required_changes, brand_kit, bb=None, design_brief=None) -> dict[str, Any]:
    """Apply the Critic's fixes: re-prompt the scene (and/or switch layout), re-render."""
    notes = "; ".join(f"[{c.get('target')}] {c.get('fix')}" for c in required_changes)
    layout = creative.get("layout", "lower")
    # if the critic complained about hierarchy/legibility, try a stronger text zone
    if any(c.get("target") in ("type", "layout") for c in required_changes):
        layout = "lower" if layout != "lower" else "top"
    if bb:
        bb.post("art_director", "revise", f"Revising {creative['id']} per critic: {notes[:160]}")
    sp = _scene_prompt(creative["brief"], brand_kit, layout, extra=notes, design_brief=design_brief)
    return _build(creative["brief"], brand_kit, creative.get("channel_size", "instagram"),
                  layout, sp, creative["id"])


if __name__ == "__main__":
    import json
    from .. import memory
    from .critic import run as critic_run

    memory.init_db()
    kits = memory.list_brand_kits()
    kit = kits[0] if kits else {"name": "Allbirds", "palette": ["#A8C686", "#6B7F61", "#000"], "rules": []}
    brief = {
        "angle_name": "Transformation", "dream_outcome": "Effortless eco-friendly comfort",
        "headline": "MADE FROM NATURE", "subhead": "The world's most comfortable sneakers, from wool.",
        "cta": "Shop the bestseller", "visual_idea": "a single wool sneaker in warm natural light on wood",
    }
    c = run(brief, kit, channel="instagram", layout="lower")
    print("creative ->", c["image_path"])
    v = critic_run(c["image_path"], brief, kit)
    print(json.dumps(v, indent=2))
