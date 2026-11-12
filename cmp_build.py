# -*- coding: utf-8 -*-
"""对比：库内现有 build_content  vs  正文筛选提炼结果。"""
import sqlite3
import collector

c = sqlite3.connect("data/bids.db")
rows = c.execute(
    "select id,operator,title,build_content,content from bids "
    "where length(coalesce(content,''))>400 order by operator, publish_date desc"
).fetchall()

lim = {"中国移动": 4, "中国联通": 4, "中国电信": 2}
seen = {}
for rid, op, title, old, ct in rows:
    if seen.get(op, 0) >= lim.get(op, 0):
        continue
    seen[op] = seen.get(op, 0) + 1
    new = collector.parse_build_content(ct or "", title)
    print("=" * 70)
    print(f"[{op}] {title[:56]}")
    print(f"  旧: {old}")
    print(f"  新: {new}")
print("=" * 70)
