---
title: AdLoop
emoji: 🎨
colorFrom: indigo
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
license: mit
---

# AdLoop — a multi-agent ad-creative society

**Global AI Hackathon Series with Qwen Cloud · Track 3: Agent Society**

Give it a product URL and a team of AI agents research the brand, write the copy, ground the design in real visual references, design the creatives, and **critique and revise their own work** with a vision model before showing you anything. An open-source, functional take on Omneky, built as a society of specialised agents that collaborate over a shared blackboard and a persistent memory. Every model call runs on **Qwen Cloud (DashScope)**.

**Live demo:** https://danyuav-adloop.hf.space

---

## Why it's an "Agent Society" (Track 3)

Six specialised agents divide the work, hand off over a shared **blackboard**, and one of them (the Critic) sends work *back* for revision — collaboration with a feedback loop, not a single prompt.

```
URL ─▶ Strategist ─▶ Copywriter ─▶ Design Researcher ─▶ Art Director ─┐
        (brand kit)   (N angles)     (visual brief)      (renders)    │
                                                                      ▼
                                              ┌───────────────────────────┐
        gallery ◀── keep best ◀── Director ◀──│  Critic  ⇄  Art Director   │
                                   (arbitrate) │  (score 0–100, revise)    │
                                              └───────────────────────────┘
                                    ▲                                   │
                                    └──────── shared memory ◀───────────┘
                                        (brand kits · creatives · lessons)
```

- **Strategist** — reads the product page → a `BrandKit` (name, palette, fonts, audience, tone, value props, brand rules).
- **Copywriter** — N framework-diverse ad angles, guided by a compiled copywriting playbook.
- **Design Researcher** — pulls real visual references (live Pinterest, with a curated fallback) and distils a design brief.
- **Art Director** — turns the brief into a scene, generates the background (Wanxiang), and composites the type layer with HTML/CSS → a channel-sized PNG.
- **Critic** — a vision model scores each creative on 6 dimensions (thumbstop, hierarchy, legibility, brand fit, hook clarity, CTA visibility) → **0–100 + pass/fail + concrete required changes**. This self-critique loop is the core idea: the society doesn't just produce, it *judges and improves* before output.
- **Director** — orchestrates the pipeline, runs the Art Director ↔ Critic revision loop, keeps the best result, and writes lessons back to memory.

## Qwen Cloud models used

Everything runs on the DashScope international endpoint (`dashscope-intl.aliyuncs.com`). See `app/qwen_client.py`.

| Role | Model |
|---|---|
| Copy / text | `qwen-plus` |
| Planning / strategy | `qwen-max` |
| Vision critique + reference analysis | `qwen-vl-max` |
| Creative backgrounds (text-to-image) | `wan2.2-t2i-flash` (Wanxiang) |
| Memory / semantic recall | `text-embedding-v3` |

## Memory

A SQLite store (`app/memory.py`) holds brand kits, past creatives, and lessons, with embedding-based semantic recall weighted by recency and score — so the society gets better at a brand the more it works on it.

## Benchmark — the society vs a single-agent baseline

Track 3 asks for a measurable gain over a single-agent baseline. `benchmarks/run_society_vs_baseline.py` runs the same brief through the full society and through a naive single-agent control, scored by the Critic.

| | Society | Single-agent baseline |
|---|---|---|
| Avg score /100 | **64.4** | 56.7 |
| Brand fit /10 | **8.3** | 4.7 |

*(N=3, 1 revision round — a larger, multi-round re-run is in progress. Numbers regenerate via the benchmark script.)*

## Run it locally

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
cp .env.example .env    # paste your DASHSCOPE_API_KEY
python -m uvicorn app.server:app --host 127.0.0.1 --port 8011
# open http://127.0.0.1:8011
```

## Deploy

- **Hugging Face Space** — this repo is a Docker Space; the root `Dockerfile` runs it. Set `DASHSCOPE_API_KEY` as a Space secret.
- **Any Ubuntu VM (ECS / VPS)** — `bash deploy/setup.sh` (see `deploy/README.md`).

## Compliance

Clean-room, original code. No third-party logos, screenshots, trademarks, or copyrighted media in the repo, UI, or demo. Demonstrations use fictional sample brands. MIT licensed (`LICENSE`).
