"""后台启动器：端口已占用则跳过，否则拉起 app.py（无窗口）。"""
import os
import socket
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
PYTHONW = Path(sys.executable).with_name("pythonw.exe")
PORT = 8848


def port_busy():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1.0)
        return s.connect_ex(("127.0.0.1", PORT)) == 0


def main():
    if port_busy():
        return 0
    exe = str(PYTHONW) if PYTHONW.exists() else sys.executable
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
    log = BASE / "data" / "service.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    with open(log, "a", encoding="utf-8") as f:
        subprocess.Popen(
            [exe, str(BASE / "app.py")],
            cwd=str(BASE),
            env=env,
            stdout=f,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            close_fds=True,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
