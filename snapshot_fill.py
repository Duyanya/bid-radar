# -*- coding: utf-8 -*-
"""为缺正文/缺快照的记录补齐本地存档快照。

内容非空的 → 详情页快照（正文归档）；
内容为空的（如电信详情被网关 401 拦截）→ 列表页快照，如实标注"正文需门户登录"。
用法: python snapshot_fill.py [--apply]
"""
import html
import io
import os
import sys
import sqlite3
from datetime import datetime

db = sqlite3.connect("data/bids.db")
db.row_factory = sqlite3.Row
os.makedirs("data/snapshots", exist_ok=True)

TPL = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>{title}</title>
<style>
 body{{margin:0;padding:32px;background:#0f1115;color:#e6e8ee;
      font:15px/1.75 "Microsoft YaHei",system-ui,sans-serif}}
 .wrap{{max-width:860px;margin:0 auto}}
 h1{{font-size:20px;line-height:1.5;margin:0 0 18px}}
 table{{border-collapse:collapse;width:100%;margin:0 0 22px}}
 td{{border-bottom:1px solid #262a33;padding:7px 10px;vertical-align:top}}
 td.k{{color:#8b93a7;width:120px;white-space:nowrap}}
 .body{{white-space:pre-wrap;background:#151821;border:1px solid #262a33;
        border-radius:8px;padding:16px}}
 .note{{margin-top:18px;padding:12px 14px;border-left:3px solid #d9a441;
        background:#1b1a14;color:#d8cfa9;font-size:13.5px}}
 a{{color:#6fb3ff}}
</style></head><body><div class="wrap">
<h1>{title}</h1>
<table>{meta}</table>
{bodyblock}
<div class="note">{note}</div>
</div></body></html>
"""

def fill(apply=True):
    rows = db.execute("select * from bids").fetchall()

    made, skipped = [], 0
    for r in rows:
        path = r["snapshot_path"] or ""
        if path and os.path.exists(path):
            skipped += 1
            continue
        title = r["title"] or "(无标题)"
        content = (r["content"] or "").strip()
        detail = bool(content)
        note = ("本文为采集时官网详情页正文的本地存档。" if detail else
                "本条公告的详情页（/portal/noticeDetail）返回 401 认证失败，正文需门户登录后才能查看；"
                "此处仅归档采集到的列表字段与官网链接，官网下架后仍可核对标题、日期与类型。")
        meta = [
            ("运营商", r["operator"] or "—"),
            ("公告类型", r["notice_type"] or "—"),
            ("发布日期", r["publish_date"] or "—"),
            ("截止日期", r["deadline"] or "—"),
            ("金额（元）", str(r["amount_value"]) if r["amount_value"] else "未公示"),
            ("中选厂商", r["winner"] or "未公示"),
            ("相关性", r["relevance"] or "—"),
            ("快照类型", "详情页快照" if detail else "列表页快照"),
            ("快照时间", datetime.now().strftime("%Y-%m-%d %H:%M")),
            ("官网链接", '<a href="%s" target="_blank" rel="noopener">%s</a>'
                         % (html.escape(r["url"] or "#"), html.escape((r["url"] or "")[:80]))),
        ]
        bodyblock = ('<div class="body">%s</div>' % html.escape(content)) if detail else ""
        out = "data/snapshots/%s.html" % r["id"]
        io.open(out, "w", encoding="utf-8", newline="\n").write(TPL.format(
            title=html.escape(title),
            meta="".join('<tr><td class="k">%s</td><td>%s</td></tr>' % (k, v) for k, v in meta),
            bodyblock=bodyblock, note=note))
        made.append((r["id"], r["operator"], detail, out))
    
    print("已有快照跳过 %d，新建 %d" % (skipped, len(made)))
    for row in made:
        print("  %-28s %-6s %s" % (row[0][:28], row[1], "详情页" if row[2] else "列表页"))
    
    if apply and made:
        db.executemany("update bids set snapshot_path=? where id=?", [(m[3], m[0]) for m in made])
        db.commit()
        print("已写库 %d 条" % len(made))
    elif not apply:
        print("(dry-run，加 --apply 落库)")
    return skipped, made


if __name__ == "__main__":
    ap = "--apply" in sys.argv
    fill(ap)
