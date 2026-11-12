# 免费方案：GitHub Actions 抓取 + Cloudflare Pages 展示

整条链路不依赖你的电脑：抓取在 GitHub 免费 runner 上跑，网页由 Cloudflare 免费 CDN 提供。
一次性授权之后，每天自动更新。

## 一、已经跑起来的部分

| 组件 | 位置 | 说明 |
|---|---|---|
| 代码仓库 | https://github.com/Duyanya/bid-radar | 公开仓库，398 个文件 |
| 定时抓取 | `.github/workflows/collect.yml` | 每天 UTC 01:00（北京 09:00），也可手动触发 |
| 数据 | `data/bids.db` + `data/snapshots/` | 每轮抓完自动提交回仓库 |
| 网页 | `site/` | 由 `build_static.py` 从库生成，纯静态，无需后端 |

首次手动触发实测（2026-11-12 14:33）：移动 185 条 / 联通 28 条 / 电信 6 条，境外 IP 没有被瑞数 WAF 拦。
**结论：免费方案可行。**

## 二、还差最后一步：把 `site/` 挂到 Cloudflare Pages

只有这一步需要你操作（免费，约 3 分钟）：

1. 打开 https://dash.cloudflare.com/sign-up ，用邮箱注册（不用买域名，不用绑卡）。
2. 左侧 **Workers & Pages** → **Create** → **Pages** → **Connect to Git**。
3. 授权 GitHub，选中仓库 `Duyanya/bid-radar`，分支 `master`。
4. 构建设置全部留空或按下面填（我们是纯静态，**不需要**构建命令）：

   | 项目 | 值 |
   |---|---|
   | Framework preset | None |
   | Build command | 留空 |
   | Build output directory | `site` |

5. 点 **Save and Deploy**，约 1 分钟出地址，形如 `https://bid-radar.pages.dev`。
6. 把这个地址告诉我，我写进 `data/public_url.txt`（或你在仓库 Settings → Variables 里加 `PUBLIC_URL`），页脚就会显示它。

之后每次 Actions 提交新的 `site/`，Cloudflare 会自动重新发布，不用管。

## 三、两个必须知道的事实

1. **定时不是精确 09:00。** GitHub 免费 runner 的 cron 高峰期会排队，实测延迟 5–30 分钟。要精确 09:00 只能自己买服务器。
2. **cron 是 UTC。** 工作流里写的是 `0 1 * * *`（UTC 01:00 = 北京 09:00），别手动改成 9，否则会北京时间 17:00 跑。

## 四、排错表

| 现象 | 原因 | 处理 |
|---|---|---|
| 页面数据不动 | Actions 失败 | 仓库 **Actions** 标签看红色 run，点开看日志 |
| 某站 0 条 | 该站 WAF 拒了 runner IP | 看日志里 `[CMCC]` / `[CT]` / `[CU]` 段；本地补跑一次即可 |
| 页面 404 | Pages 的 output directory 填错 | 必须填 `site` |
| 页脚地址不对 | `public_url.txt` 没更新 | 仓库 Variables 加 `PUBLIC_URL` = 你的 Pages 地址 |
| `site/` 里少了旧快照 | 记录被重抓但详情没取到 | 已修：upsert 只补空不覆盖，历史字段不会被抹掉 |

## 五、一个已经踩过的坑（已修）

SQLite 开了 WAL，写入先落 `bids.db-wal`。第一次跑完只把 `bids.db` 提交了，主库文件里还是旧数据（42 行），
导致第二轮从 42 行重新累积，中选厂商从 51 条掉到 12 条、快照从 136 份掉到 52 份。

修法：`db.checkpoint()` 把 WAL 并回主库，`collector.py` 收尾调用，工作流提交前再跑一次并断言行数 > 100。
