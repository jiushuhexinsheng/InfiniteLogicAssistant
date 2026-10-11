# -*- coding: utf-8 -*-
"""模型 profile 工具 — 协议分派 / 模型列表路径推导 / 对外输出剥密钥（无内置目录）

2026-10-11 起厂商目录（BUILTIN_* 预设与 config.yaml vendor_presets）整体退役：
LLM/ASR/TTS 全部改为用户自填 profile，本模块只保留与目录正交的三个纯函数。
- provider 是协议（openai / anthropic / gemini），分派只发生在 LLM 层；
  TTS/ASR 维持各自 chat_path 推断。
- endpoint 为基座 URL（不含 /v1，与 chat_path 配对），避免拼出 /v1/v1/ 错误地址。

Model profile utilities — protocol dispatch / models-list path inference / secret-stripping
for external output (no built-in catalogue).

As of 2026-10-11 the vendor catalogue (BUILTIN_* presets and config.yaml vendor_presets)
is retired entirely: LLM/ASR/TTS are all user-filled profiles, and this module keeps only
the three catalogue-independent helpers.
"""
from typing import Any

_KNOWN_PROTOCOLS = ("openai", "anthropic", "gemini")


def resolve_protocol(profile: dict) -> str:
    """LLM 协议分派：provider 命中 → chat_path 推断 → 默认 openai。

    仅 LLM 层调用；TTS/ASR 不依赖此函数（维持各自 chat_path 推断）。

    LLM protocol dispatch: ``provider`` match → ``chat_path`` inference → default
    ``openai``. Called only by the LLM layer; TTS/ASR rely on their own chat_path
    inference.
    """
    p = (profile.get("provider") or "").strip()
    if p in _KNOWN_PROTOCOLS:
        return p
    path = (profile.get("chat_path") or "").lower()
    if "v1/messages" in path:
        return "anthropic"
    if "generatecontent" in path:
        return "gemini"
    return "openai"


def models_path_for(profile: dict) -> str:
    """获取模型列表路径：显式 models_path 优先，否则从 chat_path 推导。

    Resolve the models-list endpoint: explicit ``models_path`` takes priority,
    otherwise inferred from ``chat_path``.
    """
    mp = (profile.get("models_path") or "").strip()
    if mp:
        return mp
    path = profile.get("chat_path") or "/v1/chat/completions"
    if "generatecontent" in path.lower():
        return "/v1beta/models"
    # /v1/chat/completions → /v1/models；/chat/completions → /models
    if path.endswith("/chat/completions"):
        return path[: -len("/chat/completions")] + "/models"
    base = path.rsplit("/", 1)[0] if "/" in path else ""
    return f"{base}/models"


# ─────────────────────────── 公开输出（剥密钥） ───────────────────────────

_SECRET_KEYS = ("api_key", "api_token")


def to_public_dict(d: dict) -> dict:
    """递归剥除 api_key / api_token，用于对外输出。

    Recursively strip ``api_key`` / ``api_token`` from a dict, for safe external
    output.
    """
    out: dict = {}
    for k, v in d.items():
        if k in _SECRET_KEYS:
            continue
        if isinstance(v, dict):
            out[k] = to_public_dict(v)
        elif isinstance(v, list):
            out[k] = [_to_public_item(i) for i in v]
        else:
            out[k] = v
    return out


def _to_public_item(item: Any) -> Any:
    """递归处理列表中的元素（剥除敏感字段）。

    Process list items recursively (strip sensitive fields).
    """
    if isinstance(item, dict):
        return to_public_dict(item)
    if isinstance(item, list):
        return [_to_public_item(i) for i in item]
    return item
