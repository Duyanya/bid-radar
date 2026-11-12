# -*- coding: utf-8 -*-
"""电信详情二次试探：只发 2 个请求，间隔 6 秒，避免触发封禁。"""
import time
import urllib.request
import urllib.error

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")
BASE = "https://caigou.chinatelecom.com.cn"
URLS = [
    BASE + "/portal/noticeDetail?id=4884927341995999232&docId=4884927341995999232",
    BASE + "/portal/noticeDetail?noticeId=4884927341995999232",
]

for i, u in enumerate(URLS):
    req = urllib.request.Request(u, headers={
        "User-Agent": UA,
        "Referer": BASE + "/portal/notice",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
    })
    try:
        r = urllib.request.urlopen(req, timeout=20)
        body = r.read()
        print(i, "HTTP", r.status, "len", len(body), body[:200])
    except urllib.error.HTTPError as e:
        body = e.read()
        print(i, "HTTPError", e.code, "len", len(body), body[:300])
    except Exception as e:
        print(i, "ERR", type(e).__name__, str(e)[:160])
    if i == 0:
        time.sleep(6)
