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


def main() -> int:
    db.init()
    rows = db.query(limit=100000)
    stats = dict(db.stats())
    stats["ok"] = True
    try:
        pub = (BASE / "data" / "public_url.txt").read_text(encoding="utf-8").strip()
    except OSError:
        pub = ""
    stats["public_url"] = pub

    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "data").mkdir(parents=True)
    (OUT / "snap").mkdir(parents=True)

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

    # index.html：注入静态适配层
    html = (BASE / "index.html").read_text(encoding="utf-8")
    shim = "<script>/* 静态托管适配：把 /api/* 映射到预生成的 JSON 与快照文件 */\n(function(){var o=window.fetch.bind(window);\nwindow.fetch=function(u,opt){u=String(u);\n if(u.indexOf('/api/bids')===0)  return o('./data/bids.json',opt);\n if(u.indexOf('/api/stats')===0) return o('./data/stats.json',opt);\n if(u.indexOf('/api/export')===0)return Promise.reject(new Error('static mode'));\n if(u.indexOf('/api/refresh')===0)return Promise.resolve(new Response(JSON.stringify({ok:true,static:true}),{status:200,headers:{'Content-Type':'application/json'}}));\n return o(u,opt);};})();\ndocument.addEventListener('DOMContentLoaded',function(){var b=document.getElementById('rf');\nif(b){b.textContent='云端每日 09:00 自动更新';b.disabled=true;b.style.opacity=.6;\nb.title='公网站点为静态托管，数据由云端定时任务每天 09:00 抓取后自动发布';}});\n</script>"
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
