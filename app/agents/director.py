"""
Creative Director — the orchestrator of the society.

Takes a brand + objective, assigns the Copywriter to produce N angles, then for each
angle runs the Art Director ↔ Critic negotiation: generate → critique → (if rejected)
revise per the critic's required_changes → re-critique, up to max_rounds. It keeps the
best-scoring version, writes the result + lessons back to memory (so the system gets
sharper over sessions), and records every move on the blackboard.
"""
from __future__ import annotations

import os
from typing import Any

from .. import config, memory, qwen_client
from ..blackboard import Blackboard, Job
from . import art_director, copywriter, critic, design_researcher, strategist

MAX_ROUNDS = int(os.getenv("ADLOOP_MAX_ROUNDS", "2"))
_LAYOUTS = ["lower", "band", "top"]
_VALID_LAYOUTS = {"lower", "band", "top", "center"}


def _plan(brand_kit, objective, channel, n, bb=None) -> dict[str, Any]:
    """The Director actually PLANS the campaign with the LLM: a strategic rationale plus a
    per-variant layout + creative emphasis, so the set is deliberately diverse and on-strategy.
    Falls back to a sensible layout rotation if the model call fails (never blocks a run)."""
    fallback = {
        "rationale": (f"Ship {n} distinct angles for {channel}, rotating layouts so the set reads as a "
                      f"campaign rather than one template repeated. Every variant must clear the critic bar."),
        "angles": [{"layout": _LAYOUTS[i % len(_LAYOUTS)], "emphasis": ""} for i in range(n)],
    }
    try:
        plan = qwen_client.chat_json(
            [
                {"role": "system", "content": (
                    "You are the Creative Director of an AI ad-agency society. Given a brand and an objective, "
                    "you plan a multi-variant campaign: set the layout and the creative emphasis for EACH variant "
                    "so the batch is diverse, non-repetitive, and on-strategy. Output ONLY JSON.")},
                {"role": "user", "content": (
                    f"BRAND: {brand_kit.get('name','')} — {brand_kit.get('product_summary','')}\n"
                    f"AUDIENCE: {brand_kit.get('audience','')}\nTONE: {brand_kit.get('tone','')}\n"
                    f"VALUE PROPS: {brand_kit.get('value_props', [])}\n"
                    f"OBJECTIVE: {objective}\nCHANNEL: {channel}\nVARIANTS: {n}\n"
                    "Available layouts: lower, band, top, center.\n\n"
                    "Return JSON: {\"rationale\": str (2-3 sentences on the campaign strategy and how the variants "
                    "differ), \"angles\": [{\"layout\": one of lower|band|top|center, \"emphasis\": short phrase "
                    f"naming what THIS variant should push}}, ... exactly {n} items]}}")},
            ],
            model=config.PLAN_MODEL,
        )
        raw = plan.get("angles") or []
        if not raw:
            return fallback
        angles = []
        for i in range(n):
            a = raw[i % len(raw)]
            lay = str(a.get("layout", "lower")).lower()
            angles.append({
                "layout": lay if lay in _VALID_LAYOUTS else _LAYOUTS[i % len(_LAYOUTS)],
                "emphasis": (a.get("emphasis") or "").strip(),
            })
        return {"rationale": (plan.get("rationale") or fallback["rationale"]).strip(), "angles": angles}
    except Exception:
        if bb:
            bb.post("director", "info", "Planning model unavailable — using a default layout rotation.")
        return fallback


def _round_rec(n, creative, verdict) -> dict[str, Any]:
    """One entry in the critic trail: this round's image + what the critic said about it."""
    return {
        "round": n,
        "image_path": creative["image_path"],
        "overall": verdict["overall"],
        "pass": verdict["pass"],
        "scores": verdict["scores"],
        "rationale": verdict["rationale"],
        "required_changes": verdict["required_changes"],
        "kept": False,
    }


