# -*- coding: utf-8 -*-
"""体检：设备采购残留 / 建设内容泛词 / 中选人字段"""
import sqlite3, re, sys

DB = r"C:/Users/Administrator/Documents/NinesWork/Outputs/bid-radar/data/bids.db"
c = sqlite3.connect(DB)
c.row_factory = sqlite3.Row

cols = [d[1] for d in c.execute("pragma table_info(bids)")]
print("COLUMNS:", cols)
print("总数:", c.execute("select count(*) from bids").fetchone()[0])

DEV = ("设备采购", "采购设备", "设备购置", "购置设备", "硬件采购", "采购硬件",
       "设备招标", "采购项目", "设备及安装", "设备采购及安装", "采购及安装")

print("\n===== A. 疑似设备采购（标题/建设内容/正文命中）=====")
hit = 0
for r in c.execute("select * from bids"):
    blob = " ".join(str(r[k] or "") for k in ("title", "content", "build_content"))
    m = [w for w in DEV if w in blob]
    if m:
        hit += 1
        print(f"[{hit}] {r['operator']} | {r['publish_date']} | id={r['id']}")
        print("   标题:", r["title"][:80])
        print("   命中词:", m)
        print("   建设内容:", (r["build_content"] or "")[:90])
print("A 命中合计:", hit)

print("\n===== B. 建设内容含泛词 =====")
GEN = ("项目", "询比", "采购", "招标", "公告", "公示", "中选", "比选", "谈判", "竞争性")
b = 0
for r in c.execute("select * from bids"):
    bc = r["build_content"] or ""
    m = [w for w in GEN if w in bc]
    if m:
        b += 1
        print(f"[{b}] {r['operator']} id={r['id']} 泛词={m} -> {bc[:90]}")
print("B 命中合计:", b)

print("\n===== C. 云南 家宽/装维/智能体 相关 =====")
for r in c.execute("select * from bids where title like '%云南%' or title like '%家宽%' or title like '%装维%' or title like '%智能体%'"):
    print("id:", r["id"], "|", r["operator"], "|", r["publish_date"])
    print("  标题:", r["title"][:100])
    for k in cols:
        if k in ("winner", "winner_name", "bid_winner", "award", "supplier"):
            print(f"  {k}:", r[k])
    print("  建设内容:", (r["build_content"] or "")[:100])

print("\n===== D. 中选/中标人字段有值的条数 =====")
for k in ("winner", "winner_name", "bid_winner", "award", "supplier"):
    if k in cols:
        n = c.execute(f"select count(*) from bids where {k} is not null and trim({k})!=''").fetchone()[0]
        print(f"  {k}: {n} 条有值")

print("\n===== E. 建设内容为空的 =====")
n = c.execute("select count(*) from bids where build_content is null or trim(build_content)=''").fetchone()[0]
print("  空建设内容:", n)
