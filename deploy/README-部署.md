# 投标雷达 —— 搬到云服务器（不依赖本机）

目标：抓取（每天 09:00）和网页 24 小时都在服务器上跑，本机可以关机、断网、重装。

## 一、买什么

| 项目 | 建议 | 说明 |
|---|---|---|
| 机器 | 国内轻量云服务器 2 核 2G / 40G 盘 | 阿里云/腾讯云/华为云轻量都行，新用户常年 ¥100–300/年 |
| 系统 | Ubuntu 22.04 或 24.04 | 一键安装脚本按这个写；Debian 12 也可 |
| 地域 | **必须国内**（华东/华北/华南） | 移动/电信/联通的招标站对境外和机房 IP 都有 WAF，境外节点大概率被拦 |
| 带宽 | 3–5 Mbps 够 | 只有网页和 JSON，图片都没有 |

磁盘占用参考：代码 + 依赖约 600 MB（Playwright Chromium 占大头），数据 10 MB / 年起。

## 二、装

1. 把整个项目目录打包上传（或 `git clone`），`bin/`、`__pycache__/`、`tmp/` 不用传。
2. 服务器上执行：

```bash
sudo bash deploy/install.sh
```

脚本做 6 件事：装系统库 → 建 `bidradar` 账号 → 代码同步到 `/opt/bid-radar` → venv + `playwright install chromium` → 装 systemd 服务并启动 → `curl /api/stats` 自检。

3. 验证：

```bash
systemctl status bidradar-web         # active (running)
systemctl list-timers bidradar-collect.timer   # 下一次 09:00
curl -s http://127.0.0.1:8848/api/stats
```

## 三、把老数据带过去

本机现有的 136 条公告 + 快照直接复制，不用重抓：

```bash
# 本机（Windows，bash）：
scp data/bids.db root@服务器IP:/opt/bid-radar/data/
scp -r data/snapshots root@服务器IP:/opt/bid-radar/data/
ssh root@服务器IP "chown -R bidradar:bidradar /opt/bid-radar/data && systemctl restart bidradar-web"
```

## 四、对外地址（三种，任选）

| 方案 | 地址 | 成本 | 说明 |
|---|---|---|---|
| A. 自己的域名 + Caddy | `https://bid.example.com` | 域名 ¥30–60/年 | 最稳，换机器地址不变。Caddyfile 两行：`bid.example.com { reverse_proxy 127.0.0.1:8848 }` |
| B. 服务器上装 Tailscale + Funnel | `https://xxx.tailxxxx.ts.net` | 免费 | 和现在一样，但**机器换了 ts.net 名字会变**，要重新发一次链接 |
| C. 公网 IP + 端口 | `http://IP:8848` | 免费 | 明文 HTTP、IP 会变、暴露端口，不推荐 |

## 五、必须实测的风险（别当成已解决）

1. **机房 IP 能不能过 WAF**：现在本机是家用/办公宽带，移动 b2b 站的瑞数 WAF 过了；云服务器是 IDC 段，可能被降到验证码或直接 403。上线第一件事就是手动跑一次 `collector.py cmcc 2 0` 看真实条数，不行就换机房/加住宅代理。
2. **电信限流**：逻辑没变（约 8 次请求即封、间隔 5–8 秒），脚本里已 sleep，但仍要控制频率。
3. **Playwright 内存**：Chromium 单实例约 300 MB，2G 内存够，别同时开多个抓取进程。
4. **时区**：`timedatectl set-timezone Asia/Shanghai`，否则 09:00 会按 UTC 触发。

## 六、日常运维

```bash
systemctl restart bidradar-web          # 重启网页
sudo -u bidradar /opt/bid-radar/.venv/bin/python /opt/bid-radar/collector.py all 15 20   # 手动抓
journalctl -u bidradar-collect -n 50    # 看抓取日志
cp /opt/bid-radar/data/bids.db ~/bids-$(date +%F).db   # 手动备份
```

建议再加一条 `crontab`：每天 10:00 把 `bids.db` 复制到 `~/backup/`，保留 14 天。
