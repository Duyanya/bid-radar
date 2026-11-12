"""把 Markdown 文档转成带中文样式的 HTML，便于打印/分发为 PDF。"""
import sys
import re
from pathlib import Path

import markdown

BASE = Path(r"C:\Users\Administrator\Documents\NinesWork\Outputs\bid-radar")

CSS = """
@page { size: A4; margin: 18mm 16mm; }
* { box-sizing: border-box; }
body {
  font-family: "Microsoft YaHei", "PingFang SC", "Hiragino Sans GB", sans-serif;
  font-size: 10.5pt; line-height: 1.75; color: #1f2430;
  max-width: 900px; margin: 0 auto; padding: 24px 32px;
}
h1 {
  font-size: 21pt; color: #1a365d; border-bottom: 3px solid #2b6cb0;
  padding-bottom: 10px; margin: 0 0 22px;
}
h2 {
  font-size: 14.5pt; color: #2b6cb0; margin: 28px 0 12px;
  padding-left: 10px; border-left: 4px solid #2b6cb0;
}
h3 { font-size: 12pt; color: #2c5282; margin: 18px 0 8px; }
table {
  border-collapse: collapse; width: 100%; margin: 12px 0 18px;
  font-size: 9.5pt; page-break-inside: avoid;
}
th {
  background: #2b6cb0; color: #fff; padding: 7px 9px;
  text-align: left; font-weight: 600; border: 1px solid #2b6cb0;
}
td { padding: 6px 9px; border: 1px solid #cbd5e0; vertical-align: top; }
tr:nth-child(even) td { background: #f7fafc; }
code {
  background: #edf2f7; padding: 1px 5px; border-radius: 3px;
  font-family: Consolas, "Courier New", monospace; font-size: 9pt; color: #c53030;
}
pre {
  background: #1a202c; color: #e2e8f0; padding: 13px 16px;
  border-radius: 5px; overflow-x: auto; font-size: 9pt; line-height: 1.55;
}
pre code { background: none; color: inherit; padding: 0; }
blockquote {
  border-left: 4px solid #ecc94b; background: #fffff0;
  margin: 12px 0; padding: 9px 16px; color: #744210;
}
ul, ol { padding-left: 24px; margin: 8px 0; }
li { margin: 3px 0; }
hr { border: none; border-top: 1px solid #e2e8f0; margin: 26px 0; }
strong { color: #1a365d; }
em { color: #718096; font-style: normal; font-size: 9.5pt; }
"""


def convert(md_path, title):
    text = md_path.read_text(encoding="utf-8")
    body = markdown.markdown(
        text, extensions=["tables", "fenced_code", "nl2br", "sane_lists"]
    )
    html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>{title}</title><style>{CSS}</style></head>
<body>{body}</body></html>"""
    out = md_path.with_suffix(".html")
    out.write_text(html, encoding="utf-8")
    return out


if __name__ == "__main__":
    for name in ("需求文档", "使用说明"):
        p = BASE / f"{name}.md"
        if p.exists():
            o = convert(p, name)
            print(f"{o.name}  {o.stat().st_size:,} 字节")
