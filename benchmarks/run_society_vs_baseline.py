"""
Track-3 deliverable: measurable efficiency gain of the agent society over a single-agent baseline.

Same brand + objective for both. Baseline = one-shot LLM+image (app/baseline.py). Society = the
full Director loop. Every creative from BOTH sides is scored by the SAME Critic rubric, then we
report average score, pass rate, and per-dimension deltas.

    python benchmarks/run_society_vs_baseline.py [N] [max_rounds]
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import baseline, memory  # noqa: E402
from app.agents import critic, director  # noqa: E402

DIMS = ["thumbstop", "hierarchy", "legibility", "brand_fit", "hook_clarity", "cta_visibility"]


def _agg(scored: list[dict]) -> dict:
    n = len(scored) or 1
    overall = sum(s["scores"]["overall"] for s in scored) / n
    passes = sum(1 for s in scored if s["pass"]) / n
    dims = {d: round(sum(s["scores"].get(d, 0) for s in scored) / n, 2) for d in DIMS}
    return {"n": len(scored), "avg_overall": round(overall, 1), "pass_rate": round(passes * 100), "dims": dims}


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    rounds = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    memory.init_db()
    kit = memory.list_brand_kits()[0]
    objective = "Drive first purchases for the summer collection"
    print(f"Brand: {kit['name']} | N={n} | society max_rounds={rounds}\n")

    # --- baseline (score each with the critic) ---
    print("Generating baseline (single-agent)…")
    base = baseline.generate_baseline(kit, objective, n=n)
    base_scored = [{**critic.review(c["image_path"], c["brief"], kit)} for c in base]

    # --- society (already critic-scored during the run) ---
    print("Running the agent society…")
    soc = director.run_campaign(kit, objective, n=n, max_rounds=rounds)
    soc_scored = [{"scores": c["scorecard"], "pass": c["status"] == "pass"} for c in soc]

    result = {
        "brand": kit["name"], "objective": objective, "n": n, "max_rounds": rounds,
        "baseline": _agg(base_scored), "society": _agg(soc_scored),
    }
    result["delta_overall"] = round(result["society"]["avg_overall"] - result["baseline"]["avg_overall"], 1)

    out = Path(__file__).resolve().parent / "results.json"
    out.write_text(json.dumps(result, indent=2))

    b, s = result["baseline"], result["society"]
    print("\n================ RESULTS ================")
    print(f"{'metric':<16}{'baseline':>12}{'society':>12}")
    print(f"{'avg score /100':<16}{b['avg_overall']:>12}{s['avg_overall']:>12}")
    print(f"{'pass rate %':<16}{b['pass_rate']:>12}{s['pass_rate']:>12}")
    for d in DIMS:
        print(f"{d:<16}{b['dims'][d]:>12}{s['dims'][d]:>12}")
    print(f"\nSociety beats baseline by {result['delta_overall']} points. → {out}")


if __name__ == "__main__":
    main()
