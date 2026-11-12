# -*- coding: utf-8 -*-
"""拉一条详情，看正文里中选人长什么样，并测 parse_winner。"""
import re, sys
import collector
from playwright.sync_api import sync_playwright

RID, UUID, PT = sys.argv[1], sys.argv[2], (sys.argv[3] if len(sys.argv) > 3 else "SELECTION_RESULTS")

with sync_playwright() as p:
    b, pg = collector.launch(p)
    try:
        pg.goto("https://b2b.10086.cn/b2b/main/preparePurchaseNoticeList.html",
                wait_until="networkidle", timeout=90000)
        pg.wait_for_timeout(3000)
        txt, meta, err = collector.fetch_cmcc_detail(pg, {"id": RID, "uuid": UUID, "publishType": PT})
    finally:
        b.close()

print("err=", err, "len=", len(txt or ""))
if txt:
    print("--- 含「中选/成交/中标/供应商/名通」的行 ---")
    n = 0
    for line in txt.split("\n"):
        s = line.strip()
        if not s:
            continue
        if re.search(r"中选|成交|中标|供应商|名通|单位名称", s):
            print("  ", s[:90])
            n += 1
            if n >= 14:
                break
    print("--- parse_winner =>", repr(collector.parse_winner(txt)))
    print("--- parse_amount =>", collector.parse_amount(txt))
