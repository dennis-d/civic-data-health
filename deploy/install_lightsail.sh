#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${1:-https://github.com/dennis-d/civic-data-health.git}"
APP_DIR="/opt/civic-data-health"
DATA_DIR="/var/lib/civic-data-health"
WEB_DIR="/var/www/civic-data-health"

if ! id civic-health >/dev/null 2>&1; then
  sudo useradd --system --home-dir "$DATA_DIR" --shell /sbin/nologin civic-health
fi

sudo mkdir -p "$DATA_DIR" "$WEB_DIR"
sudo chown -R civic-health:civic-health "$DATA_DIR" "$WEB_DIR"

if [ -d "$APP_DIR/.git" ]; then
  sudo git -C "$APP_DIR" fetch --prune
  sudo git -C "$APP_DIR" reset --hard origin/main
else
  if [ -e "$APP_DIR" ]; then
    sudo mv "$APP_DIR" "$APP_DIR.bak.$(date -u +%Y%m%dT%H%M%SZ)"
  fi
  sudo git clone "$REPO_URL" "$APP_DIR"
fi

sudo python3 -m venv "$APP_DIR/.venv"
sudo "$APP_DIR/.venv/bin/pip" install --upgrade pip
sudo "$APP_DIR/.venv/bin/pip" install "$APP_DIR"
sudo cp "$APP_DIR/deploy/civic-health.service" /etc/systemd/system/civic-health.service
sudo cp "$APP_DIR/deploy/civic-health-refresh.service" /etc/systemd/system/civic-health-refresh.service
sudo cp "$APP_DIR/deploy/civic-health-refresh.timer" /etc/systemd/system/civic-health-refresh.timer
sudo systemctl daemon-reload
sudo systemctl enable --now civic-health-refresh.timer
sudo systemctl restart civic-health-refresh.service
sudo systemctl enable civic-health.service
sudo systemctl restart civic-health.service
sudo systemctl reload nginx
