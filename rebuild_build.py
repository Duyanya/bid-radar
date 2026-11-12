# -*- coding: utf-8 -*-
"""全库建设内容重算 + 逐条差异输出（dry-run 默认，--apply 落库）。"""
import sqlite3
import sys

import collector

APPLY = "--apply" in sys.argv
c = sqlite3.connect("data/bids.db")
rows = c.execute(
    "select id,operator,title,build_content,content from bids order by operator, publish_date desc"
).fetchall()

chg, empty, same = [], 0, 0
for rid, op, title, old, ct in rows:
    new = collector.parse_build_content(ct or "", title or "")
    if not new:
        empty += 1
        continue
    if (old or "").strip() == new.strip():
        same += 1
        continue
    chg.append((rid, op, title or "", (old or ""), new))

# 只在「新结果不比旧的差」时替换，避免把已写好的详细内容压短
def better(old, new):
    old = (old or "").strip()
    if not old:
        return True
    if len(old) <= 25:            # 旧值只是标题提炼，直接换
        return True
    return len(new) >= len(old) * 0.8

chg = [c for c in chg if better(c[3], c[4])]

print(f"总条数 {len(rows)}  变化 {len(chg)}  不变 {same}  提炼为空 {empty}")
for rid, op, title, old, new in chg:
    print("-" * 66)
    print(f"[{op}] {title[:50]}")
    print(f"  旧({len(old)}): {old[:120]}")
    print(f"  新({len(new)}): {new[:200]}")

if APPLY and chg:
    c.executemany("update bids set build_content=? where id=?", [(n, i) for i, _, _, _, n in chg])
    c.commit()
    print(f"\n已落库 {len(chg)} 条")
elif chg:
    print("\n(dry-run，未写库；加 --apply 落库)")
