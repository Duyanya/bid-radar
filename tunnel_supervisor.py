"""公网隧道守护：cloudflared 掉线自动重启，并把当前公网地址写到 data/public_url.txt。

- 每 2 秒读一次 cloudflared 日志，抓到 trycloudflare 地址就落盘
- 进程退出（断网/被杀/Cloudflare 侧踢）后 5 秒自动重连
- 地址变化时覆盖 public_url.txt，页面与服务都不受影响
"""
import os
import re
import subprocess
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
CF = BASE / "bin" / "cloudflared.exe"
LOG = BASE / "data" / "tunnel.log"
URLFILE = BASE / "data" / "public_url.txt"
TARGET = "http://127.0.0.1:8848"
URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")


def spawn():
    LOG.parent.mkdir(parents=True, exist_ok=True)
    fh = open(LOG, "w", encoding="utf-8", errors="replace")
    proc = subprocess.Popen(
        [str(CF), "tunnel", "--url", TARGET, "--no-autoupdate", "--protocol", "http2"],
        cwd=str(BASE / "bin"),
        stdout=fh,
        stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        close_fds=True,
    )
    return proc, fh


def note(msg):
    try:
        with open(BASE / "data" / "tunnel_status.log", "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")
    except OSError:
        pass


def main():
    while True:
        if not CF.exists():
            note(f"missing binary {CF}")
            time.sleep(60)
            continue
        proc, fh = spawn()
        note(f"started pid={proc.pid}")
        url = None
        deadline = time.time() + 120
        while time.time() < deadline:
            time.sleep(2)
            if proc.poll() is not None:
                break
            try:
                txt = LOG.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            m = URL_RE.search(txt)
            if m:
                url = m.group(0)
                old = URLFILE.read_text(encoding="utf-8").strip() if URLFILE.exists() else ""
                if old != url:
                    URLFILE.write_text(url, encoding="utf-8")
                    note(f"url {url}")
                break
        if proc.poll() is None:
            proc.wait()
        try:
            fh.close()
        except OSError:
            pass
        note(f"exited code={proc.returncode}, restarting in 5s")
        time.sleep(5)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
