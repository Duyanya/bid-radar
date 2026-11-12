# -*- coding: utf-8 -*-
"""电信条数体检：原始列表 -> 栏目 -> 省公司 -> 网络域，逐层记账。"""
import collections, json, sys
import collector, classifier
from playwright.sync_api import sync_playwright

pages = int(sys.argv[1]) if len(sys.argv) > 1 else 2
rows = []
with sync_playwright() as p:
    b, pg = collector.launch(p)
    try:
        pg.goto("https://caigou.chinatelecom.com.cn/", wait_until="networkidle", timeout=90000)
        pg.wait_for_timeout(3000)
        rows = collector.fetch_ct(pg, pages=pages)
    finally:
        b.close()

print("\n===== 原始抓取 %d 条 =====" % len(rows))
print("栏目分布:", dict(collections.Counter(r["notice_type"] for r in rows)))
print("日期范围:", min(r["publish_date"] for r in rows), "~", max(r["publish_date"] for r in rows))

keep, drop = [], collections.Counter()
for r in rows:
    ok, lv, why = classifier.classify(r["title"], "")
    if ok:
        keep.append(r)
    else:
        drop[why or "未说明"] += 1

print("\n===== 过滤后保留 %d 条 =====" % len(keep))
print("剔除原因分布:")
for k, v in drop.most_common():
    print("   %-28s %d" % (k, v))

print("\n----- 保留的 -----")
for r in keep:
    print("  +", r["publish_date"], "|", r.get("region", ""), "|", r["title"][:58])
print("\n----- 剔除的（前 40）-----")
n = 0
for r in rows:
    ok, lv, why = classifier.classify(r["title"], "")
    if not ok:
        n += 1
        if n <= 40:
            print("  -", r["publish_date"], "|", r.get("region", ""), "|", r["title"][:52], "||", why)

json.dump({"raw": len(rows), "keep": len(keep), "drop": dict(drop)},
          open("data/ct_diag.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
