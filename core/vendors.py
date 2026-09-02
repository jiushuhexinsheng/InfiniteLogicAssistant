# -*- coding: utf-8 -*-
"""厂商目录 — 内置 LLM/ASR/TTS 预设 + config.yaml vendor_presets 扩展

设计要点：
- 预设只是「预填默认值」：选中后写入 profile 变成普通配置，可再手改；保留自由手填路径。
- endpoint 为基座 URL（不含 /v1，与 chat_path 配对），避免拼出 /v1/v1/ 错误地址。
- provider 是协议（openai / anthropic / gemini）；vendor 是目录 ID（UI 元数据）。
- 协议分派只发生在 LLM 层（resolve_protocol）；TTS/ASR 全走 openai，维持既有 chat_path 推断。

Vendor catalogue — built-in LLM/ASR/TTS presets + config.yaml vendor_presets
extension.

Design notes:
- Presets are just "pre-filled defaults": once selected they become ordinary
  profiles, still fully editable; manual fill path remains available.
- ``endpoint`` is the base URL (without /v1, paired with ``chat_path``),
  avoiding accidental /v1/v1/ duplication.
- ``provider`` is the protocol (openai / anthropic / gemini); ``vendor`` is the
  catalogue ID (UI metadata).
- Protocol dispatch happens only at the LLM layer (``resolve_protocol``);
  TTS/ASR always use openai, relying on the existing ``chat_path`` inference.
"""
from typing import Any

from core.config import VendorPreset
from core.logger import logger


def _preset(
    preset_id: str,
    *,
    kind: str,
    label: str,
    provider: str = "openai",
    endpoint: str = "",
    chat_path: str = "",
    models_path: str = "",
    models: list[str] | None = None,
    vision_models: list[str] | None = None,
    voices: list[str] | None = None,
    api_key_env: str = "",
    compat: dict | None = None,
    defaults: dict | None = None,
) -> tuple[str, VendorPreset]:
    """构造一个预设条目：返回 (preset_id, VendorPreset) 元组，用于构建字典。

    Build a preset entry: return a ``(preset_id, VendorPreset)`` tuple for dict
    construction.
    """
    return (
        preset_id,
        VendorPreset(
            kind=kind, label=label, provider=provider, endpoint=endpoint, chat_path=chat_path,
            models_path=models_path, models=models or [], vision_models=vision_models or [],
            voices=voices or [], api_key_env=api_key_env, compat=compat or {},
            defaults=defaults or {},
        ),
    )


# ─────────────────────────── 内置 LLM 预设（16 个） ───────────────────────────

