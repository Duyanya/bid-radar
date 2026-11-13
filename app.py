"""后端：零依赖 HTTP 服务，提供 API + 静态页面。"""
import gzip, json, os, sys, threading, datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
import db

PORT = int(os.environ.get("PORT", "8848"))
# 0.0.0.0 = 同一局域网内任何设备都能访问；改成 127.0.0.1 则只限本机
HOST = os.environ.get("HOST", "0.0.0.0")


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        ae = (self.headers.get("Accept-Encoding") or "").lower()
        if "gzip" in ae and len(body) > 1024:
            body = gzip.compress(body, 6)
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Vary", "Accept-Encoding")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        p = u.path

        if p in ("/", "/index.html"):
            f = BASE / "index.html"
            if f.exists():
                return self._send(200, f.read_text(encoding="utf-8"), "text/html; charset=utf-8")
            return self._send(404, "index.html missing", "text/plain; charset=utf-8")

        if p == "/api/bids":
            rows = db.query(op=q.get("operator"), kw=q.get("kw"),
                            status=q.get("status"), days=q.get("days"),
                            limit=int(q.get("limit", 500)))
            return self._send(200, json.dumps(
                {"ok": True, "count": len(rows), "rows": rows}, ensure_ascii=False))

        if p == "/api/stats":
            pub = ""
            try:
                f = BASE / "data" / "public_url.txt"
                if f.exists():
                    pub = f.read_text(encoding="utf-8").strip()
            except OSError:
                pub = ""
            return self._send(200, json.dumps({"ok": True, **db.stats(), "public_url": pub}, ensure_ascii=False))

        if p == "/api/export":
            return self.export_csv(q)

        if p == "/api/snapshot":
            bid = q.get("id", "")
            r = [x for x in db.query(limit=9999) if x["id"] == bid]
            if not r or not r[0].get("snapshot_path"):
                return self._send(404, json.dumps({"ok": False, "msg": "无快照"}, ensure_ascii=False))
            f = BASE / r[0]["snapshot_path"]
            if f.exists():
                return self._send(200, f.read_text(encoding="utf-8", errors="ignore"), "text/html; charset=utf-8")
            return self._send(404, json.dumps({"ok": False, "msg": "快照文件缺失"}, ensure_ascii=False))

        return self._send(404, json.dumps({"ok": False, "msg": "not found"}))

    def export_csv(self, q):
        import csv, io
        rows = db.query(op=q.get("operator"), kw=q.get("kw"), status=q.get("status"),
                        limit=9999)
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["名称", "招标内容", "招标信息", "招标时间", "招标金额", "中选厂商", "运营商", "来源", "官网链接", "状态", "首次记录"])
        for r in rows:
            w.writerow([r["title"], (r["content"] or "")[:200], r["notice_type"],
                        r["publish_date"], r["amount_raw"] or "—", r["winner"] or "—",
                        r["operator"], r["source"], r["url"],
                        "在架" if r["status"] == "active" else "已下架", r["first_seen"]])
        data = "\ufeff" + buf.getvalue()
        self.send_response(200)
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        self.send_header("Content-Disposition",
                         f'attachment; filename="bids_{datetime.date.today()}.csv"')
        b = data.encode("utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_POST(self):
        u = urlparse(self.path)
        if u.path == "/api/refresh":
            n = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(n) or b"{}")
            def bg():
                try:
                    import collector
                    collector.run(body.get("which", "all"), int(body.get("pages", 2)), 0)
                except Exception as e:
                    db.log_run("refresh", 0, 0, 0, str(e)[:300])
            threading.Thread(target=bg, daemon=True).start()
            return self._send(200, json.dumps({"ok": True, "msg": "抓取已在后台启动"}, ensure_ascii=False))
        return self._send(404, "{}")


if __name__ == "__main__":
    db.init()
    try:
        from http.server import ThreadingHTTPServer as Srv
    except ImportError:
        Srv = HTTPServer
    srv = Srv((HOST, PORT), H)

    lan = ""
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        lan = s.getsockname()[0]
        s.close()
    except Exception:
        pass

    print(f"Bid Radar -> http://127.0.0.1:{PORT}")
    if lan and HOST == "0.0.0.0":
        print(f"局域网访问 -> http://{lan}:{PORT}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
