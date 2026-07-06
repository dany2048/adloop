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

from .. import memory
from ..blackboard import Blackboard, Job
from . import art_director, copywriter, critic, design_researcher, strategist

MAX_ROUNDS = int(os.getenv("ADLOOP_MAX_ROUNDS", "2"))


def _produce_one(angle, brand_kit, channel, max_rounds, bb, design_brief=None) -> dict[str, Any]:
    """Run the Art Director ↔ Critic loop for a single angle; return the best creative."""
    creative = art_director.run(angle, brand_kit, channel, bb=bb, design_brief=design_brief)
    verdict = critic.run(creative["image_path"], angle, brand_kit, bb=bb)
    best = (creative, verdict)

    rounds = 0
    while not verdict["pass"] and rounds < max_rounds:
        rounds += 1
        bb.post("director", "info", f"“{angle.get('angle_name','')}” at {verdict['overall']}/100 — sending back for revision (round {rounds}).")
        creative = art_director.revise(creative, verdict["required_changes"], brand_kit, bb=bb, design_brief=design_brief)
        verdict = critic.run(creative["image_path"], angle, brand_kit, bb=bb)
        if verdict["overall"] > best[1]["overall"]:
            best = (creative, verdict)

    creative, verdict = best
    creative["scorecard"] = verdict["scores"]
    creative["status"] = "pass" if verdict["pass"] else "best_effort"
    creative["rationale"] = (
        f"Angle: {angle.get('angle_name','')} ({angle.get('framework','')}). "
        f"Final critic score {verdict['overall']}/100. {verdict['rationale']}"
    )
    return creative, verdict


def run_campaign(brand_kit, objective, channel="instagram", n=3, max_rounds=MAX_ROUNDS, bb=None) -> list[dict[str, Any]]:
    if bb is None:
        bb = Blackboard(Job(chat_request=objective, brand_kit_id=brand_kit.get("id")))
    bb.set_status("running")
    bb.post("director", "plan", f"Brief: “{objective}”. Plan: {n} angles for {channel}, each must pass the critic (≥{critic.PASS_OVERALL}/100) within {max_rounds} revision rounds.")

    angles = copywriter.run(brand_kit, objective, channel, n, bb=bb)
    for a in angles:
        bb.add_brief(a)

    # Ground the visuals in real references (Pinterest) before designing — once per campaign.
    design_brief = design_researcher.run(brand_kit, objective, channel, bb=bb)

    results = []
    for angle in angles:
        creative, verdict = _produce_one(angle, brand_kit, channel, max_rounds, bb, design_brief=design_brief)
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
