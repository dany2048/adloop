"""Generate 8-bit pixel-art agent mascots via fal nano-banana → frontend/sprites/{key}.png."""
import os, asyncio, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV = ROOT.parent.parent / ".env"   # personal-workspace/.env
key = [l.split("=", 1)[1].strip().strip('"') for l in open(ENV) if l.startswith("FAL_AI_KEY=")][0]
os.environ["FAL_KEY"] = key
import fal_client

OUT = ROOT / "frontend" / "sprites"
OUT.mkdir(parents=True, exist_ok=True)

STYLE = ("Minimal flat 8-bit pixel-art app icon. ONE simple cute rounded robot head, big friendly glowing "
         "eyes, VERY few details, bold clean chunky pixels, high contrast, centered, front-facing. The whole "
         "robot is predominantly a SOLID {color} color so it reads instantly by color alone at a squint. "
         "Exactly one small {symbol} as its only accessory. The ENTIRE square image is filled edge-to-edge with "
         "the SAME solid flat dark charcoal #12141A background — no white anywhere, no border, no separate "
         "circle, a uniform dark tile. Simple, iconic, minimal — no clutter, no props, no scene, one character "
         "only, no text, no logo. ")

# each = predominant color + ONE tiny role symbol (squint test: tell them apart by color first)
AGENTS = {
    "strategist":       {"color": "indigo blue", "symbol": "compass needle on its forehead"},
    "copywriter":       {"color": "amber gold",  "symbol": "pen-nib antenna"},
    "design_researcher":{"color": "cyan",        "symbol": "magnifying-glass eye"},
    "art_director":     {"color": "hot pink",    "symbol": "paintbrush antenna"},
    "critic":           {"color": "red",         "symbol": "tiny star badge"},
    "director":         {"color": "teal green",  "symbol": "play-triangle on its chest"},
}


async def one(k, spec):
    prompt = STYLE.format(color=spec["color"], symbol=spec["symbol"])
    for args in ({"prompt": prompt, "aspect_ratio": "1:1"}, {"prompt": prompt}):
        try:
            res = await fal_client.subscribe_async("fal-ai/nano-banana-2", arguments=args)
            d = res if isinstance(res, dict) else getattr(res, "__dict__", {})
            url = None
            if d.get("images"):
                url = d["images"][0].get("url") if isinstance(d["images"][0], dict) else None
            if not url and d.get("image"):
                url = d["image"].get("url") if isinstance(d["image"], dict) else d["image"]
            if url:
                urllib.request.urlretrieve(url, OUT / f"{k}.png")
                print("saved", k)
                return True
        except Exception as e:
            print(k, "attempt failed:", type(e).__name__, str(e)[:160])
    print(k, "FAILED")
    return False


async def main():
    for k, subj in AGENTS.items():
        await one(k, subj)

asyncio.run(main())
print("done ->", OUT)
