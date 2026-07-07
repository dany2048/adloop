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

import os
import uuid
from pathlib import Path
from typing import Any

from PIL import Image

from .. import config, product, prompts, qwen_client, render

_USE_PRODUCT = os.getenv("ADLOOP_USE_PRODUCT", "1") == "1"

_OUT = Path(__file__).resolve().parent.parent.parent / "output" / "creatives"

_REGION = {
    "lower": "lower third",
    "top": "upper third",
    "center": "edges, keeping the middle calm",
    "band": "upper two-thirds — keep the product high in frame; a solid band will cover the lower third",
}

_SCENE_SYS = """You write prompts for a text-to-image model that generates AD BACKGROUNDS.
Output ONLY the prompt text, nothing else. Hard requirements:
- The scene contains NO text, NO words, NO letters, NO logos, NO typography of any kind.
- Leave clean, uncluttered negative space in the {region} so a headline can be overlaid later.
- Photographic, commercial advertising quality, strong single focal point.
- Obey the brand's visual rules and palette. Match the angle's mood."""


def _scene_prompt(brief: dict[str, Any], brand_kit: dict[str, Any], layout: str, extra: str = "", design_brief: dict[str, Any] | None = None, product_mode: bool = False) -> str:
    region = _REGION.get(layout, "lower third")
    user = (
        f"BRAND: {brand_kit.get('name','')} — {brand_kit.get('product_summary','')}\n"
        f"VISUAL RULES: {brand_kit.get('rules', [])}\n"
        f"PALETTE: {brand_kit.get('palette', [])}\n"
        f"AD ANGLE: {brief.get('angle_name','')} — {brief.get('dream_outcome','')}\n"
        f"ART DIRECTION HINT: {brief.get('visual_idea','')}\n"
    )
    if brief.get("director_note"):
        user += f"DIRECTOR'S EMPHASIS FOR THIS VARIANT: {brief['director_note']}\n"
    otype = (brand_kit.get("offering_type") or "product").lower()
    vdir = brand_kit.get("visual_direction", "")
    if vdir:
        user += f"VISUAL DIRECTION (follow this): {vdir}\n"
    if otype == "service":
        user += ("This brand is a SERVICE, not a physical product — do NOT depict a product object or packaging. Show the OUTCOME "
                 "or experience: confident real people, an aspirational real-world result, or a clean conceptual scene conveying the "
                 "benefit. Editorial, human, premium advertising photography.\n")
    elif otype == "app":
        user += ("This is an APP / SOFTWARE — show it IN CONTEXT: a modern smartphone or laptop on a clean minimal surface with a soft, "
                 "glowing, abstract on-screen UI (no detailed text or fake buttons), or a sleek modern digital scene. Crisp, premium, "
                 "tech-forward. Do NOT depict a physical retail product or packaging.\n")
    if product_mode:
        user += ("IMPORTANT: Generate ONLY an empty background environment/surface that fits the brand — "
                 "NO product, NO main object, NO people in frame. The real product photo will be composited "
                 "on top, centered in the upper area, so keep that zone clean and uncluttered.\n")
    if design_brief:
        user += (
            f"DESIGN DIRECTION (from real references, follow it): composition: {design_brief.get('composition','')}; "
            f"mood: {design_brief.get('mood','')}; palette emphasis: {design_brief.get('palette_emphasis','')}.\n"
        )
    if extra:
        user += f"REVISION NOTES (must address): {extra}\n"
    return qwen_client.chat(
        [{"role": "system", "content": prompts.render("art_director", _SCENE_SYS, region=region)}, {"role": "user", "content": user}],
        model=config.TEXT_MODEL, temperature=0.7,
    ).strip()


def _composite_product(scene_path: Path, product_img: Image.Image, layout: str) -> None:
    """Paste the real product cutout onto the generated backdrop, in the clean upper zone."""
    scene = Image.open(scene_path).convert("RGBA")
    W, H = scene.size
    target_w = int(W * 0.58)
    pw, ph = target_w, int(product_img.height * (target_w / product_img.width))
    max_h = int(H * (0.46 if layout == "band" else 0.52))
    if ph > max_h:
        ph, pw = max_h, int(product_img.width * (max_h / product_img.height))
    resized = product_img.resize((max(pw, 1), max(ph, 1)))
    x = (W - pw) // 2
    y = int(H * (0.30 if layout == "top" else 0.09))  # keep clear of the text zone
    scene.alpha_composite(resized, (x, y))
    scene.convert("RGB").save(scene_path)


def _build(brief, brand_kit, channel, layout, scene_prompt, cid, product_img=None) -> dict[str, Any]:
    # unique per render so a revision never overwrites the earlier (rejected) round's image
    rid = uuid.uuid4().hex[:10]
    scene_path = _OUT / f"{rid}_scene.png"
    qwen_client.generate_image(scene_prompt, out_path=scene_path,
                               size="1080*1350" if channel == "instagram" else "1024*1024",
                               negative_prompt="text, words, letters, watermark, logo, caption")
    if product_img is not None:
        try:
            _composite_product(scene_path, product_img, layout)
        except Exception:
            pass  # fall back to the generated scene if compositing fails
    ad_path = _OUT / f"{rid}.png"
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
    # NB: layout is chosen per-angle by the Director for variety; the design_brief still
    # shapes composition/mood/palette via _scene_prompt, just not a single forced layout.
    otype = (brand_kit.get("offering_type") or "product").lower()
    product_img = product.cutout(brand_kit.get("logo_url")) if (_USE_PRODUCT and otype == "product") else None
    if bb:
        extra = " (compositing the real product)" if product_img is not None else ""
        bb.post("art_director", "info", f"Designing “{brief.get('angle_name','')}”{extra} — generating scene + composing type.")
    sp = _scene_prompt(brief, brand_kit, layout, design_brief=design_brief, product_mode=product_img is not None)
    creative = _build(brief, brand_kit, channel, layout, sp, cid, product_img=product_img)
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
    otype = (brand_kit.get("offering_type") or "product").lower()
    product_img = product.cutout(brand_kit.get("logo_url")) if (_USE_PRODUCT and otype == "product") else None
    if bb:
        bb.post("art_director", "revise", f"Revising {creative['id']} per critic: {notes[:160]}")
    sp = _scene_prompt(creative["brief"], brand_kit, layout, extra=notes, design_brief=design_brief, product_mode=product_img is not None)
    return _build(creative["brief"], brand_kit, creative.get("channel_size", "instagram"),
                  layout, sp, creative["id"], product_img=product_img)


if __name__ == "__main__":
    import json
    from .. import memory
    from .critic import run as critic_run

    memory.init_db()
    kits = memory.list_brand_kits()
    kit = kits[0] if kits else {"name": "Lumora", "palette": ["#A8C686", "#6B7F61", "#000"], "rules": []}
    brief = {
        "angle_name": "Transformation", "dream_outcome": "Effortless everyday comfort",
        "headline": "MADE FOR MOVEMENT", "subhead": "The everyday essential, reimagined.",
        "cta": "Shop the bestseller", "visual_idea": "a single product in warm natural light on wood",
    }
    c = run(brief, kit, channel="instagram", layout="lower")
    print("creative ->", c["image_path"])
    v = critic_run(c["image_path"], brief, kit)
    print(json.dumps(v, indent=2))
