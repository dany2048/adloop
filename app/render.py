"""
Renderer: Wanxiang background scene + a designed HTML/CSS type layer → channel-sized PNG.

This is the RELIABLE image path (vs. baking text into the generation). The AI makes the
scene; the headline/subhead/CTA are real text composited on top, so they're always crisp
and on-brand. Uses Jinja2 + Playwright (headless Chromium).
"""
from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from playwright.sync_api import sync_playwright

_TPL_DIR = Path(__file__).resolve().parent.parent / "templates"
_env = Environment(loader=FileSystemLoader(str(_TPL_DIR)), autoescape=select_autoescape(["html", "j2"]))

CHANNELS: dict[str, tuple[int, int]] = {
    "instagram": (1080, 1350),   # 4:5 feed
    "story": (1080, 1920),       # 9:16
    "meta_feed": (1200, 628),    # 1.91:1 link
}


def _data_url(path: str | Path) -> str:
    p = Path(path)
    mime = mimetypes.guess_type(p.name)[0] or "image/png"
    return f"data:{mime};base64,{base64.b64encode(p.read_bytes()).decode()}"


def _hex_rgb(c: str) -> tuple[int, int, int]:
    c = (c or "#000").lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    try:
        return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
    except (ValueError, IndexError):
        return 0, 0, 0


def _lum(c: str) -> float:
    """Perceived luminance 0..1 — used to keep text readable regardless of brand color."""
    r, g, b = _hex_rgb(c)
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255.0


def _font_query(*names: str) -> str:
    """Build a Google Fonts query for the brand's fonts (best-effort; falls back to system)."""
    seen, parts = set(), []
    for n in names:
        n = (n or "").strip()
        if not n or n.lower() in seen:
            continue
        seen.add(n.lower())
        fam = n.split(",")[0].strip().replace(" ", "+")
        parts.append(f"family={fam}:wght@400;500;700;800")
    return "&".join(parts)


def render_ad(
    bg_image_path: str | Path,
    headline: str,
    out_path: str | Path,
    subhead: str = "",
    cta: str = "",
    eyebrow: str = "",
    palette: list[str] | None = None,
    fonts: dict[str, str] | None = None,
    layout: str = "lower",          # lower | top | center
    channel: str = "instagram",
) -> Path:
    w, h = CHANNELS.get(channel, CHANNELS["instagram"])
    palette = palette or ["#111111"]
    fonts = fonts or {}
    accent = next((c for c in palette if c.lower() not in ("#ffffff", "#fff", "#000000", "#000")), palette[0])
    accent_lum = _lum(accent)
    # dark brand accents vanish over a photo — force the eyebrow readable, and keep the CTA label legible on its button
    eyebrow_color = accent if accent_lum > 0.42 else "#F2F2F2"
    cta_text = "#0A0A0A" if accent_lum > 0.55 else "#FFFFFF"
    band_color = "rgba(11,12,14,0.94)"
    display_font = fonts.get("display", "Archivo")
    body_font = fonts.get("body", "Inter")

    # headline size scales to length so long lines still fit
    n = max(len(headline), 1)
    headline_px = int(h * (0.085 if n <= 22 else 0.066 if n <= 36 else 0.052))

    html = _env.get_template("ad_base.html.j2").render(
        w=w, h=h, bg_data_url=_data_url(bg_image_path),
        headline=headline, subhead=subhead, cta=cta, eyebrow=eyebrow,
        accent=accent, text_color="#FFFFFF", cta_text=cta_text, eyebrow_color=eyebrow_color,
        band_color=band_color,
        display_font=display_font, body_font=body_font,
        font_query=_font_query(display_font, body_font),
        layout=layout, headline_px=headline_px,
        pad=int(w * 0.07), gap=int(h * 0.018),
    )

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": w, "height": h}, device_scale_factor=1)
        page.set_content(html, wait_until="networkidle")
        page.screenshot(path=str(out), clip={"x": 0, "y": 0, "width": w, "height": h})
        browser.close()
    return out


if __name__ == "__main__":
    import sys

    bg = sys.argv[1] if len(sys.argv) > 1 else "output/_smoke.png"
    out = render_ad(
        bg, headline="MADE FOR MOVEMENT", out_path="output/_render_test.png",
        eyebrow="Lumora", subhead="The everyday essential, reimagined.",
        cta="Shop the bestseller", palette=["#A8C686", "#6B7F61", "#000000"],
        fonts={"display": "Archivo", "body": "Inter"}, layout="lower", channel="instagram",
    )
    print("rendered ->", out.resolve())
