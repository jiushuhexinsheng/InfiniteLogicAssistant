# -*- coding: utf-8 -*-
"""配置运行时 — 全局单例 + 热重载 + profile 解析 + 设置快照

Configuration runtime — global singleton + hot reload + profile resolution + settings snapshot.

兼容层：resolve_llm_profile()/resolve_asr_profile()/resolve_tts_profile() 仍返回 (name, dict)，
is_*_configured / is_tts_enabled / ensure_dirs 保留；settings 属性由包 __init__ 的 __getattr__ 代理到 get_settings()。

Compatibility layer: resolve_llm_profile()/resolve_asr_profile()/resolve_tts_profile() still return
(name, dict); is_*_configured / is_tts_enabled / ensure_dirs are kept; the settings attribute is
proxied to get_settings() via __getattr__ in the package __init__.

单例状态 _settings / _reload_hooks 的读写统一经包命名空间 `core.config.X`，
使测试 monkeypatch.setattr(core.config, "_settings", None) 重置对内部调用也生效。

Singleton state _settings / _reload_hooks is read and written through the package namespace
`core.config.X`, so a test can monkeypatch.setattr(core.config, "_settings", None) to reset
and internal calls see the change too.
"""
from core.config.constants import ROOT_DIR
from core.config.loader import _build, _print_notice
from core.config.schema import Settings

_settings: Settings | None = None
# (回调, 作用域段名元组或 None=每次都跑)。(callback, section names or None=always).
_reload_hooks: list[tuple] = []


def _get_settings() -> Settings:
    """经包命名空间取当前单例（get_settings 可被 monkeypatch 替换以隔离真实配置）。

    Get the current singleton through the package namespace (get_settings can be monkeypatched
    to isolate the real configuration).

    Returns:
        当前 Settings 单例。
        The current Settings singleton.
    """
    from core import config as _cfg
    return _cfg.get_settings()


def add_reload_hook(fn, sections: tuple[str, ...] | None = None) -> None:
    """注册配置热重载后的回调（如重建 ASR/TTS 客户端等持有旧 profile 的单例）。

    ``sections`` 为作用域：只有这些顶层配置段发生变化时才执行该回调；``None``
    表示每次重载都执行。语音引擎/子进程池这类昂贵资源应限定在 ``("voice",)``，
    否则改 LLM 或记忆配置也会把本地模型全部卸载重载。

    Register a callback invoked after configuration hot reload (e.g. to rebuild
    singletons such as ASR/TTS clients that hold stale profiles).

    ``sections`` scopes the callback: it runs only when one of those top-level
    config sections changed; ``None`` runs on every reload. Expensive resources such
    as local engines / the TTS child pool should be scoped to ``("voice",)`` so an
    LLM or memory edit does not unload and reload every local model.

    Args:
        fn: 无参回调函数。A zero-argument callback.
        sections: 触发的顶层段名；None = 每次都执行。Triggering top-level sections;
            None = every reload.
    """
    from core import config as _cfg
    _cfg._reload_hooks.append((fn, sections))


def get_settings() -> Settings:
    """返回当前 Settings 单例；首次调用时惰性构建。

    Return the current Settings singleton, building it lazily on first call.

    Returns:
        当前 Settings 单例。
        The current Settings singleton.
    """
    from core import config as _cfg
    if _cfg._settings is None:
        _cfg._settings = _build()
    return _cfg._settings


def _changed_sections(old: Settings | None, new: Settings) -> set[str] | None:
    """比较新旧配置的顶层段，返回变化的段名集合（首次构建返回 None = 全部）。

    Compare the top-level sections of the old and new settings; return the changed
    names (None on first build, meaning "everything").

    Args:
        old: 旧配置（可能为 None）。Old settings (may be None).
        new: 新配置。New settings.

    Returns:
        变化的顶层段名；None 表示无从比较。Changed section names; None when unknown.
    """
    if old is None:
        return None
    before, after = old.model_dump(), new.model_dump()
    keys = set(before) | set(after)
    return {k for k in keys if before.get(k) != after.get(k)}