BUILTIN_LLM: dict[str, VendorPreset] = dict([
    _preset("deepseek", kind="llm", label="DeepSeek", endpoint="https://api.deepseek.com",
            chat_path="/v1/chat/completions", models=["deepseek-chat", "deepseek-reasoner"],
            api_key_env="DEEPSEEK_API_KEY", defaults={"temperature": 0.7, "max_tokens": 4096}),
    _preset("openai", kind="llm", label="OpenAI", endpoint="https://api.openai.com",
            chat_path="/v1/chat/completions",
            models=["gpt-4o", "gpt-4o-mini", "gpt-5", "gpt-5-mini"],
            vision_models=["gpt-4o", "gpt-5"], api_key_env="OPENAI_API_KEY",
            compat={"max_tokens_field": "max_completion_tokens"},
            defaults={"temperature": 0.7, "max_tokens": 4096}),
    _preset("qwen", kind="llm", label="通义千问（阿里百炼）", endpoint="https://dashscope.aliyuncs.com/compatible-mode/v1",
            chat_path="/chat/completions", models=["qwen-plus", "qwen-turbo", "qwen-max"],
            vision_models=["qwen-vl-max"], api_key_env="DASHSCOPE_API_KEY",
            defaults={"temperature": 0.7, "max_tokens": 4096}),
    _preset("glm", kind="llm", label="智谱 GLM", endpoint="https://open.bigmodel.cn/api/paas/v4",
            chat_path="/chat/completions", models=["glm-4-plus", "glm-4-air", "glm-4-flash"],
            api_key_env="ZHIPU_API_KEY", defaults={"temperature": 0.7, "max_tokens": 4096}),
    _preset("kimi", kind="llm", label="Kimi（月之暗面）", endpoint="https://api.moonshot.cn/v1",
            chat_path="/chat/completions", models=["kimi-k2-0905-preview", "moonshot-v1-8k"],
            api_key_env="MOONSHOT_API_KEY", defaults={"temperature": 0.7, "max_tokens": 4096}),
    _preset("doubao", kind="llm", label="豆包（火山方舟）", endpoint="https://ark.cn-beijing.volces.com/api/v3",
            chat_path="/chat/completions", models=["doubao-pro-32k", "doubao-lite-32k"],
            api_key_env="VOLC_ARK_API_KEY", defaults={"temperature": 0.7, "max_tokens": 4096}),
    _preset("qianfan", kind="llm", label="百度千帆", endpoint="https://qianfan.baidubce.com/v2",
            chat_path="/chat/completions", models=["ernie-4.0-8k", "ernie-3.5-8k", "ernie-speed-8k"],
            api_key_env="QIANFAN_API_KEY", defaults={"temperature": 0.7, "max_tokens": 4096}),
    _preset("xinghuo", kind="llm", label="讯飞星火", endpoint="https://spark-api-open.xf-yun.com/v1",
            chat_path="/chat/completions", models=["4.0Ultra", "generalv3.5", "general"],
            api_key_env="SPARK_API_KEY", defaults={"temperature": 0.7, "max_tokens": 4096}),
    _preset("minimax", kind="llm", label="MiniMax", endpoint="https://api.minimax.chat/v1",
            chat_path="/chat/completions", models=["abab6.5s-chat", "abab6.5g-chat"],
            api_key_env="MINIMAX_API_KEY", defaults={"temperature": 0.7, "max_tokens": 4096}),
    _preset("siliconflow", kind="llm", label="硅基流动", endpoint="https://api.siliconflow.cn/v1",
            chat_path="/chat/completions",
            models=["deepseek-ai/DeepSeek-V3", "Qwen/Qwen2.5-7B-Instruct"],
            api_key_env="SILICONFLOW_API_KEY", defaults={"temperature": 0.7, "max_tokens": 4096}),
    _preset("openrouter", kind="llm", label="OpenRouter（聚合）", endpoint="https://openrouter.ai/api/v1",
            chat_path="/chat/completions", models=["anthropic/claude-3.5-sonnet", "openai/gpt-4o"],
            api_key_env="OPENROUTER_API_KEY", defaults={"temperature": 0.7, "max_tokens": 4096}),
    _preset("ollama", kind="llm", label="Ollama（本地）", endpoint="http://127.0.0.1:11434",
            chat_path="/v1/chat/completions", models=["llama3.1", "qwen2.5", "deepseek-r1"],
            compat={"stream_options": False}, defaults={"timeout": 120}),
    _preset("lmstudio", kind="llm", label="LM Studio（本地）", endpoint="http://127.0.0.1:1234",
            chat_path="/v1/chat/completions", compat={"stream_options": False}, defaults={"timeout": 120}),
    _preset("anthropic", kind="llm", label="Anthropic Claude", provider="anthropic",
            endpoint="https://api.anthropic.com", chat_path="/v1/messages",
            models=["claude-sonnet-4-20250514", "claude-3-7-sonnet-latest", "claude-3-5-haiku-latest"],
            api_key_env="ANTHROPIC_API_KEY", defaults={"max_tokens": 4096}),
    _preset("gemini", kind="llm", label="Google Gemini", provider="gemini",
            endpoint="https://generativelanguage.googleapis.com",
            chat_path="/v1beta/models/{model}:streamGenerateContent?alt=sse",
            models_path="/v1beta/models", models=["gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.0-flash"],
            api_key_env="GEMINI_API_KEY", defaults={"max_tokens": 4096}),
    _preset("xiaomi-mimo-llm", kind="llm", label="小米 MiMo（大模型）", endpoint="https://api.xiaomimimo.com",
            chat_path="/v1/chat/completions",
            models=["mimo-v2.5-pro", "mimo-v2.5"],
            api_key_env="MIMO_API_KEY",
            compat={"max_tokens_field": "max_completion_tokens"},
            defaults={"max_tokens": 4096, "temperature": 0.7}),
])


# ─────────────────────────── 内置 ASR 预设 ───────────────────────────

BUILTIN_ASR: dict[str, VendorPreset] = dict([
    _preset("openai-whisper", kind="asr", label="OpenAI Whisper", endpoint="https://api.openai.com",
            chat_path="/v1/chat/completions", models=["gpt-4o-transcribe", "gpt-4o-mini-transcribe"],
            api_key_env="OPENAI_API_KEY", defaults={"language": "zh", "timeout": 30}),
    _preset("siliconflow-asr", kind="asr", label="硅基流动 ASR", endpoint="https://api.siliconflow.cn/v1",
            chat_path="/chat/completions", models=["Qwen2-Audio-7B-Instruct"],
            api_key_env="SILICONFLOW_API_KEY", defaults={"language": "zh", "timeout": 30}),
    _preset("xiaomi-mimo-asr", kind="asr", label="小米 MiMo ASR", endpoint="https://api.xiaomimimo.com",
            chat_path="/v1/chat/completions", models=["mimo-v2.5-asr"],
            api_key_env="MIMO_API_KEY",
            compat={"auth_header": "api-key", "audio_data_url": True, "send_language": True},
            defaults={"language": "zh", "timeout": 30}),
])


