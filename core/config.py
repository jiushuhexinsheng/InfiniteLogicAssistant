# -*- coding: utf-8 -*-
"""全局配置加载

支持 YAML 配置 + ${ENV_VAR} 环境变量插值 + 默认值兜底。
每个字段均通过 __getattr__ 暴露，支持点号访问。
"""
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

# PyInstaller 冻结时 __file__ 指向临时解压目录，改用 exe 所在目录作为根（config/data 放 exe 旁）
if getattr(sys, "frozen", False):
    ROOT_DIR = Path(sys.executable).resolve().parent
else:
    ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_FILE = ROOT_DIR / "config.yaml"
EXAMPLE_FILE = ROOT_DIR / "config.yaml.example"

ENV_VAR_PATTERN = re.compile(r"\$\{(\w+)\}")

DEFAULTS: Dict[str, Any] = {
    "voice": {
        "asr": {
            # 当前生效的 ASR profile 名；默认 openai（OpenAI 兼容，endpoint/model 由用户自填）
            "active": "openai",
            "profiles": {
                "openai": {
                    "provider": "openai",
                    "endpoint": "",
                    "api_key": "${ASR_API_KEY}",
                    "model": "",
                    "language": "zh",
                    "timeout": 30,
                    "chat_path": "/v1/chat/completions",
                },
            },
        },
        "tts": {
            "enabled": False,
            "active": "openai",
            "profiles": {
                "openai": {
                    "provider": "openai",
                    "endpoint": "",
                    "api_key": "${TTS_API_KEY}",
                    "model": "tts-1",
                    "voice": "alloy",
                    "timeout": 30,
                    "chat_path": "/v1/audio/speech",
                },
            },
        },
        "wake_word": {
            "enabled": True,
            "keyword": "小逻小逻",
            "sensitivity": 0.5,
            "model_path": "/models/vosk-model-small-cn-0.22.tar.gz",  # 浏览器端 URL
            # 桌面监听用本地模型目录；Windows 上 Kaldi/vosk 无法加载含中文的路径，必须 ASCII
            "local_model": "",
        },
        "vad": {
            "silence_threshold": 0.02,
            "silence_duration_ms": 1500,
            "max_duration_ms": 10000,
        },
    },
    "llm": {
        # 当前生效的 LLM profile 名（对应 profiles 下的键名）；默认 deepseek
        "active": "deepseek",
        "profiles": {
            "deepseek": {
                "provider": "openai",
                "endpoint": "https://api.deepseek.com",
                "api_key": "${LLM_API_KEY}",
                "model": "deepseek-chat",
                "vision_model": "",
                "chat_path": "/v1/chat/completions",
                "max_tokens": 4096,
                "temperature": 0.7,
                "timeout": 60,
            },
            "openai": {
                "provider": "openai",
                "endpoint": "https://api.openai.com/v1",
                "api_key": "${OPENAI_API_KEY}",
                "model": "gpt-4o-mini",
                "vision_model": "",
                "chat_path": "/v1/chat/completions",
                "max_tokens": 4096,
                "temperature": 0.7,
                "timeout": 60,
            },
            "qwen": {
                "provider": "openai",
                "endpoint": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "api_key": "${QWEN_API_KEY}",
                "model": "qwen-plus",
                "vision_model": "",
                "chat_path": "/v1/chat/completions",
                "max_tokens": 4096,
                "temperature": 0.7,
                "timeout": 60,
            },
        },
    },
    "agent": {
        "recursion_limit": 6,
        "max_history_messages": 40,
        # 复杂任务（多参数/长目标）转多智能体协调者
        "multi_agent": False,
    },
    "llm_client": {
        "retry_max": 3,
        "retry_backoff_base": 0.5,
        "retry_backoff_max": 10.0,
        "circuit_breaker_threshold": 5,
        "circuit_breaker_cooldown": 30.0,
        "request_timeout": 60,
    },
    "tools": {
        "search_max_results": 5,
        "weather_timeout": 10,
    },
    "mcp": {
        # MCP server 列表：{"name","command","args"}；服务启动时自动连接并注册其工具
        "servers": [],
    },
    "server": {"host": "127.0.0.1", "port": 8520, "open_browser": True},
}

# ─── 多 profile 兼容层（llm / voice.asr / voice.tts 共用）───
# 旧版扁平配置（provider/endpoint/model 直接平铺在 section 下）在加载时归一化为 profiles.default。

