"""Generate one 8-bit hero banner. Usage: python gen_hero_variant.py "<prompt>" <out_path>"""
import os, sys, asyncio, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV = ROOT.parent.parent / ".env"
key = [l.split("=", 1)[1].strip().strip('"') for l in open(ENV) if l.startswith("FAL_AI_KEY=")][0]
os.environ["FAL_KEY"] = key
import fal_client

PROMPT = sys.argv[1]
OUT = sys.argv[2] if len(sys.argv) > 2 else "frontend/hero.png"


async def main():
    for args in ({"prompt": PROMPT, "aspect_ratio": "16:9"}, {"prompt": PROMPT}):
        try:
            res = await fal_client.subscribe_async("fal-ai/nano-banana-2", arguments=args)
            d = res if isinstance(res, dict) else getattr(res, "__dict__", {})
            url = d["images"][0].get("url") if d.get("images") else (d.get("image", {}) or {}).get("url")
            if url:
                urllib.request.urlretrieve(url, ROOT / OUT)
                print("SAVED", OUT)
                return
        except Exception as e:
            print("attempt failed:", type(e).__name__, str(e)[:150])
    print("FAILED")

asyncio.run(main())