def _produce_one(angle, brand_kit, channel, max_rounds, bb, design_brief=None, layout="lower") -> dict[str, Any]:
    """Run the Art Director ↔ Critic loop for a single angle; return the best creative + full trail."""
    creative = art_director.run(angle, brand_kit, channel, layout=layout, bb=bb, design_brief=design_brief)
    verdict = critic.run(creative["image_path"], angle, brand_kit, bb=bb)
    trail = [_round_rec(0, creative, verdict)]
    best = (creative, verdict)

    rounds = 0
    while not verdict["pass"] and rounds < max_rounds:
        rounds += 1
        bb.post("director", "info", f"“{angle.get('angle_name','')}” at {verdict['overall']}/100 — sending back for revision (round {rounds}).")
        creative = art_director.revise(creative, verdict["required_changes"], brand_kit, bb=bb, design_brief=design_brief)
        verdict = critic.run(creative["image_path"], angle, brand_kit, bb=bb)
        trail.append(_round_rec(rounds, creative, verdict))
        if verdict["overall"] > best[1]["overall"]:
            best = (creative, verdict)

    creative, verdict = best
    # mark which round was kept (match on the winning image)
    for r in trail:
        r["kept"] = r["image_path"] == creative["image_path"]
    creative["scorecard"] = verdict["scores"]
    creative["status"] = "pass" if verdict["pass"] else "best_effort"
    creative["trail"] = trail
    creative["rationale"] = (
        f"Angle: {angle.get('angle_name','')} ({angle.get('framework','')}). "
        f"Final critic score {verdict['overall']}/100 after {len(trail)} round(s). {verdict['rationale']}"
    )
    return creative, verdict


def run_campaign(brand_kit, objective, channel="instagram", n=3, max_rounds=MAX_ROUNDS, bb=None) -> list[dict[str, Any]]:
    if bb is None:
        bb = Blackboard(Job(chat_request=objective, brand_kit_id=brand_kit.get("id")))
    bb.set_status("running")
    # The Director plans the campaign with the LLM: strategic rationale + per-variant layout/emphasis.
    plan = _plan(brand_kit, objective, channel, n, bb=bb)
    bb.post("director", "plan",
            f"Strategy: {plan['rationale']} Delivering {n} variants for {channel}; each must clear the "
            f"critic (≥{critic.PASS_OVERALL}/100) within {max_rounds} revision rounds.")

    angles = copywriter.run(brand_kit, objective, channel, n, bb=bb)
    for a in angles:
        bb.add_brief(a)

    # Ground the visuals in real references (Pinterest) before designing — once per campaign.
    design_brief = design_researcher.run(brand_kit, objective, channel, bb=bb)

    plan_angles = plan["angles"]
    results = []
    for i, angle in enumerate(angles):
        slot = plan_angles[i % len(plan_angles)]
        layout = slot["layout"]
        if slot.get("emphasis"):
            angle["director_note"] = slot["emphasis"]  # the Director's per-variant steer for the Art Director
        creative, verdict = _produce_one(angle, brand_kit, channel, max_rounds, bb, design_brief=design_brief, layout=layout)
        creative["design_refs"] = (design_brief or {}).get("references", [])  # the real Pinterest refs that grounded this
        memory.save_creative(creative)
        # learn: store the critic's top lesson, weighted by the score it ended at
        for ch in verdict.get("required_changes", [])[:1]:
            if brand_kit.get("id"):
                memory.add_memory(brand_kit["id"], "lesson", f"{ch.get('issue','')} → {ch.get('fix','')}", score=verdict["overall"] / 100.0)
        bb.add_creative(creative)
        results.append(creative)

    passed = sum(1 for c in results if c["status"] == "pass")
    bb.set_status("done")
    bb.post("director", "final", f"Delivered {len(results)} creatives ({passed} passed the critic outright). Avg score {round(sum(c['scorecard']['overall'] for c in results)/len(results),1)}/100.")
    return results


def run_from_url(url, objective, channel="instagram", n=3, max_rounds=MAX_ROUNDS, docs=None) -> dict[str, Any]:
    """Full pipeline from a cold URL: extract brand (or reuse memory) → run the campaign."""
    job = Job(chat_request=objective)
    bb = Blackboard(job)
    bb.set_status("running")
    bb.post("director", "plan", f"New request on {url}: {objective}")
    brand_kit = strategist.run(url, docs=docs, persist=True, bb=bb)
    job.brand_kit_id = brand_kit.get("id")
    creatives = run_campaign(brand_kit, objective, channel, n, max_rounds, bb=bb)
    return {"job": job.as_dict(), "brand_kit": brand_kit, "creatives": creatives}


if __name__ == "__main__":
    import json

    memory.init_db()
    kits = memory.list_brand_kits()
    kit = kits[0]
    out = run_campaign(kit, "Drive first purchases for the summer collection", channel="instagram", n=1, max_rounds=1)
    print(json.dumps([{"id": c["id"], "status": c["status"], "score": c["scorecard"]["overall"], "img": c["image_path"]} for c in out], indent=2))
