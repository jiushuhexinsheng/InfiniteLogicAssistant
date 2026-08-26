# -*- coding: utf-8 -*-
"""全局配置 — pydantic 强类型加载（参考 InfiniteLogic-main 的强类型方案，保留本项目多 profile YAML 结构）

配置源（优先级从低到高）：
1. pydantic 模型默认值（Field 约束 / Literal 枚举，写错配置启动即报错）
2. config.yaml            —— 非敏感结构（llm/voice/server/mcp/rag/agent/llm_client/tools），不含任何密钥
3. config.secrets.yaml    —— 密钥独立存储（gitignored，仅提交 example 模板）
4. 环境变量               —— LLM_API_KEY / ASR_API_KEY / TTS_API_KEY / SERVER_API_TOKEN 覆盖密钥

兼容层：resolve_llm_profile()/resolve_asr_profile()/resolve_tts_profile() 仍返回 (name, dict)，
is_*_configured / is_tts_enabled / ROOT_DIR / ensure_dirs 保留；cfg() 点号访问已移除。
"""
import os
import shutil
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_FILE = ROOT_DIR / "config.yaml"
EXAMPLE_FILE = ROOT_DIR / "config.yaml.example"
SECRETS_FILE = ROOT_DIR / "config.secrets.yaml"
SECRETS_EXAMPLE = ROOT_DIR / "config.secrets.yaml.example"

_ENV_KEY_MAP = {
    "llm": "LLM_API_KEY",
    "asr": "ASR_API_KEY",
    "tts": "TTS_API_KEY",
}


# ─────────────────────────── 模型定义 ───────────────────────────


class CompatConfig(BaseModel):
    """厂商兼容开关（影响请求体组装；默认与既有行为一致，纯增量）。"""

    model_config = ConfigDict(extra="allow")

    stream_options: bool = True   # 是否发 stream_options.include_usage（部分网关拒绝未知字段）
    max_tokens_field: Literal["max_tokens", "max_completion_tokens"] = "max_tokens"


class VendorPreset(BaseModel):
    """厂商目录预设（代码内置 + config.yaml vendor_presets 扩展）；extra=forbid 防拼错键。"""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["llm", "asr", "tts"]
    label: str = ""
    provider: str = "openai"   # 协议：openai / anthropic / gemini
    endpoint: str = ""         # 基座 URL（不含 /v1，与 chat_path 配对）
    chat_path: str = ""
    models_path: str = ""      # 获取模型列表路径；空则从 chat_path 推导
    models: list[str] = Field(default_factory=list)
    vision_models: list[str] = Field(default_factory=list)
    voices: list[str] = Field(default_factory=list)   # 仅 TTS
    api_key_env: str = ""      # 推荐环境变量名（非密钥本身）
    compat: dict[str, Any] = Field(default_factory=dict)
    defaults: dict[str, Any] = Field(default_factory=dict)


class ProfileBase(BaseModel):
    """各 profile 公共字段；extra=allow 保留用户透传键（如 TTS 的 format/voice_ref）。"""

    model_config = ConfigDict(extra="allow")

    provider: str = "openai"   # 协议：openai / anthropic / gemini（LLM 分派用）
    vendor: str = ""           # 厂商目录 ID（UI 元数据，不参与请求）
    endpoint: str = ""
    api_key: str = ""  # 由 loader 从 secrets/环境注入；config.yaml 不写
    api_key_env: str = ""      # 本 profile 专用环境变量名（优先级最高）
    chat_path: str = "/v1/chat/completions"
    timeout: int = Field(30, gt=0)
    models: list[str] = Field(default_factory=list)   # 可用模型列表（UI 下拉 / 展示）
    models_path: str = ""      # 获取模型列表路径；空则从 chat_path 推导
    compat: CompatConfig = Field(default_factory=CompatConfig)


class LlmProfile(ProfileBase):
    model: str = ""
    vision_model: str = ""
    max_tokens: int = Field(4096, gt=0)
    temperature: float = Field(0.7, ge=0.0, le=2.0)


class AsrProfile(ProfileBase):
    model: str = ""
    language: str = "zh"


class TtsProfile(ProfileBase):
    model: str = "tts-1"
    voice: str = "alloy"
    format: Literal["wav", "mp3", "pcm16"] = "wav"
    voice_ref: str | None = None
    voices: list[str] = Field(default_factory=list)   # 音色列表（UI 下拉）


class LlmSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    active: str = "deepseek"
    profiles: dict[str, LlmProfile] = Field(default_factory=dict)


class AsrSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    active: str = "openai"
    profiles: dict[str, AsrProfile] = Field(default_factory=dict)


class TtsSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    active: str = "openai"
    profiles: dict[str, TtsProfile] = Field(default_factory=dict)


class WakeWordConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    keyword: str = "小逻小逻"
    sensitivity: float = Field(0.5, ge=0.0, le=1.0)
    model_path: str = "/models/vosk-model-small-cn-0.22.tar.gz"


class VadConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    silence_threshold: float = Field(0.02, ge=0.0)
    silence_duration_ms: int = Field(1500, ge=0)
    max_duration_ms: int = Field(10000, ge=1000)


class VoiceSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    wake_word: WakeWordConfig = Field(default_factory=lambda: WakeWordConfig())
    vad: VadConfig = Field(default_factory=lambda: VadConfig())
    asr: AsrSection = Field(default_factory=lambda: AsrSection())
    tts: TtsSection = Field(default_factory=lambda: TtsSection())


class AgentSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recursion_limit: int = Field(12, gt=0)
    multi_agent: bool = False
    models_failover: list[str] = Field(default_factory=list)  # 主模型故障时的备选模型（P3）


class LlmClientSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    retry_max: int = Field(3, ge=0)
    retry_backoff_base: float = Field(0.5, gt=0)
    retry_backoff_max: float = Field(10.0, gt=0)
    circuit_breaker_threshold: int = Field(5, gt=0)
    circuit_breaker_cooldown: float = Field(30.0, gt=0)
    request_timeout: int = Field(60, gt=0)


class ToolsSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    search_max_results: int = Field(5, gt=0)
    weather_timeout: int = Field(10, gt=0)


class McpServer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    command: str
    args: list[str] = Field(default_factory=list)


class McpSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    servers: list[McpServer] = Field(default_factory=list)


class RagSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    auto_index: bool = True


class ServerSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host: str = "127.0.0.1"
    port: int = Field(8520, ge=1, le=65535)
    open_browser: bool = True
    api_token: str = ""  # 由 loader 从 secrets/环境注入
    cors_origins: list[str] = Field(default_factory=list)


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    llm: LlmSection = Field(default_factory=lambda: LlmSection())
    voice: VoiceSection = Field(default_factory=lambda: VoiceSection())
    server: ServerSection = Field(default_factory=lambda: ServerSection())
    mcp: McpSection = Field(default_factory=lambda: McpSection())
    rag: RagSection = Field(default_factory=lambda: RagSection())
    agent: AgentSection = Field(default_factory=lambda: AgentSection())
    llm_client: LlmClientSection = Field(default_factory=lambda: LlmClientSection())
    tools: ToolsSection = Field(default_factory=lambda: ToolsSection())
    vendor_presets: dict[str, VendorPreset] = Field(default_factory=dict)  # 厂商目录 YAML 扩展


# ─────────────────────────── 加载与密钥注入 ───────────────────────────


def _read_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _resolve_env(value: str) -> str:
    """解析 ${VAR} 占位符（仅用于旧配置迁移：config.yaml 里残留的 api_key 字段）。"""
    import re

    m = re.fullmatch(r"\$\{(\w+)\}", value.strip())
    return os.environ.get(m.group(1), "") if m else value


def _load_secrets() -> dict:
    """读取 config.secrets.yaml + 环境变量覆盖，返回 {
        'llm': {'api_key': str, 'profiles': {name: key}}, 'asr': ..., 'tts': ..., 'server': {'api_token': str}
    }"""
    raw = _read_yaml(SECRETS_FILE)
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
    > 旧 config.yaml profile.api_key（弃用，仅迁移）"""
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
    for sec_key in _ENV_KEY_MAP:
        section = data.get(sec_key)
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
    """对外暴露单个 profile 的密钥解析（fetch-models 等服务端转发用）。"""
    return _profile_api_key(section, name, _load_secrets(), profile)


def _build() -> Settings:
    if not CONFIG_FILE.exists() and EXAMPLE_FILE.exists():
        shutil.copy2(str(EXAMPLE_FILE), str(CONFIG_FILE))
        print(f"[配置] 已从 config.yaml.example 创建 config.yaml，请编辑后重新运行")
    if not SECRETS_FILE.exists() and SECRETS_EXAMPLE.exists():
        shutil.copy2(str(SECRETS_EXAMPLE), str(SECRETS_FILE))
        print(f"[配置] 已从 config.secrets.yaml.example 创建 config.secrets.yaml（密钥独立存储，不入库）")

    data = _read_yaml(CONFIG_FILE)
    _inject_secrets(data, _load_secrets())
    try:
        return Settings(**data)
    except ValidationError as e:
        lines = []
        for err in e.errors():
            loc = ".".join(str(x) for x in err["loc"])
            lines.append(f"  - {loc or '(root)'}: {err['msg']} ({err['type']})")
        raise RuntimeError(f"配置无效（{CONFIG_FILE.name}），请修正后重启：\n" + "\n".join(lines)) from e


# ─────────────────────────── 全局单例与访问 ───────────────────────────

_settings: Settings | None = None
_reload_hooks: list = []


def add_reload_hook(fn) -> None:
    """注册配置热重载后的回调（如重建 ASR/TTS 客户端等持有旧 profile 的单例）。"""
    _reload_hooks.append(fn)


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = _build()
    return _settings


def reload_settings() -> Settings:
    """重新加载配置（PATCH /api/config 后调用；per-request 读取立即生效）。"""
    global _settings
    _settings = _build()
    for fn in _reload_hooks:
        try:
            fn()
        except Exception:
            pass
    return _settings


def __getattr__(name: str):
    # 让 config.settings.xxx 始终指向当前单例（reload 后自动拿到新值）
    if name == "settings":
        return get_settings()
    raise AttributeError(name)


# ─────────────────────────── profile 解析（兼容返回 (name, dict)） ───────────────────────────


def resolve_llm_profile() -> tuple[str, dict]:
    return _resolve_profile("llm", "deepseek")


def resolve_asr_profile() -> tuple[str, dict]:
    return _resolve_profile("asr", "openai")


def resolve_tts_profile() -> tuple[str, dict]:
    return _resolve_profile("tts", "openai")


def _resolve_profile(section: str, active_default: str) -> tuple[str, dict]:
    s = getattr(get_settings().voice if section in ("asr", "tts") else get_settings(), section)
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
    if not get_settings().voice.tts.enabled:
        return False
    _, p = resolve_tts_profile()
    return bool(p.get("endpoint"))


def editable_snapshot() -> dict:
    """设置页可编辑快照：不含任何密钥值，密钥只以 *_set 布尔暴露。"""
    s = get_settings()

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
