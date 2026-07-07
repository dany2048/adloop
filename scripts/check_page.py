"""Render localhost:8011 at a given width; report em-dash-in-text, horizontal overflow, JS errors, and screenshot.
Usage: python check_page.py <width> <out_png>"""
import sys
from playwright.sync_api import sync_playwright

W = int(sys.argv[1])
OUT = sys.argv[2] if len(sys.argv) > 2 else f"output/_check_{W}.png"

with sync_playwright() as p:
    b = p.chromium.launch(args=["--no-sandbox"])
    pg = b.new_page(viewport={"width": W, "height": 1000}, device_scale_factor=1)
    errs = []
    pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
    pg.goto("http://127.0.0.1:8011", wait_until="networkidle")
    pg.wait_for_timeout(1600)
    emdash = pg.evaluate("document.body.innerText.includes('\\u2014')")
    overflow = pg.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
    # how much of the viewport width the main content actually uses (empty-right detector)
    fill = pg.evaluate(
        "(() => { const c=document.querySelector('.content'); if(!c) return 0;"
        "const r=c.getBoundingClientRect(); return Math.round(100*(r.width)/window.innerWidth); })()"
    )
    pg.screenshot(path=OUT, full_page=True)
    b.close()

print(f"width={W} | em_dash_in_text={emdash} | horizontal_overflow_px={overflow} | content_fills_pct={fill} | js_errors={errs[:6]}")
print(f"screenshot={OUT}")
