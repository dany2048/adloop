# Deploying AdLoop

Goal: a **public URL that stays live and free through Jul 31** (the hackathon judging window), running the FastAPI app, meaningfully calling Qwen via DashScope.

Two supported paths — pick based on which box you can actually create:

- **Path A — Alibaba Cloud ECS** (strictest reading of the "proof of Alibaba Cloud deployment" requirement). Use if your account clears identity verification.
- **Path B — any Ubuntu VPS** (DigitalOcean / Vultr / Hetzner) as the reliable fallback if Alibaba's RiskControl/KYC blocks ECS creation. The app still uses Qwen via DashScope, which is the one universally-agreed requirement.

Both paths run the **same three files** in this folder: `setup.sh`, `adloop.service`, and (for container hosts) `Dockerfile`.

---

## Path A / B — Ubuntu box (ECS or VPS), identical steps

Provision: **Ubuntu 22.04, 2 vCPU / ≥2 GB RAM** (4 GB is comfortable; 2 GB works because `setup.sh` adds swap), **Singapore region** (keeps egress to Google Fonts + Pinterest fast), open inbound **ports 22 and 80**.

1. Get the code onto the box, into `/opt/adloop`:
   - **If the repo is public:** nothing to copy — `setup.sh` will clone it (pass `REPO_URL`).
   - **Otherwise, from your Mac:**
     ```bash
     rsync -av --exclude '.venv' --exclude 'output' --exclude 'data/adloop.db' \
       "projects/ad-variant-factory/" root@<PUBLIC_IP>:/opt/adloop/
     ```
2. SSH in and run the bootstrap:
   ```bash
   ssh root@<PUBLIC_IP>
   # Option A (public repo):
   REPO_URL=https://github.com/dany2048/adloop.git bash /tmp/setup.sh
   # Option B (code already rsync'd):
   bash /opt/adloop/deploy/setup.sh
   ```
   It installs deps, adds swap, `playwright install --with-deps chromium`, creates `.env`, and installs+starts the systemd service.
3. Paste your keys:
   ```bash
   nano /opt/adloop/.env      # DASHSCOPE_API_KEY=sk-...   (+ APIFY_API_KEY if using live Pinterest)
   systemctl restart adloop
   ```
4. Verify:
   ```bash
   curl -s localhost/healthz            # -> {"ok":true,"service":"adloop"}
   ```
   Then open `http://<PUBLIC_IP>/` in a browser.

Logs: `journalctl -u adloop -f`

---

## Container host (Fly.io / Railway / Alibaba Function Compute custom container)

`deploy/Dockerfile` uses the official Playwright image (Chromium + system libs baked in), so there's no `--with-deps` step to fail.

```bash
# Fly.io
fly launch --dockerfile deploy/Dockerfile --now
fly secrets set DASHSCOPE_API_KEY=sk-... APIFY_API_KEY=...
# Railway: point the service at deploy/Dockerfile and set the same env vars in the dashboard.
```
The app reads `$PORT` (container hosts inject it).

---

## ⚠️ Harden BEFORE exposing publicly (open wallet / OOM risks)

The MVP server has no auth or rate limiting and can fan out ~16 image gens + a $1 Apify charge per request. On a public URL that's a drainable key. Do these **before** sharing the URL (tracked as punch-list item 3 — code changes, not infra):

- [ ] Clamp `GenerateReq` in `app/server.py` (e.g. `n<=3`, `max_rounds<=2`).
- [ ] Add a simple per-IP/day request counter.
- [ ] Set `ADLOOP_DISABLE_APIFY=1` on the server (curated design-reference fallback already works) so no per-run Apify charge.
- [ ] Serialize renders (one Chromium at a time) so 2-3 concurrent judges don't OOM a small box.
- [ ] Add a `GET /creatives` endpoint + load past creatives on boot, and **seed a fictional demo brand** so a judge landing cold sees output immediately (not a blank gallery).

---

## Deploy-proof artifacts for the submission

The Devpost "additional info" form asks for (a) a code file showing Alibaba Cloud API usage and (b) proof the project runs on Alibaba Cloud:

- **(a)** → link `app/qwen_client.py` (calls DashScope / Qwen Cloud directly).
- **(b)** → record a short clip: browser hitting `http://<PUBLIC_IP>/healthz` and a full generate run, **plus** the Alibaba console showing the ECS instance. If you're on Path B (non-Alibaba host because ECS was blocked), record the running app + a Qwen/DashScope call in `journalctl -u adloop -f`, and keep your support-ticket screenshot showing Alibaba's RiskControl block as the paper trail.
