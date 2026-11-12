# -*- coding: utf-8 -*-
"""验证省直属白名单：抓移动列表，专看标题含 传输局/云网中心/研究院 的公告是否被放行。"""
import sys
import collector, classifier
from playwright.sync_api import sync_playwright

pages = int(sys.argv[1]) if len(sys.argv) > 1 else 3
rows = []
with sync_playwright() as p:
    b, pg = collector.launch(p)
    try:
        pg.goto("https://b2b.10086.cn/b2b/main/preparePurchaseNoticeList.html",
                wait_until="networkidle", timeout=90000)
        pg.wait_for_timeout(3000)
        rows += collector.fetch_cmcc(pg, pages=pages, notice_type="PROCUREMENT")
        rows += collector.fetch_cmcc(pg, pages=pages, notice_type="SELECTION_RESULTS")
    finally:
        b.close()

hit = [r for r in rows if any(u in r["title"] for u in classifier.DIRECT_UNITS)]
print("抓取 %d 条，其中含省直属单位 %d 条" % (len(rows), len(hit)))
for r in hit:
    ok, lv, why = classifier.classify(r["title"], "")
    print(("  + " if ok else "  - ") + r["publish_date"] + " | " + r["title"][:56] + " || " + ("%s:%s" % (lv, why)))
keep = [r for r in rows if classifier.classify(r["title"], "")[0]]
print("整体保留 %d/%d" % (len(keep), len(rows)))
