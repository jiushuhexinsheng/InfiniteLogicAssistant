# -*- coding: utf-8 -*-
"""配置运行时 — 全局单例 + 热重载 + profile 解析 + 设置快照

兼容层：resolve_llm_profile()/resolve_asr_profile()/resolve_tts_profile() 仍返回 (name, dict)，
is_*_configured / is_tts_enabled / ensure_dirs 保留；settings 属性由包 __init__ 的 __getattr__ 代理到 get_settings()。

单例状态 _settings / _reload_hooks 的读写统一经包命名空间 `core.config.X`，
使测试 monkeypatch.setattr(core.config, "_settings", None) 重置对内部调用也生效。
"""
from core.config.constants import ROOT_DIR
from core.config.loader import _build
from core.config.schema import Settings

_settings: Settings | None = None
_reload_hooks: list = []


def _get_settings() -> Settings:
    """经包命名空间取当前单例（get_settings 可被 monkeypatch 替换以隔离真实配置）。"""
    from core import config as _cfg
    return _cfg.get_settings()


def add_reload_hook(fn) -> None:
    """注册配置热重载后的回调（如重建 ASR/TTS 客户端等持有旧 profile 的单例）。"""
    from core import config as _cfg
    _cfg._reload_hooks.append(fn)


def get_settings() -> Settings:
    from core import config as _cfg
    if _cfg._settings is None:
        _cfg._settings = _build()
    return _cfg._settings


def reload_settings() -> Settings:
    """重新加载配置（PATCH /api/config 后调用；per-request 读取立即生效）。"""
    from core import config as _cfg
    _cfg._settings = _build()
    for fn in list(_cfg._reload_hooks):
        try:
            fn()
        except Exception:
            pass
    return _cfg._settings


# ─────────────────────────── profile 解析（兼容返回 (name, dict)） ───────────────────────────


def resolve_llm_profile() -> tuple[str, dict]:
    return _resolve_profile("llm", "deepseek")


def resolve_asr_profile() -> tuple[str, dict]:
    return _resolve_profile("asr", "openai")


def resolve_tts_profile() -> tuple[str, dict]:
    return _resolve_profile("tts", "openai")


def _resolve_profile(section: str, active_default: str) -> tuple[str, dict]:
    s = getattr(_get_settings().voice if section in ("asr", "tts") else _get_settings(), section)
    profiles = s.profiles
    if not profiles:
        return "", {}
    active = s.active or active_default
    if active not in profiles:
        active = next(iter(profiles))
        print(f"[WARN] {section}.active='{s.active}' 在 profiles 中不存在，已回退到 '{active}'")
    return active, profiles[active].model_dump()


def is_llm_configured() -> bool:
    _, p = resolve_llm_profile()
    return bool(p.get("endpoint") and p.get("model"))


def is_asr_configured() -> bool:
    _, p = resolve_asr_profile()
    return bool(p.get("endpoint") and p.get("model"))


def is_tts_enabled() -> bool:
    if not _get_settings().voice.tts.enabled:
        return False
    _, p = resolve_tts_profile()
    return bool(p.get("endpoint"))


# ─────────────────────────── 设置快照 / 目录 ───────────────────────────


def editable_snapshot() -> dict:
    """设置页可编辑快照：不含任何密钥值，密钥只以 *_set 布尔暴露。"""
    s = _get_settings()

    def _profiles(section) -> dict:
        return {
            name: {k: v for k, v in p.model_dump().items() if k != "api_key"}
            for name, p in section.profiles.items()
        }

    def _key_set(section) -> dict:
        return {name: bool(p.api_key) for name, p in section.profiles.items()}

    return {
        "llm": {"active": s.llm.active, "profiles": _profiles(s.llm),
                "api_key_set": _key_set(s.llm)},
        "asr": {"active": s.voice.asr.active, "profiles": _profiles(s.voice.asr),
                "api_key_set": _key_set(s.voice.asr)},
        "tts": {"enabled": s.voice.tts.enabled, "active": s.voice.tts.active,
                "profiles": _profiles(s.voice.tts), "api_key_set": _key_set(s.voice.tts)},
        "wake_word": s.voice.wake_word.model_dump(),
        "vad": s.voice.vad.model_dump(),
        "agent": s.agent.model_dump(),
        "llm_client": s.llm_client.model_dump(),
        "tools": s.tools.model_dump(),
        "mcp": {"servers": [m.model_dump() for m in s.mcp.servers]},
        "rag": s.rag.model_dump(),
        "server": {
            "host": s.server.host, "port": s.server.port, "open_browser": s.server.open_browser,
            "cors_origins": s.server.cors_origins, "api_token_set": bool(s.server.api_token),
        },
    }


def ensure_dirs():
    (ROOT_DIR / "data").mkdir(exist_ok=True)
