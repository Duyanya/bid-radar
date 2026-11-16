"""把 bids.db 导出成纯静态站点（GitHub Pages / 任意静态托管可用）。

产出 site/：
  index.html            由根目录 index.html 改写：接口换成静态 JSON、快照换成静态文件
  data/bids.json        /api/bids 的快照（全量，结构完全一致）
  data/stats.json       /api/stats 的快照
  snap/<id>.html        每条公告的快照原文
  .nojekyll             让 Pages 不做 Jekyll 处理

用法：python build_static.py [输出目录]
"""
import json
import os
import shutil
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else BASE / "site"
sys.path.insert(0, str(BASE))
import db  # noqa: E402
from network_scope import classify_network, RULE_VERSION


def main() -> int:
    db.init()
    rows = db.query(limit=100000)
    previous_data = OUT / 'data' / 'bids.json'
    if previous_data.exists():
        previous_rows = json.loads(previous_data.read_text(encoding='utf-8')).get('rows', [])
        missing_ids = {row['id'] for row in previous_rows} - {row['id'] for row in rows}
        if missing_ids:
            raise RuntimeError(f'历史留存保护：数据库缺少 {len(missing_ids)} 条已发布记录，停止发布，保留原站点。')
    stats = dict(db.stats())
    stats["ok"] = True
    for row in rows:
        inside, level, reason = classify_network(row.get("title", ""), row.get("content", ""))
        row.update(in_scope=inside, scope_level=level, scope_reason=reason, scope_version=RULE_VERSION)
    selected = [row for row in rows if row["in_scope"]]
    stats["network"] = {
        "total": len(selected),
        "active": sum(row.get("status") == "active" for row in selected),
        "archived": sum(row.get("status") == "archived" for row in selected),
        "with_amount": sum(bool(row.get("amount_value")) and float(row["amount_value"]) > 0 for row in selected),
        "with_winner": sum(bool(row.get("winner")) for row in selected),
        "cmcc": sum(row.get("operator") == "中国移动" for row in selected),
        "ct": sum(row.get("operator") == "中国电信" for row in selected),
        "cu": sum(row.get("operator") == "中国联通" for row in selected),
    }
    stats["scope_version"] = RULE_VERSION
    try:
        pub = (BASE / "data" / "public_url.txt").read_text(encoding="utf-8").strip()
    except OSError:
        pub = ""
    stats["public_url"] = pub

    # Retain historical snapshots; scope changes never remove stored records/files.
    (OUT / "data").mkdir(parents=True, exist_ok=True)
    (OUT / "snap").mkdir(parents=True, exist_ok=True)

    (OUT / "data" / "bids.json").write_text(
        json.dumps({"ok": True, "count": len(rows), "rows": rows}, ensure_ascii=False),
        encoding="utf-8")
    (OUT / "data" / "stats.json").write_text(
        json.dumps(stats, ensure_ascii=False), encoding="utf-8")

    # 快照：按 id 落成静态文件
    snap_ok = 0
    for r in rows:
        sp = r.get("snapshot_path") or ""
        if not sp:
            continue
        src = BASE / sp
        if not src.exists():
            continue
        dst = OUT / "snap" / f"{r['id']}.html"
        shutil.copyfile(src, dst)
        snap_ok += 1

    # 文档 PDF 一起发布，公网可直接下载
    docs = OUT / "docs"
    docs.mkdir(exist_ok=True)
    for src_name, dst_name in (("使用说明.pdf", "usage.pdf"), ("需求文档.pdf", "requirements.pdf")):
        src = BASE / src_name
        if src.exists():
            (docs / dst_name).write_bytes(src.read_bytes())

    # index.html：注入静态适配层
    html = (BASE / "index.html").read_text(encoding="utf-8")
    shutil.copyfile(BASE / "public_adapter.js", OUT / "public_adapter.js")
    shim = '<script src="./public_adapter.js"></script>'
    if "</head>" not in html:
        print("!! index.html 缺少 </head>，无法注入")
        return 2
    html = html.replace("</head>", shim + "</head>", 1)
    # 快照链接：/api/snapshot?id=x -> ./snap/x.html
    old = '/api/snapshot?id=${encodeURIComponent(r.id)}'
    new = './snap/${encodeURIComponent(r.id)}.html'
    if old not in html:
        print("!! 未找到快照链接模板，静态版快照会失效")
        return 3
    html = html.replace(old, new)
    (OUT / "index.html").write_text(html, encoding="utf-8")
    (OUT / ".nojekyll").write_text("", encoding="utf-8")

    size = sum(f.stat().st_size for f in OUT.rglob("*") if f.is_file())
    print(f"site/ 生成完成：{len(rows)} 条记录、{snap_ok} 份快照、共 {size/1024/1024:.1f} MB")
    print(f"  数据：data/bids.json ({(OUT/'data'/'bids.json').stat().st_size/1024:.0f} KB)"
          f"，data/stats.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
