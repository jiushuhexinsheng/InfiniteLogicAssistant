# -*- coding: utf-8 -*-
"""core/model_compat.py — 协议分派 / 模型路径 / 剥密钥（厂商目录已退役）。

Protocol dispatch / model paths / secret stripping (the vendor catalogue retired 2026-10-11).
"""
from core.model_compat import models_path_for, resolve_protocol, to_public_dict


def test_resolve_protocol():
    """协议按 provider / chat_path 正确分派（目录反查已随目录删除）。
    The protocol resolves from provider / chat_path (the catalogue lookup went away with the
    catalogue)."""
    assert resolve_protocol({"provider": "openai"}) == "openai"
    assert resolve_protocol({"provider": "anthropic"}) == "anthropic"
    assert resolve_protocol({"provider": "gemini"}) == "gemini"
    assert resolve_protocol({"provider": "xiaomi", "chat_path": "/v1/chat/completions"}) == "openai"  # 未知→openai
    assert resolve_protocol({"provider": "custom", "chat_path": "/v1/messages"}) == "anthropic"        # chat_path 推断
    assert resolve_protocol({"provider": "custom", "chat_path": "/v1beta/models/m:streamGenerateContent?alt=sse"}) == "gemini"
    assert resolve_protocol({}) == "openai"   # 空 profile 默认 openai


def test_models_path_for():
    """模型路径按 chat_path 推断或直接取用。The models path is inferred from chat_path or taken as given."""
    assert models_path_for({"chat_path": "/v1/chat/completions"}) == "/v1/models"
    assert models_path_for({"chat_path": "/chat/completions"}) == "/models"
    assert models_path_for({"models_path": "/v1beta/models"}) == "/v1beta/models"
    assert models_path_for({"chat_path": "/v1beta/models/m:streamGenerateContent?alt=sse"}) == "/v1beta/models"


def test_to_public_dict_strips_secrets():
    """公开字典递归剥除密钥字段。The public dict recursively strips secret fields."""
    out = to_public_dict({"a": 1, "api_key": "x", "api_token": "y", "nested": {"api_key": "z"}, "list": [{"api_token": "w"}]})
    assert out["a"] == 1
    assert "api_key" not in out and "api_token" not in out
    assert out["nested"] == {}
    assert out["list"] == [{}]


def test_no_builtin_catalogue_module():
    """目录模块必须已不存在（防止回归）。The catalogue module must stay gone (regression guard)."""
    import importlib.util

    assert importlib.util.find_spec("core.vendors") is None
