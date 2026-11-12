"""探测：从境外/机房出口 IP 访问移动招标站，看 WAF 是否放行。

用法：python probe_geo.py [proxy_url]
不给 proxy 则直连（对照组）。只翻 1 页采购公告，不写库。
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

from playwright.sync_api import sync_playwright
import collector as C

UA = C.UA
proxy = sys.argv[1] if len(sys.argv) > 1 else None
tag = proxy or "direct"

with sync_playwright() as p:
    b = p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled", "--no-sandbox"])
    ctx = b.new_context(locale="zh-CN", user_agent=UA, proxy={"server": proxy} if proxy else None)
    pg = ctx.new_page()
    resp = pg.goto("https://b2b.10086.cn/b2b/main/preparePurchaseNoticeList.html",
                   wait_until="networkidle", timeout=90000)
    pg.wait_for_timeout(4000)
    print(f"[{tag}] page_status={resp.status if resp else 'none'} title={pg.title()[:40]!r}")
    try:
        rows = C.fetch_cmcc(pg, pages=1, notice_type="PROCUREMENT")
        print(f"[{tag}] api_rows={len(rows)}")
        if rows:
            print(f"[{tag}] sample={rows[0]['title'][:50]!r} date={rows[0].get('publish_date')}")
    except Exception as e:
        print(f"[{tag}] api_error={type(e).__name__}: {str(e)[:120]}")
    # 页面里是否出现拦截字样
    txt = pg.content()
    for k in ("瑞数", "访问验证", "安全验证", "人机", "blocked", "captcha"):
        if k.lower() in txt.lower():
            print(f"[{tag}] has_marker={k}")
    b.close()
