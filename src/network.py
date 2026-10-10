# -*- coding: utf-8 -*-
"""
network.py —— 网络检测与 WiFi 连接模块
========================================
- is_authenticated(): 判断当前是否已通过校园网认证（能否正常访问外网）；
- get_current_ssid(): 获取当前连接的 WiFi 名称（Windows）；
- connect_wifi():     尝试连接到指定 WiFi（需已保存过该网络的密码）；
- can_reach_portal(): 判断认证门户是否可达（避免在非校园网环境误触发 Edge）。
"""
import socket
import subprocess
import time
from urllib.parse import urlsplit

import requests

# 模拟浏览器 UA，避免部分门户拦截脚本默认 UA
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0"
    )
}


def _decode(data):
    """兼容 UTF-8 和 Windows 当前代码页的子进程输出。"""
    for enc in ("utf-8", "mbcs", "gbk", "latin-1"):
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, AttributeError):
            continue
    return str(data)


def _run(cmd, timeout=10):
    """执行命令并返回 CompletedProcess，失败返回 None。"""
    try:
        return subprocess.run(cmd, capture_output=True, timeout=timeout,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        return None


def get_current_ssid():
    """获取当前连接的 WiFi SSID；无无线连接或失败时返回 None。"""
    result = _run(["netsh", "wlan", "show", "interfaces"], timeout=10)
    if result is None or result.returncode != 0:
        return None
    out = _decode(result.stdout)
    for line in out.splitlines():
        # 输出形如 "    SSID : JXUAS"（中英文环境均是 "SSID : 名称"）
        key, separator, value = line.partition(":")
        if separator and key.strip() == "SSID":
            return value.strip() or None
    return None


def connect_wifi(ssid, backup=None, timeout=15):
    """
    尝试连接主 SSID，失败则尝试备用 SSID。
    注意：Windows 只能连接「已保存过密码」的无线网络，请先手动连过一次。
    """
    current = get_current_ssid()
    candidates = list(dict.fromkeys(name for name in (ssid, backup) if name))
    for name in candidates:
        if name and current == name:
            return True
    for name in candidates:
        result = _run(["netsh", "wlan", "connect", "name=%s" % name], timeout=15)
        if result is not None and result.returncode == 0:
            # 命令成功仅代表请求被接受；实际连接成功后才返回。
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                if get_current_ssid() == name:
                    return True
                time.sleep(min(0.5, max(0, deadline - time.monotonic())))
    return False


def is_authenticated(test_url):
    """
    判断是否已通过认证：能正常访问外网则视为已认证。
    未认证时，门户通常阻断/重定向对外访问，requests 会抛异常或返回非 200，
    据此判定为「未认证 / 未联网」。
    """
    try:
        resp = requests.get(
            test_url, timeout=6, headers=HEADERS, allow_redirects=False
        )
        if resp.status_code == 200:
            return True
        # 被重定向到内网门户地址，说明未认证
        location = resp.headers.get("Location", "")
        if "172.16" in location or "portal" in location.lower():
            return False
        return False
    except requests.RequestException:
        # 超时 / 连接被拒 / SSL 被门户拦截等，均视为未认证或未联网
        return False


def can_reach_portal(portal_url):
    """按 URL 的协议和显式端口探测门户，支持 HTTPS 和 IPv6。"""
    try:
        parsed = urlsplit(portal_url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            return False
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        with socket.create_connection((parsed.hostname, port), timeout=4):
            pass
        return True
    except (OSError, ValueError):
        return False