def reload_settings(source: str = "") -> Settings:
    """重新加载配置（PATCH /api/config / PUT /api/config/secrets 后调用）。

    钩子按作用域触发：只有声明过的顶层段发生变化才执行；不声明的钩子每次都跑。
    日志记录来源与变更段，便于回答「谁把本地引擎打掉了」。

    Reload the configuration (called after PATCH /api/config or PUT
    /api/config/secrets). Hooks are section-scoped: a scoped hook runs only when one
    of its sections changed; unscoped hooks run every time. The log line records the
    source and changed sections so "who unloaded the local engines?" is answerable.

    Args:
        source: 触发来源（如 ``api.config`` / ``api.secrets``），仅用于日志。
            Trigger source (e.g. ``api.config`` / ``api.secrets``), for logging only.

    Returns:
        重新加载后的 Settings 单例。The reloaded Settings singleton.
    """
    from core import config as _cfg
    old = _cfg._settings
    new = _build()
    changed = _changed_sections(old, new)
    _cfg._settings = new
    try:
        from core.logger import logger
        logger.info("配置热重载：来源={} 变更段={}",
                    source or "unknown",
                    sorted(changed) if changed is not None else "全部")
    except Exception:  # noqa: BLE001 - 日志失败绝不能挡住重载。Logging must never block reload.
        pass
    for fn, sections in list(_cfg._reload_hooks):
        if sections is not None and changed is not None and not (set(sections) & changed):
            continue
        try:
            fn()
        except Exception:
            pass
    return _cfg._settings


# ─────────────────────────── profile 解析（兼容返回 (name, dict)） ───────────────────────────


def resolve_llm_profile() -> tuple[str, dict]:
    """解析当前激活的 LLM profile，返回 (name, dict)。

    Resolve the currently active LLM profile and return (name, dict).

    Returns:
        (profile 名称, profile 配置字典)；无可用 profile 时返回 ("", {})。
        (profile name, profile config dict); ("", {}) when no profile is available.
    """
    return _resolve_profile("llm")


def resolve_asr_profile() -> tuple[str, dict]:
    """解析当前激活的 ASR profile，返回 (name, dict)。

    Resolve the currently active ASR profile and return (name, dict).

    Returns:
        (profile 名称, profile 配置字典)；无可用 profile 时返回 ("", {})。
        (profile name, profile config dict); ("", {}) when no profile is available.
    """
    return _resolve_profile("asr")


def resolve_tts_profile() -> tuple[str, dict]:
    """解析当前激活的 TTS profile，返回 (name, dict)。

    Resolve the currently active TTS profile and return (name, dict).

    Returns:
        (profile 名称, profile 配置字典)；无可用 profile 时返回 ("", {})。
        (profile name, profile config dict); ("", {}) when no profile is available.
    """
    return _resolve_profile("tts")


def _resolve_profile(section: str) -> tuple[str, dict]:
    """按段名解析当前激活的 profile（asr/tts 从 voice 段下取）。

    Resolve the active profile for a section (asr/tts live under the voice section).

    active 为空（目录退役后无内置默认名）→ 静默取第一个；active 有值但对不上 →
    告警回退第一个（2026-10-11 起 active 不再有 deepseek/openai 之类目录默认名）。

    Empty ``active`` (no built-in default name since the catalogue retired) silently
    takes the first profile; a set-but-unknown ``active`` warns then falls back.

    Args:
        section: 段名（llm / asr / tts）。
            Section name (llm / asr / tts).

    Returns:
        (profile 名称, profile 配置字典)；无可用 profile 时返回 ("", {})。
        (profile name, profile config dict); ("", {}) when no profile is available.
    """
    s = getattr(_get_settings().voice if section in ("asr", "tts") else _get_settings(), section)
    profiles = s.profiles
    if not profiles:
        return "", {}
    active = s.active
    if not active:
        active = next(iter(profiles))
    elif active not in profiles:
        active = next(iter(profiles))
        _print_notice(f"[WARN] {section}.active='{s.active}' 在 profiles 中不存在，已回退到 '{active}'")
    return active, profiles[active].model_dump()


def is_llm_configured() -> bool:
    """检查 LLM 是否已配置（endpoint 与 model 均非空）。

    Check whether the LLM is configured (both endpoint and model are non-empty).

    Returns:
        已配置返回 True，否则 False。
        True if configured, False otherwise.
    """
    _, p = resolve_llm_profile()
    return bool(p.get("endpoint") and p.get("model"))


