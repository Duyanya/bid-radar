"""独立补齐结果公告的中选厂商；保留历史状态、正文和已有快照。"""
import argparse
import json
import re
import time
from pathlib import Path
import collector
import db


def pending_rows():
    with db.conn() as c:
        rows = [dict(r) for r in c.execute(
            "SELECT * FROM bids WHERE winner IS NULL OR trim(winner)='' "
            "ORDER BY publish_date DESC, first_seen DESC")]
    return [r for r in rows if re.search(r"结果|候选|成交", r.get("title") or "")]


def apply_text(row, text):
    winner = collector.parse_winner(text)
    if not winner:
        return False
    sets, args = ["winner=?"], [winner]
    if not (row.get("content") or "").strip():
        sets.append("content=?")
        args.append(text[:8000])
    # 不重写任何已有快照（包括已下架公告）。
    snap = row.get("snapshot_path")
    default_snap = db.SNAP / (row["id"] + ".html")
    if not snap and not default_snap.exists():
        snap = db.save_snapshot(row["id"], text)
        if snap:
            sets.append("snapshot_path=?")
            args.append(snap)
    elif not snap and default_snap.exists():
        sets.append("snapshot_path=?")
        args.append(str(default_snap.relative_to(db.BASE)).replace("\\", "/"))
    args.append(row["id"])
    with db.conn() as c:
        changed = c.execute("UPDATE bids SET " + ",".join(sets) +
            " WHERE id=? AND (winner IS NULL OR trim(winner)='')", args).rowcount
    if changed:
        print(f"补齐 {row['id']}: {winner}", flush=True)
    return bool(changed)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=60)
    parser.add_argument("--cache-dir", type=Path)
    args = parser.parse_args()
    rows = pending_rows()
    waiting, updated = [], 0
    for row in rows:
        if apply_text(row, row.get("content") or ""):
            updated += 1
        else:
            waiting.append(row)
    if args.cache_dir:
        for row in waiting:
            cached = args.cache_dir / (row["id"] + ".json")
            if cached.exists():
                text = json.loads(cached.read_text(encoding="utf-8")).get("text")
                if text:
                    updated += apply_text(row, text)
    else:
        # 独立于日常详情的数量限额，同时补抓此前遗漏的历史结果公告。
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            for prefix in ("cmcc_", "cu_"):
                selected = [r for r in waiting if r["id"].startswith(prefix) and r.get("uuid")][:args.limit]
                if not selected:
                    continue
                browser = None
                try:
                    if prefix == "cu_":
                        browser, ctx, page = collector.cuisine(p)
                        page.goto(collector.CU_HOME, wait_until="domcontentloaded", timeout=60000)
                    else:
                        browser, page = collector.launch(p)
                        page.goto("https://b2b.10086.cn/b2b/main/preparePurchaseNoticeList.html", wait_until="domcontentloaded", timeout=60000)
                    page.wait_for_timeout(3000)
                    for row in selected:
                        if prefix == "cu_":
                            text, meta, err = collector.fetch_cu_detail(page, row["uuid"])
                        else:
                            text, meta, err = collector.fetch_cmcc_detail(page, {
                                "id": row["id"][5:], "uuid": row["uuid"], "publishType": "SELECTION_RESULTS"})
                        if text:
                            updated += apply_text(row, text)
                        if err:
                            print(f"待重试 {row['id']}: {err}", flush=True)
                        time.sleep(1)
                except Exception as exc:
                    print(f"{prefix} 补抓暂未完成，后续重试：{exc}", flush=True)
                finally:
                    if browser:
                        browser.close()
    db.checkpoint()
    print(f"本次补齐 {updated} 条；仍缺厂商 {len(pending_rows())} 条（无公开正文或未明确公示的保持为空）")


if __name__ == "__main__":
    main()
