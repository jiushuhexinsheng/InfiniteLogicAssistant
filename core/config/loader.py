# -*- coding: utf-8 -*-
"""配置加载 — YAML 读取 + 密钥注入 + 构建 Settings（纯函数，无全局状态）

Configuration loading — YAML reading + secret injection + building Settings (pure functions, no global state).

配置源（优先级从低到高）：
1. pydantic 模型默认值（Field 约束 / Literal 枚举，写错配置启动即报错）
2. config.yaml            —— 非敏感结构（llm/voice/server/mcp/rag/agent/llm_client/tools），不含任何密钥
3. config.secrets.yaml    —— 密钥独立存储（gitignored，仅提交 example 模板）
4. 环境变量               —— LLM_API_KEY / ASR_API_KEY / TTS_API_KEY / SERVER_API_TOKEN 覆盖密钥

Configuration sources (priority low to high):
1. pydantic model defaults (Field constraints / Literal enums; a bad config fails fast at startup)
2. config.yaml            — non-sensitive structure (llm/voice/server/mcp/rag/agent/llm_client/tools), no secrets
3. config.secrets.yaml    — secrets stored separately (gitignored; only the example template is committed)
4. environment variables  — LLM_API_KEY / ASR_API_KEY / TTS_API_KEY / SERVER_API_TOKEN override secrets

文件路径（CONFIG_FILE / SECRETS_FILE 等）统一经包命名空间 `core.config.X` 读取，
使测试 monkeypatch.setattr(core.config, "CONFIG_FILE", tmp) 对内部加载也生效。

File paths (CONFIG_FILE / SECRETS_FILE etc.) are read through the package namespace
`core.config.X`, so tests can monkeypatch.setattr(core.config, "CONFIG_FILE", tmp)
and the change also takes effect for internal loading.
"""
import os
import shutil

import yaml

from core.config.constants import _ENV_KEY_MAP
from core.config.schema import Settings


def _read_yaml(path) -> dict:
    """读取 YAML 文件并返回字典；文件不存在或内容为空时返回空字典。

    Read a YAML file and return it as a dict; return an empty dict when the file
    does not exist or its content is empty.

    Args:
        path: YAML 文件路径。
            Path to the YAML file.

    Returns:
        解析后的字典。
        The parsed dict.
    """
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _resolve_env(value: str) -> str:
    """解析 ${VAR} 占位符（仅用于旧配置迁移：config.yaml 里残留的 api_key 字段）。

    Resolve a ${VAR} placeholder (used only for legacy config migration: leftover api_key
    fields in config.yaml).

    Args:
        value: 可能含 ${VAR} 占位符的原始字符串。
            Raw string that may contain a ${VAR} placeholder.

    Returns:
        解析后的字符串；无占位符时原样返回，环境变量不存在时返回空串。
        The resolved string; returned unchanged when no placeholder is present, or an
        empty string when the referenced environment variable is missing.
    """
    import re

    m = re.fullmatch(r"\$\{(\w+)\}", value.strip())
    return os.environ.get(m.group(1), "") if m else value


def _load_secrets() -> dict:
    """读取 config.secrets.yaml + 环境变量覆盖，返回 {
        'llm': {'api_key': str, 'profiles': {name: key}}, 'asr': ..., 'tts': ..., 'server': {'api_token': str}
    }

    Read config.secrets.yaml plus environment-variable overrides and return {
        'llm': {'api_key': str, 'profiles': {name: key}}, 'asr': ..., 'tts': ..., 'server': {'api_token': str}
    }

    Returns:
        各段 api_key / profiles 与 server.api_token 的汇总字典。
        Aggregated dict of per-section api_key / profiles and server.api_token.
    """
    from core import config as _cfg
    raw = _read_yaml(_cfg.SECRETS_FILE)
    out: dict = {
        "llm": {"api_key": "", "profiles": {}},
        "asr": {"api_key": "", "profiles": {}},
        "tts": {"api_key": "", "profiles": {}},
        "server": {"api_token": ""},
    }
    for sec_key, env_name in _ENV_KEY_MAP.items():
        sec = raw.get(sec_key) if isinstance(raw, dict) else None
        if isinstance(sec, dict):
            out[sec_key]["api_key"] = str(sec.get("api_key") or "")
            profs = sec.get("profiles")
            if isinstance(profs, dict):
                out[sec_key]["profiles"] = {
                    str(k): str(v) for k, v in profs.items() if isinstance(v, str) and v
                }
        # 环境变量最高优先级
        env_val = os.environ.get(env_name, "")
        if env_val:
            out[sec_key]["api_key"] = env_val
    srv = raw.get("server") if isinstance(raw, dict) else None
    if isinstance(srv, dict):
        out["server"]["api_token"] = str(srv.get("api_token") or "")
    out["server"]["api_token"] = out["server"]["api_token"] or os.environ.get("SERVER_API_TOKEN", "")
    return out


