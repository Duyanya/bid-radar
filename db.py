"""数据库层：SQLite 持久化。核心原则——一旦入库，官网消失也不丢。"""
import sqlite3, json, os, datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
SNAP = DATA / "snapshots"
DATA.mkdir(exist_ok=True)
SNAP.mkdir(exist_ok=True)
DB = DATA / "bids.db"


def now():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def conn():
    c = sqlite3.connect(DB, timeout=30)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c


SCHEMA = """
CREATE TABLE IF NOT EXISTS bids(
    id TEXT PRIMARY KEY,
    title TEXT,
    content TEXT,
    notice_type TEXT,
    publish_date TEXT,
    deadline TEXT,
    amount_raw TEXT,
    amount_value INTEGER,
    winner TEXT,
    operator TEXT,
    region TEXT,
    source TEXT,
    url TEXT,
    uuid TEXT,
    snapshot_path TEXT,
    first_seen TEXT,
    last_seen TEXT,
    status TEXT DEFAULT 'active',
    days_left INTEGER,
    relevance TEXT,
    relevance_reason TEXT,
    build_content TEXT
);
CREATE INDEX IF NOT EXISTS idx_pub ON bids(publish_date DESC);
CREATE INDEX IF NOT EXISTS idx_op ON bids(operator);
CREATE INDEX IF NOT EXISTS idx_status ON bids(status);

CREATE TABLE IF NOT EXISTS runs(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started TEXT, finished TEXT, operator TEXT,
    fetched INTEGER DEFAULT 0, inserted INTEGER DEFAULT 0,
    updated INTEGER DEFAULT 0, errors TEXT
);
"""


def init():
    with conn() as c:
        c.executescript(SCHEMA)


def checkpoint():
    """把 WAL 内容并回主库文件。

    SQLite 开 WAL 后，提交的数据先落在 bids.db-wal；只复制 bids.db 会拿到旧数据
    （实测：主库 42 行、WAL 里 136 行）。任何"复制/提交/打包"库文件之前必须调用它。
    """
    with conn() as c:
        c.execute("PRAGMA wal_checkpoint(TRUNCATE)")


def save_snapshot(bid_id, html):
    """把详情页原文落盘。官网下线后仍可查。"""
    if not html:
        return None
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in bid_id)[:80]
    p = SNAP / f"{safe}.html"
    try:
        p.write_text(html, encoding="utf-8", errors="ignore")
        return str(p.relative_to(BASE)).replace("\\", "/")
    except Exception:
        return None


def upsert(rows):
    """增量入库：已存在则更新 last_seen（并补全空字段），不存在则插入。"""
    init()
    ins = upd = 0
    ts = now()
    with conn() as c:
        for r in rows:
            bid = r.get("id")
            if not bid:
                continue
            old = c.execute("SELECT * FROM bids WHERE id=?", (bid,)).fetchone()
            if old:
                # 只补空字段，不覆盖已有值（防止官网改动抹掉历史）
                fields, vals = [], []
                for k in ("amount_raw", "amount_value", "winner", "deadline",
                          "content", "url", "uuid", "snapshot_path", "region", "notice_type",
                          "relevance", "relevance_reason", "build_content"):
                    newv = r.get(k)
                    if newv not in (None, "", 0) and old[k] in (None, "", 0):
                        fields.append(f"{k}=?")
                        vals.append(newv)
                fields.append("last_seen=?")
                vals.append(ts)
                fields.append("status='active'")
                vals.append(bid)
                c.execute(f"UPDATE bids SET {','.join(fields)} WHERE id=?", vals)
                upd += 1
            else:
                c.execute(
                    """INSERT INTO bids(id,title,content,notice_type,publish_date,deadline,
                       amount_raw,amount_value,winner,operator,region,source,url,uuid,
                       snapshot_path,first_seen,last_seen,status,relevance,relevance_reason,build_content)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'active',?,?,?)""",
                    (bid, r.get("title"), r.get("content"), r.get("notice_type"),
                     r.get("publish_date"), r.get("deadline"), r.get("amount_raw"),
                     r.get("amount_value"), r.get("winner"), r.get("operator"),
                     r.get("region"), r.get("source"), r.get("url"), r.get("uuid"),
                     r.get("snapshot_path"), ts, ts,
                     r.get("relevance"), r.get("relevance_reason"), r.get("build_content")))
                ins += 1
    return ins, upd


def mark_stale(operator, seen_ids, min_date=""):
    """本轮没见到的记录：标记下架存档，但绝不删除。

    min_date = 本轮翻页翻到的最早发布日期。
    列表按发布日期倒序，比 min_date 更早的记录只是"还没翻到"，不代表下线，
    因此只把发布日期 >= min_date 却缺席的记录判定为已下架，避免误标。
    """
    if not seen_ids:
        return 0
    init()
    ph = ",".join("?" * len(seen_ids))
    sql = ("UPDATE bids SET status='archived' "
           f"WHERE operator=? AND status='active' AND id NOT IN ({ph})")
    params = [operator, *seen_ids]
    if min_date:
        sql += " AND publish_date >= ?"
        params.append(min_date)
    else:
        sql += " AND (publish_date IS NULL OR publish_date='')"
    with conn() as c:
        cur = c.execute(sql, params)
        return cur.rowcount


def query(op=None, kw=None, status=None, days=None, limit=500):
    init()
    sql = "SELECT * FROM bids WHERE 1=1"
    p = []
    if op and op != "all":
        sql += " AND operator=?"
        p.append(op)
    if status and status != "all":
        sql += " AND status=?"
        p.append(status)
    if kw:
        sql += " AND (title LIKE ? OR content LIKE ? OR region LIKE ? OR winner LIKE ?)"
        p += [f"%{kw}%"] * 4
    if days:
        sql += " AND publish_date >= date('now', ?)"
        p.append(f"-{int(days)} day")
    sql += " ORDER BY publish_date DESC LIMIT ?"
    p.append(int(limit))
    with conn() as c:
        return [dict(r) for r in c.execute(sql, p)]


def stats():
    init()
    with conn() as c:
        def one(q, *a):
            r = c.execute(q, a).fetchone()
            return r[0] if r else 0
        return {
            "total": one("SELECT COUNT(*) FROM bids"),
            "active": one("SELECT COUNT(*) FROM bids WHERE status='active'"),
            "archived": one("SELECT COUNT(*) FROM bids WHERE status='archived'"),
            "with_amount": one("SELECT COUNT(*) FROM bids WHERE amount_value IS NOT NULL AND amount_value>0"),
            "with_winner": one("SELECT COUNT(*) FROM bids WHERE winner IS NOT NULL AND winner<>''"),
            "cmcc": one("SELECT COUNT(*) FROM bids WHERE operator='中国移动'"),
            "ct": one("SELECT COUNT(*) FROM bids WHERE operator='中国电信'"),
            "cu": one("SELECT COUNT(*) FROM bids WHERE operator='中国联通'"),
            "last_run": one("SELECT finished FROM runs ORDER BY id DESC LIMIT 1") or "",
        }


def log_run(operator, fetched, ins, upd, errors):
    init()
    with conn() as c:
        c.execute("INSERT INTO runs(operator,fetched,inserted,updated,errors,started,finished) VALUES(?,?,?,?,?,?,?)",
                  (operator, fetched, ins, upd, errors, now(), now()))


if __name__ == "__main__":
    init()
    print("DB initialized:", DB)
    print(json.dumps(stats(), ensure_ascii=False, indent=2))
