"""
Brand Strategist agent.

Reads a product URL (+ optional pasted docs), extracts the brand DNA with Qwen,
and persists it to memory so the rest of the society — and future sessions —
never have to re-derive it. Also seeds a few brand-rule memories the Critic and
Art Director will lean on.
"""
from __future__ import annotations

from typing import Any

import requests
from bs4 import BeautifulSoup

from .. import config, memory, qwen_client

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
_MAX_TEXT = 6000

_SYS = """You are a senior brand strategist at an ad agency. Given a brand's website text, \
extract a tight, usable Brand Kit. Infer sensibly where the page is thin, but never invent \
facts about the product. Respond with ONE JSON object, no prose."""

_SCHEMA_HINT = """Return JSON with exactly these keys:
{
  "name": str,                      // brand/product name
  "tagline": str,                   // short positioning line (yours if none on page)
  "product_summary": str,           // 1-2 sentences: what it is, who it's for
  "audience": str,                  // primary target customer
  "tone": str,                      // brand voice in 3-5 adjectives
  "value_props": [str, ...],        // 3-5 concrete benefits/differentiators
  "palette": [str, ...],            // 3-5 hex colors that fit the brand (infer if not stated)
  "fonts": {"display": str, "body": str},  // suggested web-safe/Google font names
  "price_hint": str,                // price point or tier if discernible, else ""
  "rules": [str, ...]               // 3-5 brand do/don't rules for ad creative (e.g. "always show product in use")
}"""


def fetch_url(url: str, timeout: int = 20) -> dict[str, Any]:
    """Pull a page and reduce it to the signal an LLM needs."""
    r = requests.get(url, headers={"User-Agent": _UA}, timeout=timeout)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    title = (soup.title.string or "").strip() if soup.title else ""
    meta_desc = ""
    if (m := soup.find("meta", attrs={"name": "description"})) and m.get("content"):
        meta_desc = m["content"].strip()
    og_image = ""
    if (og := soup.find("meta", attrs={"property": "og:image"})) and og.get("content"):
        og_image = og["content"].strip()

    text = " ".join(soup.get_text(separator=" ").split())[:_MAX_TEXT]
    return {"url": url, "title": title, "meta_desc": meta_desc, "og_image": og_image, "text": text}


def extract_brand_kit(url: str, docs: str | None = None) -> dict[str, Any]:
    page = fetch_url(url)
    user = (
        f"WEBSITE: {url}\nTITLE: {page['title']}\nDESCRIPTION: {page['meta_desc']}\n\n"
        f"PAGE TEXT:\n{page['text']}\n"
    )
    if docs:
        user += f"\nADDITIONAL BRAND DOCS:\n{docs[:_MAX_TEXT]}\n"
    user += f"\n{_SCHEMA_HINT}"

    kit = qwen_client.chat_json(
        [{"role": "system", "content": _SYS}, {"role": "user", "content": user}],
        model=config.TEXT_MODEL,
    )
    kit["url"] = url
    if page["og_image"]:
        kit["logo_url"] = page["og_image"]
    return kit


def run(url: str, docs: str | None = None, persist: bool = True, bb=None) -> dict[str, Any]:
    """Extract + persist the brand kit and seed brand-rule memories. Returns the kit."""
    if bb:
        bb.post("strategist", "info", f"Reading {url} and extracting brand DNA…")
    kit = extract_brand_kit(url, docs)

    if persist:
        memory.init_db()
        kit_id = memory.save_brand_kit(kit)
        kit["id"] = kit_id
        for rule in kit.get("rules", [])[:5]:
            memory.add_memory(kit_id, "rule", rule, score=0.5)
        if bb:
            bb.job.brand_kit_id = kit_id

    if bb:
        bb.post(
            "strategist", "draft",
            f"Brand Kit ready for “{kit.get('name','?')}” — tone: {kit.get('tone','')}.",
            brand_kit=kit,
        )
    return kit


if __name__ == "__main__":
    import json
    import sys

    target = sys.argv[1] if len(sys.argv) > 1 else "https://www.allbirds.com"
    out = run(target, persist=True)
    print(json.dumps(out, indent=2, ensure_ascii=False))
