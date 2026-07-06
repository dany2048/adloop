"""
Critic agent — the moat.

qwen-vl-max LOOKS at a rendered ad and scores it against an ad-craft rubric that
encodes real direct-response + design discipline (Danyal's craft): scroll-stopping
power, visual hierarchy, text legibility at thumbnail size, brand-rule compliance,
hook/headline clarity, and CTA visibility. It returns structured, actionable fixes
the Art Director can act on — this is the negotiation that drives the revise loop.

`pass` is decided in code (not by the model) so the gate is deterministic.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from .. import config, qwen_client

PASS_OVERALL = float(os.getenv("ADLOOP_PASS_OVERALL", "78"))  # /100
PASS_MIN_DIM = float(os.getenv("ADLOOP_PASS_MIN_DIM", "5"))   # /10

_DIMENSIONS = ["thumbstop", "hierarchy", "legibility", "brand_fit", "hook_clarity", "cta_visibility"]

_RUBRIC = """You are a ruthless senior creative director reviewing a paid social ad BEFORE any ad \
spend. Judge the attached image as it will appear: small, in a fast-scrolling feed. Be specific and \
demanding — your job is to catch what would waste money, then say exactly how to fix it.

Score each dimension 0-10 (10 = excellent):
- thumbstop      : does it stop the scroll in <1s? bold focal point, instant intrigue.
- hierarchy      : one clear focal point; eye flows hook → product → CTA; not cluttered.
- legibility     : is ALL text crisp and readable at thumbnail size? enough contrast? no text on busy areas? safe margins?
- brand_fit      : matches the brand's tone, palette, and rules below?
- hook_clarity   : is the headline/hook a specific, compelling promise — not vague fluff?
- cta_visibility : is the call-to-action present, obvious, and clickable-looking?

BRAND TONE: {tone}
BRAND RULES (must respect): {rules}
BRAND PALETTE: {palette}

THE AD'S INTENDED COPY:
  hook:     {hook}
  headline: {headline}
  subhead:  {subhead}
  cta:      {cta}

Respond with ONLY this JSON (no prose, no code fence):
{{
  "scores": {{"thumbstop": int, "hierarchy": int, "legibility": int, "brand_fit": int, "hook_clarity": int, "cta_visibility": int}},
  "rationale": "2-3 sentences: the single biggest strength and the single biggest weakness",
  "required_changes": [
    {{"target": "scene|type|copy|layout", "issue": "what's wrong", "fix": "the concrete change to make"}}
  ]
}}
If the ad is genuinely strong, return an empty required_changes list."""


def _parse_json(text: str) -> dict[str, Any]:
    """Tolerant JSON extraction from a possibly fenced / chatty VL response."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if m:
            return json.loads(m.group(0))
        raise


def review(image_path: str | Path, brief: dict[str, Any], brand_kit: dict[str, Any]) -> dict[str, Any]:
    """Score one rendered creative. Returns {scores, overall, pass, rationale, required_changes}."""
    instruction = _RUBRIC.format(
        tone=brand_kit.get("tone", ""),
        rules=brand_kit.get("rules", []),
        palette=brand_kit.get("palette", []),
        hook=brief.get("hook", ""),
        headline=brief.get("headline", ""),
        subhead=brief.get("subhead", ""),
        cta=brief.get("cta", ""),
    )
    raw = qwen_client.critique(image_path, instruction, model=config.VL_MODEL)
    verdict = _parse_json(raw)

    scores = {d: float(verdict.get("scores", {}).get(d, 0)) for d in _DIMENSIONS}
    overall = round(sum(scores.values()) / len(scores) * 10, 1)  # → 0-100
    passed = overall >= PASS_OVERALL and min(scores.values()) >= PASS_MIN_DIM

    return {
        "scores": {**{k: int(v) for k, v in scores.items()}, "overall": overall},
        "overall": overall,
        "pass": passed,
        "rationale": verdict.get("rationale", ""),
        "required_changes": verdict.get("required_changes", []),
    }


def run(image_path, brief, brand_kit, bb=None) -> dict[str, Any]:
    if bb:
        bb.post("critic", "info", "Reviewing the creative against the ad-craft rubric…")
    v = review(image_path, brief, brand_kit)
    if bb:
        if v["pass"]:
            bb.post("critic", "verdict", f"PASS ({v['overall']}/100). {v['rationale']}", verdict=v)
        else:
            n = len(v["required_changes"])
            bb.post("critic", "verdict", f"REJECT ({v['overall']}/100) — {n} change(s) required. {v['rationale']}", verdict=v)
    return v


if __name__ == "__main__":
    import sys

    img = sys.argv[1] if len(sys.argv) > 1 else "output/_smoke.png"
    demo_brief = {"hook": "Comfort that lasts all day", "headline": "Made From Nature", "subhead": "Merino wool sneakers", "cta": "Shop now"}
    demo_brand = {"tone": "warm, natural, grounded", "rules": ["warm natural lighting", "show product in real life"], "palette": ["#A8C686", "#000"]}
    print(json.dumps(review(img, demo_brief, demo_brand), indent=2))
