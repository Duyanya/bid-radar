# -*- coding: utf-8 -*-
"""关键词补扫 → 分类 → 详情（中选人/金额/建设内容）→ 入库。只动移动。"""
import datetime, re, sqlite3, sys, time, random
import collector, classifier, db
from playwright.sync_api import sync_playwright

KWS = ["沙盘", "数字化网络运营", "数字孪生", "自智网络", "网络运营", "算力网络",
       "承载网", "核心网", "接入网", "传输网", "网管", "OSS", "编排", "云网",
       "专网", "网优", "数据中台", "智能体", "网络中台", "网络大脑"]


def main(limit_detail=40):
    db.init()
    conn = sqlite3.connect("data/bids.db")
    conn.row_factory = sqlite3.Row
    have = {r["id"] for r in conn.execute("select id from bids")}
    print("库内现有 %d 条" % len(have))

    with sync_playwright() as p:
        b, pg = collector.launch(p)
        try:
            pg.goto("https://b2b.10086.cn/b2b/main/preparePurchaseNoticeList.html",
                    wait_until="networkidle", timeout=90000)
            pg.wait_for_timeout(3000)
            rows = collector.sweep_cmcc(pg, KWS)
        finally:
            b.close()
    print("补扫命中 %d 条（含已在库）" % len(rows))

    new, dropped = [], []
    for r in rows:
        if r["id"] in have:
            continue
        ok, lv, why = classifier.classify(r.get("title", ""))
        if ok:
            r["relevance"], r["relevance_reason"] = lv, why
            new.append(r)
        else:
            dropped.append((r.get("title", "")[:46], why))
    print("新增待入库 %d 条，剔除 %d 条" % (len(new), len(dropped)))
    for t, w in dropped[:15]:
        print("   - %s [%s]" % (t, w))

    # 详情：补正文/金额/中选人/建设内容
    if new:
        with sync_playwright() as p:
            b, pg = collector.launch(p)
            try:
                pg.goto("https://b2b.10086.cn/b2b/main/preparePurchaseNoticeList.html",
                        wait_until="networkidle", timeout=90000)
                pg.wait_for_timeout(3000)
                collector.enrich_detail(pg, new, limit=limit_detail)
                # 详情失败（瑞数 confuse）时按标题兜底
                for r in new:
                    if not (r.get("build_content") or "").strip():
                        bc = collector.parse_build_content("", r.get("title", ""))
                        if bc:
                            r["build_content"] = bc
            finally:
                b.close()

    ins, upd = db.upsert(new)
    print("\n入库完成 inserted=%d updated=%d" % (ins, upd))
    print("库内总数 = %d" % conn.execute("select count(*) from bids").fetchone()[0])
    for r in conn.execute("select id,title,build_content,winner from bids "
                          "where title like '%沙盘%' or title like '%数字化网络运营%'"):
        print("  ✓", r["id"], "|", r["build_content"], "| winner:", r["winner"] or "—")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 40)
