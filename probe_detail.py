# -*- coding: utf-8 -*-
"""用 name 关键词搜索，dump 完整字段（找漏抓公告）"""
import json, sys, time
from playwright.sync_api import sync_playwright
import collector

def main(kws, ptype):
    out = []
    with sync_playwright() as p:
        b, pg = collector.launch(p)
        try:
            pg.goto("https://b2b.10086.cn/b2b/main/preparePurchaseNoticeList.html",
                    wait_until="networkidle", timeout=90000)
            pg.wait_for_timeout(4000)
            for kw in kws:
                body = {"current": 1, "size": 20, "publishOneType": ptype,
                        "sfactApplColumn5": "PC", "name": kw}
                j = pg.evaluate("""async ([path, body]) => {
                    const r = await fetch(path, {method:'POST',
                        headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
                    return await r.json();
                }""", [collector.CMCC_LIST, body])
                recs = (j.get("data") or {}).get("content") or []
                print(f"\n### 关键词={kw} 类型={ptype} 命中={len(recs)}")
                for r in recs:
                    print(json.dumps({k: r.get(k) for k in
                          ("id", "uuid", "name", "publishDate", "publishOneType",
                           "publishOneType_dictText", "companyTypeName", "publishType")},
                          ensure_ascii=False))
                out += recs
                time.sleep(1.2)
        finally:
            b.close()
    return out

if __name__ == "__main__":
    kws = sys.argv[1].split(",") if len(sys.argv) > 1 else ["沙盘"]
    ptype = sys.argv[2] if len(sys.argv) > 2 else "PROCUREMENT"
    main(kws, ptype)
