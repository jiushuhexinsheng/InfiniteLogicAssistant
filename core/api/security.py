# -*- coding: utf-8 -*-
"""HTTP / WebSocket 来源校验：Host、Origin、回环客户端与恒定时间 token 比较。

Origin/Host guards for HTTP and WebSocket requests, plus constant-time token
comparison.

浏览器侧的本地服务有两个现实攻击面：

- **DNS rebinding**：恶意页面把域名解析到 127.0.0.1，用合法 URL 访问本机服务；
  仅靠绑定地址挡不住，必须校验 `Host`。
- **跨站请求**：CORS 只限制“读响应”，不阻止简单请求“发出去”；因此状态变更
  请求还要求 `application/json`（表单无法伪造该 Content-Type），并校验 `Origin`。

Two real attack surfaces for a local browser service:

- **DNS rebinding**: a malicious page resolves its own domain to 127.0.0.1 and talks
  to the local service through a legitimate URL; only a `Host` check stops it.
- **Cross-site requests**: CORS restricts reading responses, not sending simple
  requests. State-changing requests therefore require `application/json` (forms
  cannot forge that Content-Type) and an allowed `Origin`.

The token comparison is constant-time to avoid leaking length/prefix timing.
"""
from __future__ import annotations

import hmac
from urllib.parse import urlsplit

from core import config

# 本地回环与测试客户端（TestClient 的 client.host / Host 头）。
# Loopback hosts plus the ASGI test client (TestClient's client.host / Host header).
LOOPBACK_HOSTS = frozenset({"", "127.0.0.1", "localhost", "::1", "testserver", "testclient"})


def host_only(raw: str) -> str:
    """取 Host/来源的纯主机名（去端口与 IPv6 方括号）。Extract the bare host name."""
    value = (raw or "").strip().lower()
    if value.startswith("["):
        end = value.find("]")
        return value[1:end] if end > 0 else value
    if ":" in value:
        return value.rsplit(":", 1)[0]
    return value


def allowed_hosts() -> set[str]:
    """允许的 Host/Origin 主机集合：回环 + 绑定地址 + 显式 CORS 来源。

    Allowed Host/Origin hosts: loopback + the configured bind host + explicit CORS
    origins.
    """
    hosts = set(LOOPBACK_HOSTS)
    host = host_only(config.settings.server.host)
    if host:
        hosts.add(host)
    for origin in config.settings.server.cors_origins:
        try:
            parsed = urlsplit(origin).hostname
        except ValueError:
            parsed = None
        if parsed:
            hosts.add(parsed.lower())
    return hosts


def origin_allowed(origin: str) -> bool:
    """Origin 是否可信：缺省（非浏览器/同源 GET）放行，`null` 与未知主机拒绝。

    Whether an Origin is trusted: absent (non-browser / same-origin GET) is allowed;
    `null` and unknown hosts are rejected.
    """
    if not origin:
        return True
    try:
        host = urlsplit(origin).hostname
    except ValueError:
        return False
    if not host:
        return False
    return host.lower() in allowed_hosts()


def is_loopback_host(host: str) -> bool:
    """客户端地址是否为本机回环/测试客户端。Whether the peer is loopback/test."""
    return host_only(host) in LOOPBACK_HOSTS


def token_matches(supplied: str, expected: str) -> bool:
    """恒定时间比较 API token（长度差异也不提前返回）。Constant-time token check."""
    return bool(expected) and hmac.compare_digest(supplied or "", expected)
