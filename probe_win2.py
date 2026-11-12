# -*- coding: utf-8 -*-
"""单条诊断：云南家宽装维智能体结果公示，为什么中选人抓不到。"""
import re, sqlite3, time
import collector
from playwright.sync_api import sync_playwright

conn = sqlite3.connect("data/bids.db")
conn.row_factory = sqlite3.Row
r = conn.execute("select * from bids where title like '%装维智能体%'").fetchone()
print("标题:", r["title"])
print("id:", r["id"], "uuid:", r["uuid"])
print("url:", r["url"][:160])
print("content 长度:", len(r["content"] or ""), " winner:", r["winner"])

with sync_playwright() as p:
    b, pg = collector.launch(p)
    try:
        pg.goto("https://b2b.10086.cn/b2b/main/preparePurchaseNoticeList.html",
                wait_until="networkidle", timeout=90000)
        pg.wait_for_timeout(2500)
        for pt in ("SELECTION_RESULTS", "PROCUREMENT"):
            txt, meta, err = collector.fetch_cmcc_detail(pg, {
                "id": r["id"].replace("cmcc_", ""), "uuid": r["uuid"], "publishType": pt})
            print("\n=== publishType=%s err=%s len=%s" % (pt, err, len(txt or "")))
            if txt:
                print("  开头:", txt[:200].replace("\n", " "))
                print("  parse_winner ->", collector.parse_winner(txt))
                hit = re.search(r"(中选人|中标人|成交人|中选供应商)[^\n]{0,80}", txt)
                if hit:
                    print("  命中行:", hit.group(0))
            time.sleep(1.5)
    finally:
        b.close()