_LEGACY_LLM_KEYS = ("provider", "endpoint", "model")
_LEGACY_ASR_KEYS = ("endpoint", "api_key", "model")
_LEGACY_TTS_KEYS = ("endpoint", "api_key", "model")
# profile 内可携带的全部键（外网 OpenAI 兼容，无加密签名参数）
_LLM_PROFILE_KEYS = ("provider", "endpoint", "api_key", "model", "vision_model",
                     "chat_path", "max_tokens", "temperature", "timeout")
_ASR_PROFILE_KEYS = ("provider", "endpoint", "api_key", "model", "language",
                     "timeout", "chat_path")
_TTS_PROFILE_KEYS = ("provider", "endpoint", "api_key", "model", "voice",
                     "timeout", "chat_path")


def _llm_profile_defaults() -> Dict[str, Any]:
    """LLM profile 缺失字段的兜底默认值（model 留空，缺 endpoint/model 即未配置）。"""
    return {
        "provider": "openai", "api_key": "", "chat_path": "/v1/chat/completions",
        "vision_model": "", "max_tokens": 4096, "temperature": 0.7, "timeout": 60,
    }


def _asr_profile_defaults() -> Dict[str, Any]:
    """ASR profile 缺失字段的兜底默认值（model 兜底留空，缺 endpoint/model 即未配置）。"""
    return {
        "provider": "openai", "api_key": "", "model": "",
        "language": "zh", "timeout": 30, "chat_path": "/v1/chat/completions",
    }


def _tts_profile_defaults() -> Dict[str, Any]:
    """TTS profile 缺失字段的兜底默认值。"""
    return {
        "provider": "openai", "api_key": "", "model": "tts-1",
        "voice": "alloy", "timeout": 30, "chat_path": "/v1/audio/speech",
    }


def _llm_post_merge(p: Dict[str, Any]) -> None:
    """LLM 特有：vision_model 缺省回退到 model"""
    p["vision_model"] = p.get("vision_model") or p.get("model", "")


# section 注册表：path 用元组（区分顶层 llm 与嵌套 voice.asr）
_PROFILE_SECTIONS: Dict[str, Dict[str, Any]] = {
    "llm": {
        "path": ("llm",),
        "active_default": "deepseek",
        "legacy_keys": _LEGACY_LLM_KEYS,
        "profile_keys": _LLM_PROFILE_KEYS,
        "defaults": _llm_profile_defaults,
        "post_merge": _llm_post_merge,
    },
    "voice.asr": {
        "path": ("voice", "asr"),
        "active_default": "openai",
        "legacy_keys": _LEGACY_ASR_KEYS,
        "profile_keys": _ASR_PROFILE_KEYS,
        "defaults": _asr_profile_defaults,
        "post_merge": None,
    },
    "voice.tts": {
        "path": ("voice", "tts"),
        "active_default": "openai",
        "legacy_keys": _LEGACY_TTS_KEYS,
        "profile_keys": _TTS_PROFILE_KEYS,
        "defaults": _tts_profile_defaults,
        "post_merge": None,
    },
}


def _get_section(root: Dict, path: tuple) -> Dict[str, Any]:
    """按路径元组取字典节点，任一环节非 dict 返回 {}。"""
    node = root
    for p in path:
        if not isinstance(node, dict):
            return {}
        node = node.get(p)
    return node if isinstance(node, dict) else {}


def _set_section(config: Dict, path: tuple, profiles: Dict, active: str) -> None:
    """在 config 中写入 section 的 profiles + active（保留同层其他键）。"""
    node = config
    for p in path[:-1]:
        node = node.setdefault(p, {})
    section = node.setdefault(path[-1], {})
    section["profiles"] = profiles
    section["active"] = active


def _legacy_profile(block: Any, legacy_keys, profile_keys, defaults_fn) -> Optional[Dict[str, Any]]:
    """旧版扁平块 → 单个 profile；非旧版返回 None。"""
    if not isinstance(block, dict):
        return None
    if not any(k in block for k in legacy_keys):
        return None
    p = defaults_fn()
    for k in profile_keys:
        if k in block and block[k] is not None:
            p[k] = block[k]
    p["endpoint"] = (p.get("endpoint") or "").rstrip("/")
    return p


