# -*- coding: utf-8 -*-
"""探测移动公告接口是否支持关键词过滤，并找『数字化网络运营沙盘』"""
import json, sys, time
from playwright.sync_api import sync_playwright
import collector

LIST = collector.CMCC_LIST
VARIANT = [
    {"name": "沙盘"},
    {"keyword": "沙盘"},
    {"title": "沙盘"},
    {"searchKey": "沙盘"},
    {"publishName": "沙盘"},
    {"projectName": "沙盘"},
    {"annoName": "沙盘"},
    {"blurry": "沙盘"},
]

def main():
    with sync_playwright() as p:
        b, pg = collector.launch(p)
        try:
            pg.goto("https://b2b.10086.cn/b2b/main/preparePurchaseNoticeList.html",
                   wait_until="networkidle", timeout=90000)
            pg.wait_for_timeout(4000)
            for v in VARIANT:
                body = {"current": 1, "size": 10, "publishOneType": "PROCUREMENT",
                        "sfactApplColumn5": "PC"}
                body.update(v)
                try:
                    j = pg.evaluate("""async ([path, body]) => {
                        const r = await fetch(path, {method:'POST',
                            headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
                        return await r.json();
                    }""", [LIST, body])
                except Exception as e:
                    print(f"{list(v)[0]:14s} ERR {str(e)[:60]}")
                    continue
                d = (j.get("data") or {})
                recs = d.get("content") or []
                total = d.get("total")
                names = [ (r.get("name") or "")[:38] for r in recs[:3] ]
                hit = sum(1 for r in recs if "沙盘" in (r.get("name") or ""))
                print(f"{list(v)[0]:14s} total={total} n={len(recs)} 含沙盘={hit} {names}")
                time.sleep(1.0)
        finally:
            b.close()

main()
