# -*- coding: utf-8 -*-
"""一次性维护：①剔设备采购 ②重建建设内容 ③关键词补扫入库 ④补中选人

用法：python refine_all.py [--no-detail]
"""
import datetime, re, sqlite3, sys, time, os, shutil
import html as htmllib
import collector, classifier, db

DB = "data/bids.db"


def log(*a):
    print(*a, flush=True)


def snapshot_text(path):
    if not path:
        return ""
    p = path if os.path.isabs(path) else os.path.join("data", "snapshots", os.path.basename(path))
    for cand in (p, os.path.join("data", "snapshots", os.path.basename(path))):
        if os.path.exists(cand):
            try:
                raw = open(cand, "r", encoding="utf-8", errors="ignore").read()
            except Exception:
                return ""
            if "<html" in raw[:400].lower() or "<p" in raw[:400].lower():
                raw = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", raw, flags=re.S | re.I)
                raw = re.sub(r"<[^>]+>", "\n", raw)
                raw = htmllib.unescape(raw)
                raw = re.sub(r"[ \t\u3000]+", " ", raw)
                raw = re.sub(r"\n{2,}", "\n", raw)
            return raw
    return ""


def main():
    do_detail = "--no-detail" not in sys.argv
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    shutil.copy(DB, f"data/bids.db.bak-refine-{ts}")
    log(f"[0] 备份 data/bids.db.bak-refine-{ts}")

    c = db.conn()
    c.row_factory = sqlite3.Row
    rows = [dict(r) for r in c.execute("select * from bids").fetchall()]
    log(f"[1] 现有 {len(rows)} 条")

    # ---- ① 按新规则重新分类，剔除设备采购等 ----
    dropped = []
    for r in rows:
        ok, lv, why = classifier.classify(r["title"] or "", r.get("content") or "")
        if not ok:
            dropped.append((r["id"], r["title"], why))
    for bid, title, why in dropped:
        c.execute("delete from bids where id=?", (bid,))
    c.commit()
    log(f"[2] 剔除 {len(dropped)} 条：")
    for bid, title, why in dropped:
        log(f"     - [{why}] {title[:52]}")
    rows = [r for r in rows if r["id"] not in {d[0] for d in dropped}]

    # ---- ② 重建建设内容（正文优先，标题兜底） ----
    fixed = 0
    for r in rows:
        txt = r.get("content") or ""
        if not txt or len(txt) < 40:
            txt = snapshot_text(r.get("snapshot_path"))
        bc = collector.parse_build_content(txt, r["title"] or "")
        if bc and bc != (r.get("build_content") or ""):
            c.execute("update bids set build_content=? where id=?", (bc, r["id"]))
            r["build_content"] = bc
            fixed += 1
    c.commit()
    log(f"[3] 建设内容重建 {fixed} 条")

    # ---- ③④ 详情：补中选人 / 补正文 ----
    if not do_detail:
        return
    from playwright.sync_api import sync_playwright
    need_cmcc = [r for r in rows if r["id"].startswith("cmcc_")]
    need_cu = [r for r in rows if r["id"].startswith("cu_")]

    def cmcc_ptype(r):
        t = r["title"] or ""
        if any(k in t for k in ("中选", "中标", "成交", "候选人", "结果")):
            return "SELECTION_RESULTS"
        return "PROCUREMENT"

    got_w = got_c = 0
    with sync_playwright() as p:
        b, pg = collector.launch(p)
        try:
            pg.goto("https://b2b.10086.cn/b2b/main/preparePurchaseNoticeList.html",
                    wait_until="networkidle", timeout=90000)
            pg.wait_for_timeout(3500)
            for r in need_cmcc[:30]:
                nid = r["id"].replace("cmcc_", "")
                item = {"id": nid, "uuid": r.get("uuid") or "", "publishType": cmcc_ptype(r)}
                txt, meta, err = collector.fetch_cmcc_detail(pg, item)
                if err and cmcc_ptype(r) == "SELECTION_RESULTS":
                    # 类型猜错时换另一种再试
                    item["publishType"] = "PROCUREMENT"
                    txt, meta, err = collector.fetch_cmcc_detail(pg, item)
                if err or not txt:
                    log(f"    ✗ CMCC {r['title'][:34]} → {str(err)[:40]}")
                    time.sleep(1.2)
                    continue
                upd = {}
                w = collector.parse_winner(txt)
                if w and w != r.get("winner"):
                    upd["winner"] = w
                    got_w += 1
                bc = collector.parse_build_content(txt, r["title"] or "")
                if bc and bc != r.get("build_content"):
                    upd["build_content"] = bc
                    got_c += 1
                if not (r.get("content") or ""):
                    upd["content"] = txt[:8000]
                if upd:
                    sets = ",".join(f"{k}=?" for k in upd)
                    c.execute(f"update bids set {sets} where id=?", (*upd.values(), r["id"]))
                if not r.get("snapshot_path"):
                    try:
                        sp = db.save_snapshot(r["id"], txt)
                        c.execute("update bids set snapshot_path=? where id=?", (sp, r["id"]))
                    except Exception:
                        pass
                log(f"    ✓ CMCC {r['title'][:32]} | 中选={upd.get('winner') or '—'}")
                time.sleep(1.3)
            c.commit()
        finally:
            b.close()

        if need_cu:
            b2 = None
            try:
                b2, ctx2, pg2 = collector.cuisine(p)
                pg2.goto(collector.CU_HOME, wait_until="domcontentloaded", timeout=45000)
                pg2.wait_for_timeout(4000)
                for r in need_cu[:20]:
                    if not r.get("uuid"):
                        continue
                    txt, meta, err = collector.fetch_cu_detail(pg2, r["uuid"])
                    if err or not txt:
                        log(f"    ✗ CU {r['title'][:34]} → {str(err)[:40]}")
                        continue
                    upd = {}
                    w = collector.parse_winner(txt)
                    if w and w != r.get("winner"):
                        upd["winner"] = w
                        got_w += 1
                    bc = collector.parse_build_content(txt, r["title"] or "")
                    if bc and bc != r.get("build_content"):
                        upd["build_content"] = bc
                        got_c += 1
                    if not (r.get("content") or ""):
                        upd["content"] = txt[:8000]
                    if not r.get("snapshot_path"):
                        try:
                            upd["snapshot_path"] = db.save_snapshot(r["id"], txt)
                        except Exception:
                            pass
                    if upd:
                        sets = ",".join(f"{k}=?" for k in upd)
                        c.execute(f"update bids set {sets} where id=?", (*upd.values(), r["id"]))
                    log(f"    ✓ CU {r['title'][:32]} | 中选={upd.get('winner') or '—'}")
                    time.sleep(1.8)
                c.commit()
            except Exception as e:
                log(f"    [CU] 失败: {type(e).__name__}: {str(e)[:100]}")
            finally:
                if b2:
                    b2.close()

    log(f"[4] 详情：新增中选人 {got_w} 条，改进建设内容 {got_c} 条")


if __name__ == "__main__":
    main()