def _normalize_section(config: Dict[str, Any], raw: Dict[str, Any], section_name: str) -> None:
    """把旧版扁平 section 配置归一化为 profiles 单键（就地修改 config，向后兼容）。"""
    meta = _PROFILE_SECTIONS[section_name]
    raw_section = _get_section(raw, meta["path"]) if isinstance(raw, dict) else {}
    user_profiles = raw_section.get("profiles") if isinstance(raw_section, dict) else None
    if isinstance(user_profiles, dict) and user_profiles:
        return  # 用户显式写了 profiles → 新结构优先，扁平字段视为残留
    legacy = _legacy_profile(raw_section, meta["legacy_keys"], meta["profile_keys"], meta["defaults"])
    if legacy is not None:
        _set_section(config, meta["path"], {"default": legacy}, "default")


def _resolve_env_vars(value: Any) -> Any:
    """递归替换字符串中的 ${ENV_VAR}"""
    if isinstance(value, str):
        def replacer(m):
            return os.environ.get(m.group(1), m.group(0))
        return ENV_VAR_PATTERN.sub(replacer, value)
    if isinstance(value, dict):
        return {k: _resolve_env_vars(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_env_vars(v) for v in value]
    return value


def _deep_merge(base: Dict, override: Dict) -> Dict:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config() -> Dict[str, Any]:
    config = _deep_merge(DEFAULTS, {})
    raw: Dict[str, Any] = {}
    if not CONFIG_FILE.exists() and EXAMPLE_FILE.exists():
        import shutil
        shutil.copy2(str(EXAMPLE_FILE), str(CONFIG_FILE))
        print(f"[配置] 已从 config.yaml.example 创建 config.yaml，请配置后重新运行")
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                raw = yaml.safe_load(f) or {}
            config = _deep_merge(config, raw)
        except Exception as e:
            print(f"[WARN] 配置加载失败: {e}")
    _normalize_section(config, raw, "llm")        # 旧版扁平 llm 块 → profiles.default
    _normalize_section(config, raw, "voice.asr")  # 旧版扁平 voice.asr 块 → profiles.default
    _normalize_section(config, raw, "voice.tts")  # 旧版扁平 voice.tts 块 → profiles.default
    return _resolve_env_vars(config)


# 全局单例
_config: Dict[str, Any] | None = None


def get_config() -> Dict[str, Any]:
    global _config
    if _config is None:
        _config = load_config()
    return _config


def cfg(path: str = "", default=None):
    """点号路径取值: cfg('llm.model')"""
    parts = path.split(".") if path else []
    node = get_config()
    for p in parts:
        if isinstance(node, dict):
            node = node.get(p)
        else:
            return default
    return node if node is not None else default


def _resolve_profile(section_name: str) -> tuple:
    """通用 profile 解析：(profile名, profile字典)。"""
    meta = _PROFILE_SECTIONS[section_name]
    section = _get_section(get_config(), meta["path"])
    profiles = section.get("profiles") if isinstance(section, dict) else {}
    if not isinstance(profiles, dict) or not profiles:
        return "", {}
    active = (section.get("active") if isinstance(section, dict) else None) or meta["active_default"]
    profile = profiles.get(active)
    if not isinstance(profile, dict):
        first = next(iter(profiles))
        print(f"[WARN] {'.'.join(meta['path'])}.active='{active}' 在 profiles 中不存在，已回退到 '{first}'")
        active, profile = first, profiles[first]
    merged = meta["defaults"]()
    merged.update(profile)
    merged["endpoint"] = (merged.get("endpoint") or "").rstrip("/")
    if meta["post_merge"]:
        meta["post_merge"](merged)
    return active, merged


def resolve_llm_profile() -> tuple:
    """返回当前生效的 LLM profile：(profile名, profile字典)。"""
    return _resolve_profile("llm")


def resolve_asr_profile() -> tuple:
    """返回当前生效的 ASR profile：(profile名, profile字典)。"""
    return _resolve_profile("voice.asr")


def resolve_tts_profile() -> tuple:
    """返回当前生效的 TTS profile：(profile名, profile字典)。"""
    return _resolve_profile("voice.tts")


def is_llm_configured() -> bool:
    _, profile = resolve_llm_profile()
    return bool(profile.get("endpoint") and profile.get("model"))


def is_asr_configured() -> bool:
    _, profile = resolve_asr_profile()
    return bool(profile.get("endpoint") and profile.get("model"))


def is_tts_enabled() -> bool:
    """TTS 是否启用：voice.tts.enabled 为 true，且当前 TTS profile 已配置 endpoint"""
    if not cfg("voice.tts.enabled"):
        return False
    _, profile = resolve_tts_profile()
    return bool(profile.get("endpoint"))


def ensure_dirs():
    (ROOT_DIR / "data").mkdir(exist_ok=True)
