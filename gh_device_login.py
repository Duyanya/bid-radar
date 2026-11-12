"""GitHub device flow，自己控制轮询（不依赖 gh 的交互式 TTY）。

用法：python gh_device_login.py
输出写到 %TEMP%\\bidradar_gh_login.log：只有状态和 user_code，绝不含 token。
成功后把 token 直接喂给 `gh auth login --with-token`（经 stdin，不落盘、不进聊天）。
"""
import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

PROXY = "http://127.0.0.1:7897"
CLIENT_ID = "178c6fc778ccc68e1d6a"  # gh CLI 的公开 client id
LOG = Path(os.environ.get("TEMP", ".")) / "bidradar_gh_login.log"
GH = str(Path.home() / "Downloads/gh_tmp/bin/gh.exe")

opener = urllib.request.build_opener(
    urllib.request.ProxyHandler({"http": PROXY, "https": PROXY})
)


def log(msg: str) -> None:
    with LOG.open("a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%H:%M:%S')} {msg}\n")


def post(url: str, data: dict):
    req = urllib.request.Request(
        url,
        data=urllib.parse.urlencode(data).encode(),
        headers={"Accept": "application/json", "User-Agent": "bidradar-login"},
    )
    try:
        with opener.open(req, timeout=25) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return {"_http": e.code, "_body": e.read().decode()[:200]}


def main() -> int:
    LOG.write_text("", encoding="utf-8")
    d = post("https://github.com/login/device/code",
             {"client_id": CLIENT_ID, "scope": "repo workflow read:org gist"})
    if "user_code" not in d:
        log(f"ERROR 取码失败: {d}")
        return 1
    log(f"CODE {d['user_code']}")
    log(f"URL  {d['verification_uri']}")
    interval = int(d.get("interval", 5))
    deadline = time.time() + int(d.get("expires_in", 900))
    log("WAIT 等你在浏览器里输入代码并授权…")

    while time.time() < deadline:
        time.sleep(interval)
        r = post("https://github.com/login/oauth/access_token", {
            "client_id": CLIENT_ID,
            "device_code": d["device_code"],
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        })
        err = r.get("error")
        if err == "authorization_pending":
            continue
        if err == "slow_down":
            interval += 5
            continue
        if err:
            log(f"FAIL {err} {r.get('error_description', '')}")
            return 1
        token = r.get("access_token")
        if not token:
            log(f"FAIL 无 token: {r}")
            return 1
        log("TOKEN 拿到，正在写入 gh 配置")
        p = subprocess.run([GH, "auth", "login", "--hostname", "github.com", "--with-token"],
                           input=token + "\n", capture_output=True, text=True)
        if p.returncode != 0:
            log(f"FAIL gh 写入失败 {p.stderr.strip()[:160]}")
            return 1
        env = {**os.environ, "HTTPS_PROXY": PROXY, "HTTP_PROXY": PROXY}
        q = subprocess.run([GH, "api", "user", "-q", ".login"], capture_output=True, text=True, env=env)
        log(f"OK 登录成功 user={q.stdout.strip() or '?'}")
        subprocess.run([GH, "auth", "setup-git", "--hostname", "github.com"], capture_output=True, text=True, env=env)
        return 0

    log("FAIL 超时（15 分钟内没有完成授权）")
    return 1


if __name__ == "__main__":
    sys.exit(main())
