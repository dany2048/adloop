"""
Copywriter / Storyteller agent.

Turns a Brand Kit + campaign objective into N DISTINCT ad angles, each a complete
hook → headline → subhead → CTA, every angle driven by a different copy framework
and emotional lever. Its doctrine is compiled once from the Hormozi (offers/leads)
and Sabri Suby (Sell Like Crazy) skills — see app/knowledge/copywriting_playbook.md
— so we get book-grade direct-response craft without live RAG over the books.

It also pulls the brand's best past creatives + recalled lessons from memory, so the
copy gets sharper session over session (the Track-1 "increasingly accurate" effect).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .. import config, memory, prompts, qwen_client

_PLAYBOOK_PATH = Path(__file__).resolve().parent.parent / "knowledge" / "copywriting_playbook.md"


def _load_playbook() -> str:
    try:
        return _PLAYBOOK_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        # Fallback so the agent still runs before the doctrine is compiled in.
        return (
            "Use direct-response fundamentals: lead with the dream outcome, agitate a real "
            "pain (PAS), make a specific big promise, and a single clear CTA. Each angle must "
            "use a different framework and emotional driver."
        )


_SYS = """You are an elite direct-response ad copywriter. You have internalised Alex Hormozi \
($100M Offers & Leads) and Sabri Suby (Sell Like Crazy). You write paid social ad creative that \
stops the scroll and converts — never bland brand fluff, never corporate cliché.

Apply this doctrine (your compiled knowledge):

<doctrine>
{doctrine}
</doctrine>

Hard rules:
- Every angle must use a DIFFERENT primary framework + a DIFFERENT emotional driver. No two angles may feel alike.
- SPECIFICITY IS THE WHOLE GAME. Every hook AND headline MUST anchor to a concrete, real detail from the brand's VALUE PROPS or product facts — a material, a number, a certification, a named benefit, a price, a real outcome. If a line could be pasted onto any brand in the category, it has FAILED. "Rich Flavor, Every Day" fails; "Halal-certified 170g refills, half the price of pods" wins.
- BANNED — never output these or anything like them: "Act Fast", "Limited Stock", "Loved by All", "Trusted by Many", "Rich Flavor Every Day", "Quality You Can Trust", "Elevate Your Everyday", "Discover the Difference", "Experience the Best", "Made for You". Vague filler is an automatic fail.
- One big idea per ad. One clear CTA. Concrete > abstract. Show the dream outcome.
- Stay true to the brand's tone and rules. Never invent claims the brand kit doesn't support — but you MUST use the specific claims it DOES give you.
- Respect the channel's format (headline/primary-text length norms)."""

_TASK = """Return ONE JSON object: {{"angles": [ ... ]}} with exactly {n} angle objects. Each angle:
{{
  "angle_name": str,          // short label, e.g. "Problem-Agitate", "Transformation", "Social Proof", "FOMO/Scarcity", "Founder Story", "Big Promise"
  "framework": str,           // which copy framework governs it (PAS, AIDA, 4 U's, Value-Equation lead, Godfather Offer, etc.)
  "emotional_driver": str,    // the core emotion this pulls (fear of missing out, status, relief, belonging, pride...)
  "dream_outcome": str,       // the after-state this ad sells
  "specific_detail": str,     // the exact real fact this angle is built on — a number, material, certification, price, timeframe, guarantee, result, or named capability (e.g. "170g refill", "halal-certified" for a product; "book 10 clients in 30 days", "cancel anytime", "2-minute setup", "used by 4,000 teams" for a service/app). It MUST appear verbatim in the headline or subhead.
  "hook": str,                // the scroll-stopping first line (this is the most important field) — must contain the specific_detail or another concrete fact
  "headline": str,            // the on-image headline (punchy, <= ~7 words); must be concrete, never vague filler
  "subhead": str,             // supporting line under the headline; carries the specific_detail if the headline is short
  "primary_text": str,        // the platform caption / body copy (2-4 short lines)
  "cta": str,                 // call to action (button-style, e.g. "Shop the bestseller")
  "visual_idea": str          // a one-line hint for the art director (the Art Director may override)
}}
Make the {n} angles genuinely diverse in framework, emotion, and message.

Bar for specificity (match this level):
  WEAK  → headline "Rich Flavor, Every Day"      (generic, rejected)
  STRONG→ headline "170g Refills, Half the Pods"  subhead "Halal-certified Arabica-Robusta gold."
Copy at the WEAK level fails. Every angle must hit the STRONG bar using THIS brand's real facts."""


