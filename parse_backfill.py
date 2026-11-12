# -*- coding: utf-8 -*-
"""离线回填中选人：只用库里已存的 content / 快照正文重解析，不访问运营商接口。"""
import os, sqlite3, re
import collector

conn = sqlite3.connect("data/bids.db")
conn.row_factory = sqlite3.Row

rows = conn.execute("select id,title,winner,content,snapshot_path from bids "
                    "where (winner is null or winner='')").fetchall()
print("缺中选人 %d 条" % len(rows))

fixed = 0
for r in rows:
    if not re.search(r"结果公示|中选|中标|成交|候选人", r["title"] or ""):
        continue
    txt = (r["content"] or "").strip()
    if len(txt) < 30 and r["snapshot_path"] and os.path.exists(r["snapshot_path"]):
        try:
            txt = open(r["snapshot_path"], encoding="utf-8", errors="ignore").read()
        except Exception:
            pass
    if not txt:
        continue
    w = collector.parse_winner(txt)
    if w:
        conn.execute("update bids set winner=? where id=?", (w, r["id"]))
        fixed += 1
        print("  v %s -> %s" % (r["title"][:38], w))

conn.commit()
tot = conn.execute("select count(*) from bids where winner is not null and winner!=''").fetchone()[0]
alln = conn.execute("select count(*) from bids").fetchone()[0]
print("\n本次离线补齐 %d 条；全库有中选人 %d / %d" % (fixed, tot, alln))
for r in conn.execute("select title,winner from bids where winner!='' and winner is not null "
                      "order by publish_date desc limit 6"):
    print("   ", r["title"][:36], "→", r["winner"])
