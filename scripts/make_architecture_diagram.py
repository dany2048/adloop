"""Render AdLoop's architecture diagram to a PNG (self-contained HTML → Playwright screenshot).

Output: architecture.png (repo root, embedded in the README + used as a submission artifact).
"""
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "architecture.png"
W, H = 1600, 1010

HTML = r"""
<!doctype html><html><head><meta charset="utf-8"><style>
  :root{--bg:#0B1220;--panel:#111c2e;--line:#24344d;--teal:#14B8A6;--teal2:#5EEAD4;
        --ink:#E6EEF7;--muted:#8CA3BD;--amber:#F59E0B;--pink:#EC4899;--red:#EF4444;
        --indigo:#6366F1;--cyan:#06B6D4;}
  *{box-sizing:border-box;margin:0;font-family:'Plus Jakarta Sans',-apple-system,Segoe UI,Roboto,sans-serif}
  body{width:1600px;height:1010px;background:radial-gradient(1200px 700px at 50% -10%,#12233b,var(--bg));color:var(--ink);padding:44px 52px}
  .hd{display:flex;align-items:baseline;gap:16px;margin-bottom:6px}
  .logo{font-size:32px;font-weight:800;letter-spacing:-.02em}
  .logo .g{color:var(--teal2)}
  .sub{color:var(--muted);font-size:16px;font-weight:600}
  .tag{margin-left:auto;font-family:'IBM Plex Mono',monospace;font-size:12px;color:var(--teal2);
       border:1px solid var(--teal);border-radius:999px;padding:5px 12px;background:#0e2b2a}
  .canvas{position:relative;margin-top:22px;height:872px}
  .lane{position:absolute;border:1px solid var(--line);border-radius:16px;background:linear-gradient(180deg,#101a2b,#0e1626)}
  .lane .lt{position:absolute;top:-11px;left:18px;font-family:'IBM Plex Mono',monospace;font-size:11px;
            letter-spacing:.14em;text-transform:uppercase;color:var(--muted);background:var(--bg);padding:0 8px}
  .node{position:absolute;border:1px solid var(--line);border-radius:12px;background:var(--panel);
        padding:12px 14px;box-shadow:0 6px 18px rgba(0,0,0,.35)}
  .node .nm{font-weight:800;font-size:15px;display:flex;align-items:center;gap:8px}
  .node .ds{color:var(--muted);font-size:12px;margin-top:3px;line-height:1.35}
  .node .md{font-family:'IBM Plex Mono',monospace;font-size:10.5px;color:var(--teal2);margin-top:7px}
  .dot{width:9px;height:9px;border-radius:50%;display:inline-block}
  .core{border-color:var(--teal);box-shadow:0 0 0 1px var(--teal),0 8px 22px rgba(20,184,166,.25);background:#0e2622}
  .chip{display:inline-block;font-family:'IBM Plex Mono',monospace;font-size:10px;color:var(--ink);
        background:#0c1626;border:1px solid var(--line);border-radius:6px;padding:2px 7px;margin:6px 6px 0 0}
  svg{position:absolute;inset:0;width:100%;height:100%;pointer-events:none;overflow:visible}
  .lbl{font-family:'IBM Plex Mono',monospace;font-size:11px;fill:var(--muted)}
  .foot{position:absolute;bottom:-2px;left:2px;color:var(--muted);font-size:12px}
  .foot b{color:var(--ink)}
</style></head><body>
  <div class="hd"><span class="logo">Ad<span class="g">Loop</span></span>
    <span class="sub">a self-critiquing multi-agent ad-creative society</span>
    <span class="tag">Qwen Cloud · Track 3: Agent Society</span></div>

  <div class="canvas">
    <svg viewBox="0 0 1496 872">
      <defs>
        <marker id="a" markerWidth="9" markerHeight="9" refX="6" refY="3" orient="auto">
          <path d="M0,0 L6,3 L0,6 Z" fill="#3a4d6b"/></marker>
        <marker id="at" markerWidth="9" markerHeight="9" refX="6" refY="3" orient="auto">
          <path d="M0,0 L6,3 L0,6 Z" fill="#14B8A6"/></marker>
      </defs>
      <!-- user/url -> frontend -> server -> director -->
      <path d="M180,150 H300" stroke="#3a4d6b" stroke-width="2" marker-end="url(#a)"/>
      <path d="M470,150 H590" stroke="#3a4d6b" stroke-width="2" marker-end="url(#a)"/>
      <path d="M760,150 V232" stroke="#14B8A6" stroke-width="2.5" marker-end="url(#at)"/>
      <text x="712" y="205" class="lbl">SSE stream</text>
      <!-- director -> workers bus -->
      <path d="M760,360 V420" stroke="#14B8A6" stroke-width="2.5"/>
      <path d="M250,420 H1250" stroke="#24344d" stroke-width="2"/>
      <path d="M250,420 V470" stroke="#3a4d6b" stroke-width="2" marker-end="url(#a)"/>
      <path d="M500,420 V470" stroke="#3a4d6b" stroke-width="2" marker-end="url(#a)"/>
      <path d="M760,420 V470" stroke="#3a4d6b" stroke-width="2" marker-end="url(#a)"/>
      <path d="M1030,420 V470" stroke="#3a4d6b" stroke-width="2" marker-end="url(#a)"/>
      <!-- art director <-> critic revise loop -->
      <path d="M900,530 H980" stroke="#14B8A6" stroke-width="2.5" marker-end="url(#at)"/>
      <path d="M980,585 H900" stroke="#EF4444" stroke-width="2.5" marker-end="url(#a)"/>
      <text x="905" y="522" class="lbl">render</text>
      <text x="905" y="608" class="lbl">required_changes</text>
      <!-- everything -> memory + qwen (down) -->
      <path d="M760,690 V740" stroke="#3a4d6b" stroke-width="2" marker-end="url(#a)"/>
    </svg>

    <!-- lanes -->
    <div class="lane" style="left:0;top:250px;width:1496px;height:410px"><span class="lt">The Society — orchestrated on a shared blackboard</span></div>
    <div class="lane" style="left:0;top:735px;width:1496px;height:118px"><span class="lt">Persistence &amp; models (Qwen Cloud / DashScope)</span></div>

    <!-- top row -->
    <div class="node" style="left:20px;top:118px;width:160px">
      <div class="nm"><span class="dot" style="background:var(--amber)"></span>Product URL</div>
      <div class="ds">a brand link (+ optional notes)</div></div>
    <div class="node" style="left:300px;top:112px;width:170px">
      <div class="nm">Frontend SPA</div>
      <div class="ds">live "watch the team work" timeline + gallery</div></div>
    <div class="node" style="left:590px;top:112px;width:180px">
      <div class="nm">FastAPI server</div>
      <div class="ds">/campaign · /job/stream (SSE) · rate limits</div></div>
    <div class="node core" style="left:1120px;top:96px;width:250px">
      <div class="nm"><span class="dot" style="background:var(--teal)"></span>MCP server <span class="chip" style="margin:0 0 0 6px">stdio</span></div>
      <div class="ds">exposes the agents as tools to any MCP client</div>
      <div class="md">critique_ad · generate_campaign · strategize</div></div>

    <!-- director core -->
    <div class="node core" style="left:625px;top:262px;width:270px">
      <div class="nm"><span class="dot" style="background:var(--teal)"></span>Director  <span style="color:var(--muted);font-weight:600;font-size:11px">(LLM planner + orchestrator)</span></div>
      <div class="ds">plans the campaign, assigns per-variant layout/emphasis, runs the loop, keeps the best, writes lessons</div>
      <div class="md">qwen-max</div></div>

    <!-- worker row -->
    <div class="node" style="left:150px;top:470px;width:210px">
      <div class="nm"><span class="dot" style="background:var(--indigo)"></span>Strategist</div>
      <div class="ds">URL → structured Brand Kit (tone, palette, rules)</div>
      <div class="md">qwen-plus · scrape · web-search</div></div>
    <div class="node" style="left:395px;top:470px;width:210px">
      <div class="nm"><span class="dot" style="background:var(--amber)"></span>Copywriter</div>
      <div class="ds">N framework-diverse ad angles</div>
      <div class="md">qwen-max · memory recall</div></div>
    <div class="node" style="left:655px;top:470px;width:225px">
      <div class="nm"><span class="dot" style="background:var(--pink)"></span>Art Director</div>
      <div class="ds">scene + real-product composite (rembg) + type layer</div>
      <div class="md">wan2.2-t2i · Playwright render</div></div>
    <div class="node" style="left:925px;top:470px;width:210px">
      <div class="nm"><span class="dot" style="background:var(--cyan)"></span>Design Researcher</div>
      <div class="ds">live Pinterest refs → design brief</div>
      <div class="md">qwen-vl-max · Apify</div></div>
    <div class="node core" style="left:980px;top:556px;width:300px">
      <div class="nm"><span class="dot" style="background:var(--red)"></span>Critic  <span style="color:var(--teal2);font-weight:700;font-size:11px">— the moat</span></div>
      <div class="ds">scores every ad 0–100 on 6 dims before spend; sends weak work back to revise</div>
      <div class="md">qwen-vl-max (vision)</div></div>

    <!-- bottom row: persistence + models -->
    <div class="node" style="left:150px;top:752px;width:250px">
      <div class="nm">SQLite memory</div>
      <div class="ds">brand_kits · creatives · runs · embedded lessons</div>
      <div class="md">text-embedding-v3 (semantic recall)</div></div>
    <div class="node" style="left:640px;top:752px;width:240px">
      <div class="nm">Qwen Cloud models</div>
      <div class="ds">qwen-plus · qwen-max · qwen-vl-max</div>
      <div class="md">wan2.2-t2i · text-embedding-v3</div></div>
    <div class="node" style="left:1100px;top:752px;width:260px">
      <div class="nm">Self-improvement loop</div>
      <div class="ds">top creatives + critic lessons feed the next run</div>
      <div class="md">recency × score × cosine</div></div>
  </div>
</body></html>
"""


def main() -> None:
    with sync_playwright() as p:
        b = p.chromium.launch(args=["--no-sandbox"])
        pg = b.new_page(viewport={"width": W, "height": H}, device_scale_factor=2)
        pg.set_content(HTML, wait_until="networkidle")
        pg.screenshot(path=str(OUT), clip={"x": 0, "y": 0, "width": W, "height": H})
        b.close()
    print("wrote", OUT)


if __name__ == "__main__":
    main()
