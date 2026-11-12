#!/usr/bin/env bash
# 投标雷达 —— 云服务器一键安装（Ubuntu 22.04 / 24.04，Debian 12 同样可用）
# 用法：sudo bash deploy/install.sh
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/bid-radar}"
SVC_USER="${SVC_USER:-bidradar}"

echo "==> 1/6 安装系统依赖"
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip curl ca-certificates \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 libxkbcommon0 \
    libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 \
    libcairo2 libasound2 tzdata >/dev/null

echo "==> 2/6 建服务账号"
id -u "$SVC_USER" >/dev/null 2>&1 || useradd -r -m -d /var/lib/bid-radar -s /bin/bash "$SVC_USER"

echo "==> 3/6 部署代码到 $APP_DIR"
mkdir -p "$APP_DIR"
# 假定代码已解压到当前目录（仓库根），同步过去但保留服务器上的 data/
if [ -d "$APP_DIR/data" ]; then
  rsync -a --exclude data --exclude bin --exclude __pycache__ --exclude tmp ./ "$APP_DIR/"
else
  rsync -a --exclude bin --exclude __pycache__ --exclude tmp ./ "$APP_DIR/"
fi
mkdir -p "$APP_DIR/data/snapshots"

echo "==> 4/6 建虚拟环境并装依赖"
cd "$APP_DIR"
python3 -m venv .venv
./.venv/bin/pip install -q --upgrade pip
./.venv/bin/pip install -q -r requirements.txt
./.venv/bin/playwright install --with-deps chromium

echo "==> 5/6 装 systemd 服务"
install -m 644 deploy/bidradar-web.service   /etc/systemd/system/
install -m 644 deploy/bidradar-collect.service /etc/systemd/system/
install -m 644 deploy/bidradar-collect.timer /etc/systemd/system/
chown -R "$SVC_USER":"$SVC_USER" "$APP_DIR" /var/lib/bid-radar
systemctl daemon-reload
systemctl enable --now bidradar-web.service
systemctl enable --now bidradar-collect.timer

echo "==> 6/6 自检"
sleep 1
curl -fsS http://127.0.0.1:8848/api/stats | head -c 200 || { echo "!! web 未起来，看 journalctl -u bidradar-web -n 50"; exit 1; }
echo
echo "完成。网页：http://127.0.0.1:8848（仅本机），对外用 Tailscale Funnel 或 Caddy 反代。"
echo "定时：systemctl list-timers bidradar-collect.timer"
echo "手动抓一次：sudo -u $SVC_USER $APP_DIR/.venv/bin/python $APP_DIR/collector.py all 15 20"