def _profile_api_key(section: str, name: str, secrets: dict, profile: dict) -> str:
    """单个 profile 的 api_key 解析优先级：
    profile.api_key_env 指向的 env > 段全局 env > secrets.profiles[name] > secrets 段默认
    > 旧 config.yaml profile.api_key（弃用，仅迁移）

    Resolve one profile's api_key by priority: env pointed to by profile.api_key_env >
    section-wide env > secrets.profiles[name] > section default in secrets > legacy
    config.yaml profile.api_key (deprecated, migration only).

    Args:
        section: 段名（llm / asr / tts）。
            Section name (llm / asr / tts).
        name: profile 名称。
            Profile name.
        secrets: _load_secrets 返回的密钥字典。
            Secrets dict returned by _load_secrets.
        profile: 目标 profile 的配置字典。
            Config dict of the target profile.

    Returns:
        解析出的 api_key；无法解析时返回空串。
        The resolved api_key, or an empty string when nothing can be resolved.
    """
    env_name = (profile.get("api_key_env") or "").strip()
    if env_name and os.environ.get(env_name):
        return os.environ[env_name]
    env_val = os.environ.get(_ENV_KEY_MAP[section], "")
    if env_val:
        return env_val
    sec = secrets[section]
    if name in sec["profiles"]:
        return sec["profiles"][name]
    if sec["api_key"]:
        return sec["api_key"]
    legacy = profile.get("api_key")
    if isinstance(legacy, str) and legacy:
        resolved = _resolve_env(legacy)
        print(f"[WARN] {section}.profiles.{name}.api_key 已在 config.yaml 中配置（旧格式），"
              f"请迁移到 config.secrets.yaml 或环境变量 {_ENV_KEY_MAP[section]}")
        return resolved
    return ""


def _inject_secrets(data: dict, secrets: dict) -> None:
    """把解析好的密钥注入配置字典（llm 在顶层，asr/tts 在 voice 段下）。

    Inject resolved secrets into the config dict (llm at the top level; asr/tts under the
    voice section).

    Args:
        data: 已读取的 config.yaml 字典（会被原地修改）。
            The loaded config.yaml dict (mutated in place).
        secrets: _load_secrets 返回的密钥字典。
            Secrets dict returned by _load_secrets.
    """
    for sec_key in _ENV_KEY_MAP:
        # llm 在顶层；asr/tts 嵌在 voice 段下（config.yaml 结构），都要找到
        section = data.get(sec_key)
        if not isinstance(section, dict):
            voice = data.get("voice")
            section = voice.get(sec_key) if isinstance(voice, dict) else None
        if not isinstance(section, dict):
            continue
        profiles = section.get("profiles")
        if not isinstance(profiles, dict):
            continue
        for name, p in profiles.items():
            if isinstance(p, dict):
                p["api_key"] = _profile_api_key(sec_key, name, secrets, p)
    if isinstance(data.get("server"), dict):
        data["server"]["api_token"] = secrets["server"]["api_token"]


def profile_api_key(section: str, name: str, profile: dict) -> str:
    """对外暴露单个 profile 的密钥解析（fetch-models 等服务端转发用）。

    Public API to resolve one profile's api_key (used by server-side forwarding such as
    fetch-models).

    Args:
        section: 段名（llm / asr / tts）。
            Section name (llm / asr / tts).
        name: profile 名称。
            Profile name.
        profile: 目标 profile 的配置字典。
            Config dict of the target profile.

    Returns:
        解析出的 api_key；无法解析时返回空串。
        The resolved api_key, or an empty string when nothing can be resolved.
    """
    return _profile_api_key(section, name, _load_secrets(), profile)


def _build() -> Settings:
    """构建 Settings：必要时从 example 模板创建配置文件，读取 YAML、注入密钥并校验。

    Build Settings: create config files from example templates when missing, read YAML,
    inject secrets, and validate.

    Returns:
        校验通过后的 Settings 实例。
        The validated Settings instance.

    Raises:
        RuntimeError: 配置校验失败（附带逐条错误信息）。
            RuntimeError: when configuration validation fails (with per-item error details).
    """
    from core import config as _cfg
    if not _cfg.CONFIG_FILE.exists() and _cfg.EXAMPLE_FILE.exists():
        shutil.copy2(str(_cfg.EXAMPLE_FILE), str(_cfg.CONFIG_FILE))
        print(f"[配置] 已从 config.yaml.example 创建 config.yaml，请编辑后重新运行")
    if not _cfg.SECRETS_FILE.exists() and _cfg.SECRETS_EXAMPLE.exists():
        shutil.copy2(str(_cfg.SECRETS_EXAMPLE), str(_cfg.SECRETS_FILE))
        print(f"[配置] 已从 config.secrets.yaml.example 创建 config.secrets.yaml（密钥独立存储，不入库）")

    data = _read_yaml(_cfg.CONFIG_FILE)
    _inject_secrets(data, _load_secrets())
    from pydantic import ValidationError

    try:
        return Settings(**data)
    except ValidationError as e:
        lines = []
        for err in e.errors():
            loc = ".".join(str(x) for x in err["loc"])
            lines.append(f"  - {loc or '(root)'}: {err['msg']} ({err['type']})")
        raise RuntimeError(f"配置无效（{_cfg.CONFIG_FILE.name}），请修正后重启：\n" + "\n".join(lines)) from e
