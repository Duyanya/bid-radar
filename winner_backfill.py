# -*- coding: utf-8 -*-
"""补中选人：结果类公告按 SELECTION_RESULTS 重抓详情，解析中选厂商并修 URL。"""
import re, sqlite3, sys, time, random
import collector, db
from playwright.sync_api import sync_playwright

conn = sqlite3.connect("data/bids.db")
conn.row_factory = sqlite3.Row

rows = [r for r in conn.execute(
    "select id,uuid,title,winner,content,build_content,snapshot_path,url,notice_type "
    "from bids where operator='中国移动' order by publish_date desc")
    if re.search(r"结果公示|中选|中标|成交|候选人", r["title"])]
need = [r for r in rows if not (r["winner"] or "").strip()]
print("结果类 %d 条，缺中选人 %d 条" % (len(rows), len(need)))
limit = int(sys.argv[1]) if len(sys.argv) > 1 else 45
need = need[:limit]

got = 0
with sync_playwright() as p:
    b, pg = collector.launch(p)
    try:
        pg.goto("https://b2b.10086.cn/b2b/main/preparePurchaseNoticeList.html",
                wait_until="networkidle", timeout=90000)
        pg.wait_for_timeout(3000)
        for r in need:
            txt, meta, err = collector.fetch_cmcc_detail(pg, {
                "id": r["id"].replace("cmcc_", ""), "uuid": r["uuid"],
                "publishType": "SELECTION_RESULTS"})
            if err or not txt:
                print("  x %s %s" % (r["title"][:30], (err or "")[:40]))
                time.sleep(random.uniform(1.0, 2.0))
                continue
            w = collector.parse_winner(txt)
            sets = []
            args = []
            if w:
                sets.append("winner=?")
                args.append(w)
                got += 1
            if not (r["content"] or "").strip():
                sets.append("content=?")
                args.append(txt[:8000])
            bc = collector.parse_build_content(txt, r["title"])
            if bc and (not (r["build_content"] or "").strip() or len(bc) > 6):
                sets.append("build_content=?")
                args.append(bc)
            snap = db.save_snapshot(r["id"], txt)
            if snap:
                sets.append("snapshot_path=?")
                args.append(snap)
            newurl = re.sub(r"publishType=[A-Z_]+", "publishType=SELECTION_RESULTS", r["url"])
            if newurl != r["url"]:
                sets.append("url=?")
                args.append(newurl)
            if sets:
                args.append(r["id"])
                conn.execute("update bids set " + ",".join(sets) + " where id=?", args)
                conn.commit()
            print("  %s %s | 中选人=%s" % ("v" if w else "-", r["title"][:34], w or "—"))
            time.sleep(random.uniform(1.2, 2.2))
    finally:
        b.close()

print("\n补齐中选人 %d 条" % got)
tot = conn.execute("select count(*) from bids where winner is not null and winner!=''").fetchone()[0]
print("全库有中选人 %d / %d" % (tot, conn.execute("select count(*) from bids").fetchone()[0]))
for r in conn.execute("select title,winner from bids where winner!='' and winner is not null "
                      "order by publish_date desc limit 8"):
    print("   ", r["title"][:40], "→", r["winner"])
