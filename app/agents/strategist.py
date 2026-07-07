"""
Brand Strategist agent.

Reads a product URL (+ optional pasted docs), extracts the brand DNA with Qwen,
and persists it to memory so the rest of the society — and future sessions —
never have to re-derive it. Also seeds a few brand-rule memories the Critic and
Art Director will lean on.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from .. import config, memory, prompts, qwen_client

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
_MAX_TEXT = 6000

_SYS = """You are a senior brand strategist at an ad agency. Given a brand's website text, \
extract a tight, usable Brand Kit. Infer sensibly where the page is thin, but never invent \
facts about the product. Respond with ONE JSON object, no prose."""

_SCHEMA_HINT = """Return JSON with exactly these keys:
{
  "name": str,                      // brand/product/company name
  "offering_type": str,             // EXACTLY one of: "product" (a physical product you can photograph), "service" (agency, consulting, coaching, done-for-you), "app" (software / SaaS / mobile or web app)
  "tagline": str,                   // short positioning line (yours if none on page)
  "product_summary": str,           // 1-2 sentences: what it is, who it's for (works for a product, service, OR app)
  "audience": str,                  // primary target customer
  "tone": str,                      // brand voice in 3-5 adjectives
  "value_props": [str, ...],        // 3-5 concrete benefits/differentiators (for a service/app: outcomes, capabilities, results — not physical specs)
  "palette": [str, ...],            // 3-5 hex colors that fit the brand (infer if not stated)
  "fonts": {"display": str, "body": str},  // suggested web-safe/Google font names
  "price_hint": str,                // price point or tier if discernible, else ""
  "visual_direction": str,          // ONE line: what the AD IMAGE should actually show for THIS offering — e.g. "the product in warm natural light" (product), "a confident founder celebrating a result / an aspirational lifestyle outcome" (service), "a sleek phone showing a clean app UI on a minimal desk" (app)
  "rules": [str, ...]               // 3-5 brand do/don't rules for ad creative
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
    # Product image: og:image → twitter:image → first real content <img> (for the real-product composite).
    product_image = ""
    for prop, attr in (("og:image", "property"), ("twitter:image", "name"), ("twitter:image", "property")):
        m = soup.find("meta", attrs={attr: prop})
        if m and m.get("content"):
            product_image = urljoin(url, m["content"].strip())
            break
    if not product_image:
        for im in soup.find_all("img"):
            src = im.get("src") or im.get("data-src") or im.get("data-lazy-src") or ""
            if src.startswith(("http", "//", "/")) and not any(x in src.lower() for x in ("logo", "icon", "sprite", "avatar", "favicon", ".svg")):
                product_image = urljoin(url, src.strip())
                break

    text = " ".join(soup.get_text(separator=" ").split())[:_MAX_TEXT]
    return {"url": url, "title": title, "meta_desc": meta_desc, "og_image": product_image, "text": text}


def extract_brand_kit(url: str, docs: str | None = None, page: dict[str, Any] | None = None) -> dict[str, Any]:
    page = page or fetch_url(url)
    user = (
        f"WEBSITE: {url}\nTITLE: {page['title']}\nDESCRIPTION: {page['meta_desc']}\n\n"
        f"PAGE TEXT:\n{page['text']}\n"
    )
    if docs:
        user += f"\nADDITIONAL BRAND DOCS:\n{docs[:_MAX_TEXT]}\n"
    user += f"\n{_SCHEMA_HINT}"

    kit = qwen_client.chat_json(
        [{"role": "system", "content": prompts.get("strategist", _SYS)}, {"role": "user", "content": user}],
        model=config.TEXT_MODEL,
    )
    kit["url"] = url
    if page["og_image"]:
        kit["logo_url"] = page["og_image"]
    return kit


def _web_research(url: str, title: str, snippet: str = "", bb=None) -> str:
    """Search tool: use Qwen's built-in web search to gather real, concrete context about the brand."""
    try:
        if bb:
            bb.post("strategist", "info", "Searching the web for real context on the brand…")
        return qwen_client.chat(
            [{"role": "user", "content": (
                f"Use web search to research the brand/company at {url} (page title: {title!r}).\n"
                f"Homepage snippet for grounding: {snippet[:600]}\n\n"
                "Write a tight, factual intelligence brief (5-7 sentences, concrete — not generic marketing fluff). Cover:\n"
                "1) exactly what they sell — the core product, service, or app, and its category;\n"
                "2) who the ideal customer is (be specific);\n"
                "3) their strongest real differentiators or proof — scale, results, notable clients, reputation, awards;\n"
                "4) price positioning / tier if discoverable;\n"
                "5) the core emotional promise or transformation they sell.\n"
                "Only state facts you can verify from the site or search results. If something is unknown, say so briefly "
                "rather than inventing it."
            )}],
            model=config.PLAN_MODEL, temperature=0.3, enable_search=True,
        )
    except Exception:
        return ""  # search unavailable → proceed with page scrape only


def run(url: str, docs: str | None = None, persist: bool = True, bb=None,
        brand_kit_id: str | None = None) -> dict[str, Any]:
    """Extract + persist the brand kit and seed brand-rule memories. Returns the kit.

    When `brand_kit_id` is given, the refreshed kit REPLACES that saved brand in place
    (same id) so a re-strategize keeps the brand's creatives, runs, and memory linked.
    """
    if bb:
        bb.post("strategist", "info", f"Reading {url} and researching the brand…")
    page = fetch_url(url)
    research = _web_research(url, page.get("title", ""), snippet=(page.get("meta_desc") or page.get("text", "")), bb=bb)
    combined = (docs or "")
    if research:
        combined += "\n\nWEB RESEARCH (from search):\n" + research
    kit = extract_brand_kit(url, combined or None, page=page)
    if brand_kit_id:
        kit["id"] = brand_kit_id  # update the existing brand row instead of creating a duplicate

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

    target = sys.argv[1] if len(sys.argv) > 1 else "https://example.com"
    out = run(target, persist=True)
    print(json.dumps(out, indent=2, ensure_ascii=False))