def run(
    brand_kit: dict[str, Any],
    objective: str,
    channel: str = "instagram",
    n: int = 3,
    bb=None,
) -> list[dict[str, Any]]:
    """Generate N distinct ad angles for a brand + objective."""
    doctrine = _load_playbook()

    # Pull memory: best past ads + recalled lessons for this brand.
    lessons: list[str] = []
    winners: list[dict[str, Any]] = []
    kit_id = brand_kit.get("id")
    if kit_id:
        try:
            recalled = memory.recall(kit_id, f"copywriting lessons for {objective}", k=4)
            lessons = [m["text"] for m in recalled]
            winners = memory.top_creatives(kit_id, k=2)
        except Exception:
            pass

    brand_block = (
        f"BRAND: {brand_kit.get('name','')}\n"
        f"WHAT IT IS: {brand_kit.get('product_summary','')}\n"
        f"AUDIENCE: {brand_kit.get('audience','')}\n"
        f"TONE: {brand_kit.get('tone','')}\n"
        f"VALUE PROPS: {brand_kit.get('value_props', [])}\n"
        f"BRAND RULES: {brand_kit.get('rules', [])}\n"
        f"PRICE: {brand_kit.get('price_hint','')}"
    )
    memory_block = ""
    if lessons:
        memory_block += "\n\nLESSONS THAT WORKED BEFORE (lean into these):\n- " + "\n- ".join(lessons)
    if winners:
        hooks = [w["brief"].get("hook", "") for w in winners if w.get("brief")]
        if any(hooks):
            memory_block += "\n\nPAST HIGH-SCORING HOOKS (echo what worked, don't repeat verbatim):\n- " + "\n- ".join(h for h in hooks if h)

    user = (
        f"CAMPAIGN OBJECTIVE: {objective}\nCHANNEL: {channel}\n\n{brand_block}{memory_block}\n\n"
        "Build each angle on ONE specific value prop or product fact from above and name it concretely in "
        "the hook and headline (a material, number, certification, price, or named outcome). "
        "Reread each hook/headline before finalizing: if it's generic, rewrite it with a real detail.\n\n"
        + _TASK.format(n=n)
    )

    if bb:
        bb.post("copywriter", "info", f"Drafting {n} distinct ad angles for: {objective}")

    result = qwen_client.chat_json(
        [
            {"role": "system", "content": prompts.render("copywriter", _SYS, doctrine=doctrine)},
            {"role": "user", "content": user},
        ],
        model=config.PLAN_MODEL,
        temperature=0.8,
    )
    angles = result.get("angles", []) if isinstance(result, dict) else []

    if bb:
        names = ", ".join(a.get("angle_name", "?") for a in angles)
        bb.post("copywriter", "draft", f"{len(angles)} angles ready: {names}", angles=angles)
    return angles


if __name__ == "__main__":
    import json
    import sys

    from .strategist import run as strat_run

    url = sys.argv[1] if len(sys.argv) > 1 else "https://example.com"
    obj = sys.argv[2] if len(sys.argv) > 2 else "Drive first purchases for the summer collection"
    kit = strat_run(url, persist=True)
    out = run(kit, obj, channel="instagram", n=3)
    print(json.dumps(out, indent=2, ensure_ascii=False))
