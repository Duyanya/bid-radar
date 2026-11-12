"""探测境外/机房出口 IP 对三家的可用性：python probe_geo2.py <proxy|direct> [cmcc|ct|cu|all]"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

from playwright.sync_api import sync_playwright
import collector as C

proxy = None if (len(sys.argv) < 2 or sys.argv[1] == "direct") else sys.argv[1]
which = sys.argv[2] if len(sys.argv) > 2 else "all"
tag = proxy or "direct"
px = {"server": proxy} if proxy else None


def mk(p, headless=True, ua=None, ios=False):
    b = p.chromium.launch(headless=headless,
                          args=["--disable-blink-features=AutomationControlled", "--no-sandbox"])
    kw = dict(locale="zh-CN", user_agent=ua or C.UA, proxy=px)
    if ios:
        kw.update(viewport={"width": 390, "height": 844}, timezone_id="Asia/Shanghai")
    ctx = b.new_context(**kw)
    ctx.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined});")
    return b, ctx, ctx.new_page()


with sync_playwright() as p:
    if which in ("all", "ct"):
        b, ctx, pg = mk(p, headless=True)
        try:
            pg.goto("https://caigou.chinatelecom.com.cn/", wait_until="networkidle", timeout=90000)
            print(f"[{tag}/CT] load ok title={pg.title()[:30]!r}")
            rows = C.fetch_ct(pg, pages=1)
            print(f"[{tag}/CT] rows={len(rows)}")
            if rows:
                print(f"[{tag}/CT] sample={rows[0]['title'][:40]!r}")
        except Exception as e:
            print(f"[{tag}/CT] ERR {type(e).__name__}: {str(e)[:120]}")
        b.close()

    if which in ("all", "cu"):
        b, ctx, pg = mk(p, headless=False, ua=C.CU_UA, ios=True)
        try:
            pg.goto(C.CU_HOME, wait_until="domcontentloaded", timeout=60000)
            pg.wait_for_timeout(4000)
            print(f"[{tag}/CU] load ok title={pg.title()[:30]!r}")
            rows = C.fetch_cu(pg, pages=1)
            print(f"[{tag}/CU] rows={len(rows)}")
            if rows:
                print(f"[{tag}/CU] sample={rows[0]['title'][:40]!r}")
        except Exception as e:
            print(f"[{tag}/CU] ERR {type(e).__name__}: {str(e)[:120]}")
        b.close()
