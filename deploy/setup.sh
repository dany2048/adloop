#!/usr/bin/env bash
#
# AdLoop one-shot deploy bootstrap for a fresh Ubuntu 22.04 box.
# Works identically on Alibaba Cloud ECS or any generic VPS (DigitalOcean / Vultr / Hetzner).
#
# Usage (as root on the box):
#   # Option A — code is already on the box (scp/rsync'd into /opt/adloop):
#   bash /opt/adloop/deploy/setup.sh
#
#   # Option B — pull from a public git repo:
#   REPO_URL=https://github.com/dany2048/adloop.git bash setup.sh
#
# After it finishes: paste your keys into /opt/adloop/.env, then:
#   systemctl restart adloop && curl -s localhost/healthz
#
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/adloop}"
REPO_URL="${REPO_URL:-}"
PY="python3"

echo "==> [1/7] apt deps"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y python3-venv python3-pip git curl ca-certificates

echo "==> [2/7] swap (Chromium needs headroom on <=2GB boxes)"
if ! swapon --show | grep -q '/swapfile'; then
  fallocate -l 2G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  grep -q '/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
  echo "    added 2G swap"
else
  echo "    swap already present"
fi

echo "==> [3/7] fetch code into ${APP_DIR}"
if [ -n "${REPO_URL}" ]; then
  if [ -d "${APP_DIR}/.git" ]; then
    git -C "${APP_DIR}" pull --ff-only
  else
    git clone "${REPO_URL}" "${APP_DIR}"
  fi
else
  if [ ! -d "${APP_DIR}/app" ]; then
    echo "!! No REPO_URL set and ${APP_DIR}/app not found."
    echo "   scp/rsync the project to ${APP_DIR} first, or set REPO_URL." >&2
    exit 1
  fi
  echo "    using code already present in ${APP_DIR}"
fi
cd "${APP_DIR}"

echo "==> [4/7] python venv + requirements"
${PY} -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo "==> [5/7] playwright chromium + system deps"
# --with-deps is the part that trips people up on a bare server; it pulls the shared libs Chromium needs.
python -m playwright install --with-deps chromium

echo "==> [6/7] .env"
if [ ! -f .env ]; then
  cp .env.example .env
  echo "    created .env from .env.example — EDIT IT and paste DASHSCOPE_API_KEY (+ APIFY_API_KEY if used)"
fi

echo "==> [6.5/7] open port 80 at OS level (Oracle Cloud ships iptables rules that block it)"
if command -v iptables >/dev/null 2>&1; then
  if ! iptables -C INPUT -p tcp --dport 80 -j ACCEPT 2>/dev/null; then
    iptables -I INPUT -p tcp --dport 80 -j ACCEPT
    # persist across reboots if the tool is available (Oracle Ubuntu images have it)
    if command -v netfilter-persistent >/dev/null 2>&1; then
      netfilter-persistent save || true
    fi
    echo "    inserted iptables ACCEPT for tcp/80"
  else
    echo "    tcp/80 already allowed"
  fi
fi

echo "==> [7/7] systemd service"
cp deploy/adloop.service /etc/systemd/system/adloop.service
systemctl daemon-reload
systemctl enable adloop
systemctl restart adloop
sleep 2
systemctl --no-pager status adloop || true

echo
echo "==> done. Next:"
echo "    1) nano ${APP_DIR}/.env   (paste your keys)"
echo "    2) systemctl restart adloop"
echo "    3) curl -s localhost/healthz   (expect {\"ok\":true,...})"
echo "    4) open http://<PUBLIC_IP>/ in a browser"
