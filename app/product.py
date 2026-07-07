"""
Real-product compositing.

E-commerce / product pages expose a product shot (og:image). We remove its background
to a clean transparent cutout and hand it to the Art Director to composite onto the
generated scene — so the ACTUAL product from the URL appears in the ad instead of a
hallucinated look-alike.

Cut-out strategy (best → fallback):
  1. rembg (u2net segmentation) — works on ANY background, including lifestyle shots.
     This is what makes "the exact product from the site" show up reliably.
  2. corner flood-fill (plain/white backgrounds only) — no model needed.
  3. None — the pipeline then uses a fully-generated scene.

Graceful throughout: any failure at a step falls through to the next.
"""
from __future__ import annotations

import io
import os
from typing import Optional

import requests
from PIL import Image, ImageDraw

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124 Safari/537.36"

# Accept a cutout only when a sensible fraction of the image was removed as background.
# Too little removed → nothing was segmented; too much → the subject got eaten.
_MIN_TRANSPARENT = 0.04
_MAX_TRANSPARENT = 0.97
_MAX_SIDE = 1400  # downscale huge hero images before segmentation for speed


# ------------------------------------------------------------------ rembg (lazy, cached)

_REMBG_SESSION = None
_REMBG_TRIED = False


def _rembg_session():
    """Load the rembg session once (model downloads on first use). None if unavailable."""
    global _REMBG_SESSION, _REMBG_TRIED
    if _REMBG_TRIED:
        return _REMBG_SESSION
    _REMBG_TRIED = True
    try:
        from rembg import new_session
        _REMBG_SESSION = new_session(os.getenv("REMBG_MODEL", "u2net"))
    except Exception:
        _REMBG_SESSION = None
    return _REMBG_SESSION


# ------------------------------------------------------------------ helpers

def _download(url: str) -> Optional[Image.Image]:
    try:
        r = requests.get(url, headers={"User-Agent": _UA}, timeout=20)
        r.raise_for_status()
        im = Image.open(io.BytesIO(r.content)).convert("RGBA")
    except Exception:
        return None
    if max(im.size) > _MAX_SIDE:  # shrink oversized hero shots so segmentation is quick
        im.thumbnail((_MAX_SIDE, _MAX_SIDE))
    return im


def _transparent_frac(work: Image.Image) -> float:
    alpha = work.split()[-1]
    w, h = work.size
    clear = sum(1 for p in alpha.getdata() if p < 16)
    return clear / float(max(w * h, 1))


def _validate_and_crop(work: Image.Image) -> Optional[Image.Image]:
    """Reject empty/over-eaten cutouts; tight-crop to the subject's bounding box."""
    frac = _transparent_frac(work)
    if frac < _MIN_TRANSPARENT or frac > _MAX_TRANSPARENT:
        return None
    bbox = work.getbbox()
    return work.crop(bbox) if bbox else work


def _rembg_cut(im: Image.Image) -> Optional[Image.Image]:
    session = _rembg_session()
    if session is None:
        return None
    try:
        from rembg import remove
        out = remove(im, session=session)
        if out.mode != "RGBA":
            out = out.convert("RGBA")
        return _validate_and_crop(out)
    except Exception:
        return None


def _floodfill_cut(im: Image.Image) -> Optional[Image.Image]:
    """Fallback for plain-background product shots when rembg isn't available."""
    w, h = im.size
    if w < 240 or h < 240:
        return None  # too small to be a real product shot (likely a logo/icon)
    work = im.copy()
    for corner in [(1, 1), (w - 2, 1), (1, h - 2), (w - 2, h - 2)]:
        try:
            ImageDraw.floodfill(work, corner, (0, 0, 0, 0), thresh=55)
        except Exception:
            pass
    frac = _transparent_frac(work)
    if frac < 0.08 or frac > 0.92:
        return None  # background wasn't plain (busy scene) or ate the whole image — skip
    bbox = work.getbbox()
    return work.crop(bbox) if bbox else work


# ------------------------------------------------------------------ public

_CACHE: dict[str, Optional[Image.Image]] = {}


def cutout(url: Optional[str]) -> Optional[Image.Image]:
    """A transparent product cutout from the site's product image, or None if it can't be
    isolated. Cached per URL so a 3-angle × N-round campaign fetches each image only once."""
    if not url:
        return None
    if url in _CACHE:
        return _CACHE[url]
    result = _cutout(url)
    _CACHE[url] = result
    return result


def _cutout(url: str) -> Optional[Image.Image]:
    im = _download(url)
    if im is None:
        return None
    w, h = im.size
    if w < 240 or h < 240:
        return None  # too small to be a real product shot
    # 1) proper segmentation (any background) → 2) flood-fill (plain background) → 3) give up
    return _rembg_cut(im) or _floodfill_cut(im)