def is_asr_configured() -> bool:
    """检查 ASR 是否已配置（endpoint 与 model 均非空）。

    Check whether the ASR is configured (both endpoint and model are non-empty).

    Returns:
        已配置返回 True，否则 False。
        True if configured, False otherwise.
    """
    _, p = resolve_asr_profile()
    return bool(p.get("endpoint") and p.get("model"))


def is_tts_enabled() -> bool:
    """检查 TTS 是否启用（voice.tts.enabled 为 True 且 endpoint 非空）。

    Check whether TTS is enabled (voice.tts.enabled is True and endpoint is non-empty).

    Returns:
        启用返回 True，否则 False。
        True if enabled, False otherwise.
    """
    if not _get_settings().voice.tts.enabled:
        return False
    _, p = resolve_tts_profile()
    return bool(p.get("endpoint"))


# ─────────────────────────── 设置快照 / 目录 ───────────────────────────


def editable_snapshot() -> dict:
    """设置页可编辑快照：不含任何密钥值，密钥只以 *_set 布尔暴露。

    Editable snapshot for the settings page: contains no secret values; secrets are only
    exposed as *_set booleans.

    Returns:
        可编辑配置快照字典。
        The editable configuration snapshot dict.
    """
    s = _get_settings()

    def _profiles(section) -> dict:
        return {
            name: {k: v for k, v in p.model_dump().items() if k != "api_key"}
            for name, p in section.profiles.items()
        }

    def _key_set(section) -> dict:
        return {name: bool(p.api_key) for name, p in section.profiles.items()}

    def _local_model_present() -> bool:
        # 延迟 import；registry 只做文件系统校验，不加载模型。
        # Lazy import; registry validates the filesystem only and never loads a model.
        from core.voice.local.sherpa_onnx import registry
        return registry.present("asr", s.voice.asr.local_model)

    return {
        "llm": {"active": s.llm.active, "profiles": _profiles(s.llm),
                "api_key_set": _key_set(s.llm)},
        "asr": {"active": s.voice.asr.active, "profiles": _profiles(s.voice.asr),
                "api_key_set": _key_set(s.voice.asr),
                # 三模式（2026-10-12）：mode/local_model 可编辑；local_model_present 是
                # 只读展示（纯文件系统判断，不加载模型），前端不得回送。
                "mode": s.voice.asr.mode, "local_model": s.voice.asr.local_model,
                "streaming": s.voice.asr.streaming,
                "provider": s.voice.asr.provider, "device": s.voice.asr.device,
                "num_threads": s.voice.asr.num_threads, "params": s.voice.asr.params,
                "local_model_present": _local_model_present()},
        "tts": {"enabled": s.voice.tts.enabled, "active": s.voice.tts.active,
                "profiles": _profiles(s.voice.tts), "api_key_set": _key_set(s.voice.tts),
                "mode": s.voice.tts.mode, "local_model": s.voice.tts.local_model,
                "provider": s.voice.tts.provider, "device": s.voice.tts.device,
                "num_threads": s.voice.tts.num_threads,
                "speaker": s.voice.tts.speaker, "speed": s.voice.tts.speed,
                "lang": s.voice.tts.lang, "params": s.voice.tts.params},
        "wake_word": s.voice.wake_word.model_dump(),
        "vad": s.voice.vad.model_dump(),
        "kws": s.voice.kws.model_dump(),
        "streaming": s.voice.streaming.model_dump(),
        "hardware": s.voice.hardware.model_dump(),
        "agent": s.agent.model_dump(),
        "llm_client": s.llm_client.model_dump(),
        "tools": s.tools.model_dump(),
        "permissions": s.permissions.model_dump(),
        "mcp": {"servers": [m.model_dump() for m in s.mcp.servers]},
        "rag": s.rag.model_dump(),
        "memory": s.memory.model_dump(),
        "server": {
            "host": s.server.host, "port": s.server.port, "open_browser": s.server.open_browser,
            "cors_origins": s.server.cors_origins, "api_token_set": bool(s.server.api_token),
        },
    }


def ensure_dirs():
    """确保运行时所需目录存在（当前仅 data 目录）。

    Ensure runtime-required directories exist (currently just the data directory).
    """
    (ROOT_DIR / "data").mkdir(exist_ok=True)