# ─────────────────────────── 内置 TTS 预设 ───────────────────────────

BUILTIN_TTS: dict[str, VendorPreset] = dict([
    _preset("xiaomi-mimo", kind="tts", label="小米 MiMo", endpoint="https://api.xiaomimimo.com",
            chat_path="/v1/chat/completions",
            models=["mimo-v2.5-tts", "mimo-v2.5-tts-voiceclone", "mimo-v2.5-tts-voicedesign"],
            voices=["Chloe", "Mia", "冰糖", "茉莉", "苏打", "白桦", "Dean", "Milo", "mimo_default"],
            api_key_env="TTS_API_KEY", defaults={"format": "wav", "timeout": 30}),
    _preset("openai-tts", kind="tts", label="OpenAI TTS", endpoint="https://api.openai.com",
            chat_path="/v1/audio/speech", models=["tts-1", "tts-1-hd", "gpt-4o-mini-tts"],
            voices=["alloy", "echo", "fable", "onyx", "nova", "shimmer", "coral", "verse", "ballad", "ash", "sage"],
            api_key_env="OPENAI_API_KEY", defaults={"format": "mp3", "timeout": 30}),
])


# ─────────────────────────── 合并与查询 ───────────────────────────

_KNOWN_PROTOCOLS = ("openai", "anthropic", "gemini")


def get_vendor_catalog() -> dict[str, VendorPreset]:
    """代码内置目录 + config.yaml vendor_presets 扩展（同 ID 覆盖，可追加新 ID）。

    Built-in catalogue merged with ``config.yaml`` vendor_presets extensions
    (same ID overwrites, new IDs appended).
    """
    from core import config  # 延迟导入避免任何初始化顺序问题
    merged: dict[str, VendorPreset] = {}
    merged.update(BUILTIN_LLM)
    merged.update(BUILTIN_ASR)
    merged.update(BUILTIN_TTS)
    for k, v in config.settings.vendor_presets.items():
        if isinstance(v, VendorPreset):
            merged[k] = v
        else:
            logger.warning("vendor_presets[{}] 不是 VendorPreset，已跳过", k)
    return merged


def get_preset(preset_id: str) -> VendorPreset | None:
    """按 preset_id 查询单个预设，未找到返回 None。

    Look up a single preset by its ID; return ``None`` if not found.
    """
    return get_vendor_catalog().get(preset_id)


def get_presets_by_kind(kind: str) -> list[tuple[str, VendorPreset]]:
    """按 kind（llm/asr/tts）筛选全部预设，返回 (id, preset) 列表。

    Filter all presets by *kind* (llm/asr/tts); return a list of
    ``(preset_id, VendorPreset)`` tuples.
    """
    return [(k, p) for k, p in get_vendor_catalog().items() if p.kind == kind]


def preset_to_profile(preset_id: str, p: VendorPreset) -> dict[str, Any]:
    """把目录预设转成可写入 profiles 的预填 dict（结构性字段优先，defaults 只填空）。

    Convert a catalogue preset into a pre-filled dict writable to profiles
    (structural fields prioritised; ``defaults`` fill empty slots only).
    """
    prof: dict[str, Any] = {
        "provider": p.provider or "openai",
        "vendor": preset_id,
        "endpoint": p.endpoint,
        "chat_path": p.chat_path or "/v1/chat/completions",
        "models": list(p.models),
        "model": p.defaults.get("model") or (p.models[0] if p.models else ""),
        "api_key_env": p.api_key_env,
        "compat": dict(p.compat),
    }
    if p.models_path:
        prof["models_path"] = p.models_path
    if p.vision_models:
        prof["vision_models"] = list(p.vision_models)
    if p.voices:
        prof["voices"] = list(p.voices)
        prof["voice"] = p.defaults.get("voice") or p.voices[0]
    for k, v in p.defaults.items():
        prof.setdefault(k, v)
    return prof


def resolve_protocol(profile: dict) -> str:
    """LLM 协议分派：provider 命中 → vendor 反查目录 → chat_path 推断 → 默认 openai。

    仅 LLM 层调用；TTS/ASR 不依赖此函数（维持各自 chat_path 推断）。

    LLM protocol dispatch: ``provider`` match → vendor catalogue lookup →
    ``chat_path`` inference → default ``openai``.

    Called only by the LLM layer; TTS/ASR do not depend on this function
    (they rely on their own ``chat_path`` inference).
    """
    p = (profile.get("provider") or "").strip()
    if p in _KNOWN_PROTOCOLS:
        return p
    vid = profile.get("vendor")
    preset = get_preset(str(vid)) if vid else None
    if preset is not None:
        return preset.provider or "openai"
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
    """递归剥除 api_key / api_token，用于目录等对外输出。

    Recursively strip ``api_key`` / ``api_token`` from a dict, for safe external
    output (e.g. catalogue endpoints).
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
