#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${1:-https://github.com/dennis-d/civic-data-health.git}"
APP_DIR="/opt/civic-data-health"
DATA_DIR="/var/lib/civic-data-health"
WEB_DIR="/var/www/civic-data-health"
UV_PYTHON_DIR="/opt/uv-python"

if ! id civic-health >/dev/null 2>&1; then
  sudo useradd --system --home-dir "$DATA_DIR" --shell /sbin/nologin civic-health
fi

sudo mkdir -p "$DATA_DIR" "$WEB_DIR"
sudo chown -R civic-health:civic-health "$DATA_DIR" "$WEB_DIR"
sudo mkdir -p "$UV_PYTHON_DIR"
sudo chmod 755 "$UV_PYTHON_DIR"

if [ -d "$APP_DIR/.git" ]; then
  sudo git -C "$APP_DIR" fetch --prune
  sudo git -C "$APP_DIR" reset --hard origin/main
else
  if [ -e "$APP_DIR" ]; then
    sudo mv "$APP_DIR" "$APP_DIR.bak.$(date -u +%Y%m%dT%H%M%SZ)"
  fi
  sudo git clone "$REPO_URL" "$APP_DIR"
fi

sudo env UV_PYTHON_INSTALL_DIR="$UV_PYTHON_DIR" /usr/local/bin/uv venv --clear --python 3.12 "$APP_DIR/.venv"
sudo env UV_PYTHON_INSTALL_DIR="$UV_PYTHON_DIR" /usr/local/bin/uv pip install --python "$APP_DIR/.venv/bin/python" "$APP_DIR"
sudo rm -rf "$APP_DIR/build"
sudo cp "$APP_DIR/deploy/civic-health.service" /etc/systemd/system/civic-health.service
sudo cp "$APP_DIR/deploy/civic-health-refresh.service" /etc/systemd/system/civic-health-refresh.service
sudo cp "$APP_DIR/deploy/civic-health-refresh.timer" /etc/systemd/system/civic-health-refresh.timer
sudo systemctl daemon-reload
sudo systemctl enable --now civic-health-refresh.timer
sudo -u civic-health "$APP_DIR/.venv/bin/civic-health" --db "$DATA_DIR/civic_health.sqlite" run --data-dir "$DATA_DIR/data" --out-dir "$WEB_DIR" --force
sudo systemctl enable civic-health.service
sudo systemctl restart civic-health.service
sudo systemctl reload nginx
