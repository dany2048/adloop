"""Generate an 8-bit hero banner of the AdLoop agent society via fal → frontend/hero.png."""
import os, asyncio, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV = ROOT.parent.parent / ".env"
key = [l.split("=", 1)[1].strip().strip('"') for l in open(ENV) if l.startswith("FAL_AI_KEY=")][0]
os.environ["FAL_KEY"] = key
import fal_client

PROMPT = (
    "Wide 8-bit pixel-art banner illustration, SNES 16-bit retro game style. A team of six cute colorful "
    "rounded robot mascots working together in a cozy creative studio to design advertising posters: an "
    "indigo robot with a compass, an amber robot with a pen, a cyan robot with a magnifying glass, a pink "
    "robot with a paintbrush, a red robot judge with a checkmark, and a green robot director with a "
    "clapperboard. Around them: little glowing screens showing ad posters, a mood board, paint palettes, "
    "charts. Warm inviting workshop, subtle teal accent lighting, dark charcoal background, vibrant, "
    "detailed pixel art, cinematic wide composition. No text, no words, no logos."
)


async def main():
    for args in ({"prompt": PROMPT, "aspect_ratio": "16:9"}, {"prompt": PROMPT}):
        try:
            res = await fal_client.subscribe_async("fal-ai/nano-banana-2", arguments=args)
            d = res if isinstance(res, dict) else getattr(res, "__dict__", {})
            url = d["images"][0].get("url") if d.get("images") else (d.get("image", {}) or {}).get("url")
            if url:
                urllib.request.urlretrieve(url, ROOT / "frontend" / "hero.png")
                print("saved hero.png")
                return
        except Exception as e:
            print("attempt failed:", type(e).__name__, str(e)[:150])
    print("FAILED")

asyncio.run(main())
