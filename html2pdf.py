"""用 Playwright 把文档 HTML 渲染为 PDF。"""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = Path(r"C:\Users\Administrator\Documents\NinesWork\Outputs\bid-radar")

with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    pg = b.new_page()
    for name in ("需求文档", "使用说明"):
        src = BASE / f"{name}.html"
        if not src.exists():
            continue
        pg.goto(src.as_uri(), wait_until="networkidle", timeout=30000)
        pg.wait_for_timeout(800)
        out = BASE / f"{name}.pdf"
        pg.pdf(
            path=str(out),
            format="A4",
            print_background=True,
            margin={"top": "16mm", "bottom": "16mm", "left": "14mm", "right": "14mm"},
        )
        print(f"{out.name}  {out.stat().st_size:,} 字节")
    b.close()
