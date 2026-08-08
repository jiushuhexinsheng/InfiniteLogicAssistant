# 无限逻辑·语音助手 重构实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将"AI  消息Agent"重构为"无限逻辑·语音助手"——删除全部消息与网络代码，只保留语音链路（Vosk 唤醒词 → ASR → LLM → TTS），配置统一为外网 OpenAI 兼容格式，并重新初始化 git。

**Architecture:** 保留原架构（Python 标准库 http.server + Vue3/Vite/TS + 浏览器 Vosk WASM），对外科手术式删改。后端保留 4 个 API 端点（ping/config/ai/chat/voice/transcribe），前端改为极简单页 + 悬浮球，多 profile 配置机制保留但仅保留 openai 兼容 provider。

**Tech Stack:** Python 3 (requests/pyyaml/loguru)、Vue 3 + Vite 5 + TypeScript、浏览器 Vosk WASM 唤醒词、SpeechSynthesis 播报。

## Global Constraints

- 删除所有 `原单位` / `加密` / `mail` / `网络` / `network` / `user_id` / `monitor` / `notify` 相关代码与配置（验收用 git grep 校验全库无残留）。
- 产品名统一为"无限逻辑·语音助手"，助手名"小逻"，唤醒词"小逻小逻"；物理目录 `InfiniteLogicAssistant` 不改。
- LLM 默认 profile = `deepseek`（OpenAI 兼容）；ASR/TTS 统一 OpenAI 兼容 provider，endpoint/model 留空待用户自填。
- 依赖仅保留 `requests` / `pyyaml` / `loguru`（删 gmssl、pycryptodomex）。
- 前端保留 `web/dist` 静态托管、`index.html` 中的 vosk.js/wake-word.js 引用不变。
- 平台 Windows，脚本使用 bat。

**说明（非约束）：** 本项目无测试框架，重构任务的"测试"即各任务的验证命令（import 检查 / 类型检查 / 端点冒烟 / 残留 grep）。每任务结束可独立验证，全部通过后提交。

---

## 文件结构（最终形态）

```
InfiniteLogicAssistant/
├── main.py                   入口（serve / test）
├── server.py                 HTTP 服务（4 端点 + 静态托管 web/dist）
├── start.bat / install_deps.bat / package_deploy.bat
├── config.yaml / config.yaml.example
├── requirements.txt
├── README.md
├── core/
│   ├── __init__.py           （保留）
│   ├── config.py             配置（多 profile，仅 openai 兼容）
│   ├── logger.py             （保留）
│   ├── llm/__init__.py       LLM（openai provider）
│   └── voice/__init__.py     ASR/TTS（openai provider）
├── scripts/libs/             离线 wheel（删 gmssl、pycryptodomex）
├── web/                      Vue3 前端（单页 + 悬浮球）
│   ├── index.html            （标题改）
│   ├── public/lib/*          （vosk.js / wake-word.js 保留）
│   └── src/
│       ├── main.ts           （保留）
│       ├── App.vue           （重写为极简单页）
│       ├── api.ts / types.ts / audio.ts
│       ├── composables/useApi.ts / useAssistant.ts
│       ├── components/FloatingAssistant.vue
│       └── styles/app.css    （清理为全局 reset）
└── docs/superpowers/         设计文档 + 本计划
```

---

### Task 1: git 重新初始化 + 设计文档首提交

**Files:**
- 删除: `.git/`
- 保留: `.gitignore`（现状已合适，含 data/、node_modules、web/dist、config.yaml 忽略）

**Interfaces:**
- Produces: 全新 git 仓库，首提交含设计文档；后续任务的改动逐个提交到新仓库（旧消息代码不会进入历史）。

- [ ] **Step 1: 删除旧 .git 并重新初始化**

```bash
cd "F:/projects/ai/InfiniteLogicAssistant"
rm -rf .git
git init
git config user.name "InfiniteLogic"   # 沿用原 git 用户
git config user.email "InfiniteLogic@local"   # 若无则用原收件箱；可省略
```

- [ ] **Step 2: 首提交（设计文档）**

```bash
git add .gitignore docs/superpowers/specs/2026-08-08-voice-assistant-refactor-design.md
git commit -m "init: 无限逻辑·语音助手（重构设计文档）"
```

- [ ] **Step 3: 验证**

Run: `git log --oneline`
Expected: 1 条提交，信息为 "init: 无限逻辑·语音助手（重构设计文档）"。

---

### Task 2: 后端配置外网化（core/config.py）

**Files:**
- Rewrite: `core/config.py`（全文替换）

**Interfaces:**
- Consumes: 无（保留 cfg/get_config/ensure_dirs/多 profile 机制）
- Produces: `resolve_llm_profile()` / `resolve_asr_profile()` / `resolve_tts_profile()` 返回 `(name, profile)`，profile 无 `加密` 键；`is_llm_configured()` / `is_asr_configured()` / `is_tts_enabled()` 语义不变。

- [ ] **Step 1: 全文替换 core/config.py**

新内容：

```python
# -*- coding: utf-8 -*-
"""全局配置加载

支持 YAML 配置 + ${ENV_VAR} 环境变量插值 + 默认值兜底。
每个字段均通过 __getattr__ 暴露，支持点号访问。
"""
import os
import re
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

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
            "model_path": "models/vosk-model-small-cn-0.22",
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
    "server": {"host": "127.0.0.1", "port": 8520, "open_browser": True},
}

# ─── 多 profile 兼容层（llm / voice.asr / voice.tts 共用）───
# 旧版扁平配置（provider/endpoint/model 直接平铺在 section 下）在加载时归一化为 profiles.default。

_LEGACY_LLM_KEYS = ("provider", "endpoint", "model")
_LEGACY_ASR_KEYS = ("endpoint", "api_key", "model")
_LEGACY_TTS_KEYS = ("endpoint", "api_key", "model")
# profile 内可携带的全部键（外网 OpenAI 兼容，无 加密）
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
```

- [ ] **Step 2: 验证**

Run: `python -c "from core.config import resolve_llm_profile, resolve_asr_profile, is_llm_configured; print(resolve_llm_profile()[0], is_llm_configured())"`
Expected: 输出 `deepseek True`（注意：若已有 config.yaml 则按 config.yaml 合并，默认 deepseek 有 endpoint+model 所以 True；ASR 默认 endpoint 空 → 未配置）。

Run: `git grep -n -iE "加密|原单位|mail|auth|notify|monitor|user_id" -- core/config.py`
Expected: 无输出（0 匹配）。

- [ ] **Step 3: 提交**

```bash
git add core/config.py
git commit -m "refactor: 配置外网化 — 移除消息/网络配置段与 加密，仅保留 OpenAI 兼容多 profile"
```

---

### Task 3: 后端 LLM 精简（core/llm/__init__.py）

**Files:**
- Rewrite: `core/llm/__init__.py`（全文替换）

**Interfaces:**
- Consumes: `resolve_llm_profile()` / `is_llm_configured()`（Task 2）
- Produces: `get_llm()` 单例；`LLMClient` 暴露 `available()` / `chat(system, user, model="") -> str` / `_call(messages, model="") -> str`（server.py 依赖 `_call`）；属性 `profile_name` / `provider` / `model`（main.py 依赖）。

- [ ] **Step 1: 全文替换 core/llm/__init__.py**

新内容：

```python
# -*- coding: utf-8 -*-
"""LLM 模块 — OpenAI 兼容多提供方客户端

provider="openai": OpenAI 兼容 API，POST {endpoint}{chat_path}
（DeepSeek、OpenAI、通义、vLLM、Ollama 等）
"""
import requests

from core.config import is_llm_configured, resolve_llm_profile
from core.logger import logger


class LLMClient:
    """LLM 客户端（OpenAI 兼容多提供方）"""

    def __init__(self):
        self.profile_name, p = resolve_llm_profile()
        self.provider = p.get("provider", "openai")
        self.endpoint = p.get("endpoint", "")
        self.api_key = p.get("api_key", "")
        self.model = p.get("model", "")
        self.vision_model = p.get("vision_model", "") or self.model
        self.chat_path = p.get("chat_path", "/v1/chat/completions")
        self.max_tokens = p.get("max_tokens", 4096)
        self.temperature = p.get("temperature", 0.7)
        self.timeout = p.get("timeout", 60)

        if self.profile_name:
            logger.info("LLM profile '{}'（provider={}, model={}）",
                        self.profile_name, self.provider, self.model)

    def available(self) -> bool:
        return is_llm_configured()

    def _call(self, messages: list, model: str = "") -> str:
        """调用 OpenAI 兼容 chat completions，返回 assistant 文本。"""
        url = f"{self.endpoint.rstrip('/')}{self.chat_path}"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        body = {
            "model": model or self.model,
            "messages": messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "stream": False,
        }
        resp = requests.post(url, json=body, headers=headers, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]

    def chat(self, system: str, user: str, model: str = "") -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user})
        return self._call(messages, model)


# 全局单例
_llm: LLMClient | None = None


def get_llm() -> LLMClient:
    global _llm
    if _llm is None:
        _llm = LLMClient()
    return _llm
```

- [ ] **Step 2: 验证**

Run: `python -c "from core.llm import get_llm; llm=get_llm(); print(llm.profile_name, llm.provider, llm.model)"`
Expected: `deepseek openai deepseek-chat`（若未设 LLM_API_KEY，api_key 为占位串 ${LLM_API_KEY}，无碍）。

Run: `git grep -n -iE "原单位|加密|mail|summary|polish|classify|voice_command" -- core/llm/`
Expected: 无输出。

- [ ] **Step 3: 提交**

```bash
git add core/llm/__init__.py
git commit -m "refactor: LLM 精简 — 移除  qwen 模型provider 与消息向 AI 功能，仅保留 OpenAI 兼容对话"
```

---

### Task 4: 后端语音精简（core/voice/__init__.py）

**Files:**
- Rewrite: `core/voice/__init__.py`（全文替换）

**Interfaces:**
- Consumes: `is_asr_configured()` / `is_tts_enabled()` / `resolve_asr_profile()` / `resolve_tts_profile()`（Task 2）
- Produces: `get_asr()` / `get_tts()` 单例；`ASRClient` 暴露 `available()` / `transcribe_base64(audio_base64, "wav") -> str`（server.py 依赖）及 `profile_name`/`provider`/`model`/`timeout`（main.py 依赖）；`TTSClient` 暴露 `available()` / `speak(text) -> bool`。

- [ ] **Step 1: 全文替换 core/voice/__init__.py**

新内容：

```python
# -*- coding: utf-8 -*-
"""语音模块 — ASR / TTS（OpenAI 兼容多提供方）

- ASR:  POST {endpoint}{chat_path} + messages[0].content input_audio（OpenAI 兼容）
- TTS:  POST {endpoint}{chat_path} + {"model","input","voice"}，响应为二进制音频
"""
import os
import tempfile

import requests

from core.config import is_asr_configured, is_tts_enabled, resolve_asr_profile, resolve_tts_profile
from core.logger import logger


class ASRClient:
    """ASR 语音识别客户端（OpenAI 兼容）"""

    def __init__(self):
        self.profile_name, p = resolve_asr_profile()
        self.provider = p.get("provider", "openai")
        self.endpoint = p.get("endpoint", "")
        self.api_key = p.get("api_key", "")
        self.model = p.get("model", "")
        self.language = p.get("language", "zh")
        self.timeout = p.get("timeout", 60)
        self.chat_path = p.get("chat_path", "/v1/chat/completions")

        if self.profile_name:
            logger.info("ASR profile '{}'（provider={}, model={}）",
                        self.profile_name, self.provider, self.model)

    @property
    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    def available(self) -> bool:
        return is_asr_configured()

    def transcribe_base64(self, audio_base64: str, audio_format: str = "wav") -> str:
        """调用 OpenAI 兼容 ASR（chat completions + input_audio）"""
        url = f"{self.endpoint.rstrip('/')}{self.chat_path}"
        body = {
            "model": self.model,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "input_audio", "input_audio": {"data": audio_base64, "format": audio_format}}
                ]
            }],
            "max_tokens": 1024,
        }
        resp = requests.post(url, json=body, headers=self._headers, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()


class TTSClient:
    """TTS 语音合成（OpenAI 兼容）"""

    def __init__(self):
        self.profile_name, p = resolve_tts_profile()
        self.provider = p.get("provider", "openai")
        self.endpoint = p.get("endpoint", "").rstrip("/")
        self.api_key = p.get("api_key", "")
        self.model = p.get("model", "tts-1")
        self.voice = p.get("voice", "alloy")
        self.timeout = p.get("timeout", 30)
        self.chat_path = p.get("chat_path", "/v1/audio/speech")

    def available(self) -> bool:
        return is_tts_enabled()

    def speak(self, text: str) -> bool:
        if not self.available():
            return False
        try:
            return self._speak(text)
        except Exception as e:
            logger.warning("TTS 失败: {}", e)
            return False

    def _speak(self, text: str) -> bool:
        url = f"{self.endpoint}{self.chat_path}"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        body = {"model": self.model, "input": text[:500], "voice": self.voice}
        resp = requests.post(url, json=body, headers=headers, timeout=self.timeout)
        resp.raise_for_status()
        return _play_audio(resp.content)


def _play_audio(data: bytes) -> bool:
    """把 TTS 音频写入临时文件并打开播放（Windows）"""
    import subprocess
    tmp = os.path.join(tempfile.gettempdir(), "tts_out.mp3")
    with open(tmp, "wb") as f:
        f.write(data)
    subprocess.Popen(["start", tmp], shell=True)
    return True


# 全局单例
_asr: ASRClient | None = None
_tts: TTSClient | None = None


def get_asr() -> ASRClient:
    global _asr
    if _asr is None:
        _asr = ASRClient()
    return _asr


def get_tts() -> TTSClient:
    global _tts
    if _tts is None:
        _tts = TTSClient()
    return _tts
```

- [ ] **Step 2: 验证**

Run: `python -c "from core.voice import get_asr, get_tts; print(get_asr().provider, get_tts().provider)"`
Expected: `openai openai`

Run: `git grep -n -iE "原单位|加密|sensevoice|kokoro" -- core/voice/`
Expected: 无输出。

- [ ] **Step 3: 提交**

```bash
git add core/voice/__init__.py
git commit -m "refactor: 语音精简 — 移除 网络SenseVoice/Kokoro provider，仅保留 OpenAI 兼容 ASR/TTS"
```

---

### Task 5: 后端 server/main 精简

**Files:**
- Rewrite: `main.py`、`server.py`（全文替换）

**Interfaces:**
- Consumes: `start_server()`；`get_llm()._call(messages)`、`get_asr().transcribe_base64(b64, "wav")`、`cfg()`、`is_llm_configured()`、`is_asr_configured()`、`resolve_llm_profile()`、`resolve_asr_profile()`（Task 2-4）
- Produces: 仅 4 个 HTTP 端点（见下）；`python main.py serve` / `python main.py test` 两个命令。

- [ ] **Step 1: 全文替换 main.py**

新内容：

```python
# -*- coding: utf-8 -*-
"""无限逻辑·语音助手 — 主入口

用法:
    python main.py serve             启动 Web 服务
    python main.py test              测试 LLM / ASR 连通性
"""
import base64
import io
import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.config import ensure_dirs, is_llm_configured, resolve_llm_profile, is_asr_configured, resolve_asr_profile
from core.logger import logger


def cmd_serve():
    from server import start_server
    start_server()


def _silence_wav_base64(seconds: float = 0.3, rate: int = 16000) -> str:
    """生成一小段静音 WAV 的 base64（用于 ASR 连通性测试，无需真实语音）"""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(rate * seconds))
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def cmd_test():
    """测试 LLM / ASR 连通性（start.bat 启动前调用）。

    任一失败返回非零退出码，便于启动脚本中断并提示查看 data/agent.log。
    """
    import traceback
    TEST_TIMEOUT = 8  # 连通测试超时（秒），避免服务不可达时长时间阻塞启动
    print("=" * 56)
    print("  连通性测试 — LLM / ASR")
    print("=" * 56)

    failed = False

    # ── LLM ──
    print("\n[LLM] 正在测试...")
    if not is_llm_configured():
        print("  [跳过] LLM 未配置（config.yaml 缺少 endpoint/model）")
    else:
        try:
            from core.llm import get_llm
            llm = get_llm()
            llm.timeout = TEST_TIMEOUT  # 测试用短超时，不改变 config.yaml 的生产配置
            reply = llm.chat("你是一个测试助手。", "请只回复两个字：连通")
            ok = bool(reply and reply.strip())
            print(f"  [{'OK' if ok else '失败'}] profile={llm.profile_name} provider={llm.provider} model={llm.model}")
            if ok:
                print(f"      回复: {reply.strip()[:80]}")
            else:
                print("      返回为空")
                failed = True
        except Exception as e:
            logger.error("LLM 连通性测试失败: {}", e)
            logger.debug("LLM 测试堆栈:\n{}", traceback.format_exc())
            print(f"  [失败] {type(e).__name__}: {e}")
            print("       详情见 data/agent.log")
            failed = True

    # ── ASR ──
    print("\n[ASR] 正在测试...")
    if not is_asr_configured():
        print("  [跳过] ASR 未配置（config.yaml 缺少 endpoint/model）")
    else:
        try:
            from core.voice import get_asr
            asr = get_asr()
            asr.timeout = TEST_TIMEOUT  # 测试用短超时
            audio_b64 = _silence_wav_base64()
            text = asr.transcribe_base64(audio_b64, "wav")
            ok = isinstance(text, str)
            print(f"  [{'OK' if ok else '失败'}] profile={asr.profile_name} provider={asr.provider} model={asr.model}")
            if ok:
                print(f"      返回: {text.strip()[:80] or '(空文本，链路已通)'}")
            else:
                failed = True
        except Exception as e:
            logger.error("ASR 连通性测试失败: {}", e)
            logger.debug("ASR 测试堆栈:\n{}", traceback.format_exc())
            print(f"  [失败] {type(e).__name__}: {e}")
            print("       详情见 data/agent.log")
            failed = True

    print(f"\n{'=' * 56}")
    if failed:
        print("  结果: 存在连通性失败，请查看 data/agent.log")
        sys.exit(1)
    else:
        print("  结果: LLM / ASR 连通正常")
    print(f"{'=' * 56}\n")


def main():
    ensure_dirs()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "serve"
    if cmd == "serve":
        cmd_serve()
    elif cmd == "test":
        cmd_test()
    else:
        print(f"用法: python main.py {{serve|test}}")
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 全文替换 server.py**

新内容：

```python
# -*- coding: utf-8 -*-
"""
无限逻辑·语音助手 — HTTP API 服务
"""
import json
import mimetypes
import shutil
import threading
import time
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

from core.config import cfg, ensure_dirs, is_llm_configured, is_asr_configured, resolve_llm_profile, resolve_asr_profile, ROOT_DIR
from core.logger import logger


class APIHandler:
    """语音助手 API 处理器"""

    def ai_chat(self, params: dict) -> dict:
        """通用 LLM 对话（悬浮球助手使用）"""
        from core.llm import get_llm
        llm = get_llm()
        if not llm.available():
            return {"ok": False, "error": "LLM 未配置"}
        try:
            messages = params.get("messages", [])
            logger.info("ai_chat 请求，{} 条消息", len(messages))
            result = llm._call(messages)
            logger.info("ai_chat 返回 {} 字", len(result or ""))
            return {"ok": True, "text": result}
        except Exception as e:
            logger.error("ai_chat 失败: {} | provider={} model={}", e, llm.provider, llm.model)
            logger.debug("ai_chat 堆栈", exc_info=True)
            return {"ok": False, "error": str(e)}

    def voice_transcribe(self, body: bytes) -> dict:
        from core.voice import get_asr
        asr = get_asr()
        if not asr.available():
            return {"ok": False, "error": "ASR 未配置"}
        try:
            # JSON 体传 audio_base64（16kHz mono WAV）
            if body:
                try:
                    params = json.loads(body.decode("utf-8"))
                    b64 = params.get("audio_base64", "")
                    if b64:
                        text = asr.transcribe_base64(b64, "wav")
                        return {"ok": True, "text": text}
                except (json.JSONDecodeError, UnicodeDecodeError):
                    pass
            return {"ok": False, "error": "请提供 audio_base64 参数"}
        except Exception as e:
            logger.error("voice_transcribe: {}", e)
            return {"ok": False, "error": str(e)}

    def config(self) -> dict:
        return {
            "llm_available": is_llm_configured(),
            "llm_profile": resolve_llm_profile()[0],
            "asr_available": is_asr_configured(),
            "asr_profile": resolve_asr_profile()[0],
            "wake_word": cfg("voice.wake_word", {}),
            "vad": cfg("voice.vad", {}),
        }


# ─── 静态文件服务 ───

WEB_DIST_DIR = ROOT_DIR / "web" / "dist"
_CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".mjs": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".ico": "image/x-icon",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".ttf": "font/ttf",
    ".wasm": "application/wasm",
    ".mdl": "application/octet-stream",
    ".fst": "application/octet-stream",
    ".int": "application/octet-stream",
    ".mat": "application/octet-stream",
    ".dubm": "application/octet-stream",
    ".ie": "application/octet-stream",
    ".stats": "application/octet-stream",
    ".conf": "text/plain; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
}


def _send_file(handler, path: Path, content_type: str) -> None:
    """流式发送文件，避免大文件整块读入内存（如 Vosk 模型 ~40MB）"""
    try:
        size = path.stat().st_size
        f = path.open("rb")
    except Exception:
        handler._send_json({"ok": False, "error": "读取失败"}, 500)
        return
    handler.send_response(200)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(size))
    handler.end_headers()
    try:
        shutil.copyfileobj(f, handler.wfile)
    finally:
        f.close()


def _serve_static(handler, path: str) -> bool:
    """托管 web/dist 前端静态资源，供 'python main.py serve' 单命令启动。

    返回 True 表示已处理（页面/资源已输出），False 表示非前端路径（未匹配）。
    """
    if not WEB_DIST_DIR.is_dir():
        return False
    # 去掉查询串
    clean = path.split("?")[0]
    # 规范化：空路径/目录 → index.html
    if clean in ("", "/"):
        clean = "/index.html"
    # 解析到 dist 根内，防止路径穿越
    try:
        rel = Path(clean.lstrip("/"))
        target = (WEB_DIST_DIR / rel).resolve()
        target.relative_to(WEB_DIST_DIR.resolve())
    except (ValueError, OSError):
        handler._send_json({"ok": False, "error": "禁止访问"}, 403)
        return True
    if target.is_dir():
        target = target / "index.html"
    if target.is_file():
        content_type = (_CONTENT_TYPES.get(target.suffix.lower())
                        or mimetypes.guess_type(target.name)[0]
                        or "application/octet-stream")
        _send_file(handler, target, content_type)
        return True
    # 前端 SPA 路由兜底：仅对导航请求(Accept: text/html)回退 index.html；
    # 资源请求(script/fetch)与 /api 路径返回真实 404，避免 404 被吞成 HTML
    accept = handler.headers.get("Accept", "")
    if "text/html" in accept and not clean.startswith("/api"):
        target = (WEB_DIST_DIR / "index.html").resolve()
        if target.is_file():
            _send_file(handler, target, "text/html; charset=utf-8")
            return True
    return False


# ─── HTTP Server ───

api = APIHandler()


class AgentHTTPHandler(BaseHTTPRequestHandler):
    """API 路由处理器（前端与 API 同源托管，无需 CORS 头）"""

    def log_message(self, format, *args):
        logger.debug("HTTP {} {}", self.command, args[0] if args else "")

    def _send_json(self, data: dict, status: int = 200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(length) if length else b""

    def do_GET(self):
        path = urlparse(self.path).path
        routes = {
            "/api/ping": lambda: {"ok": True, "time": datetime.now().isoformat()},
            "/api/config": lambda: api.config(),
        }
        handler = routes.get(path)
        if handler:
            return self._send_json(handler())
        # 非 API 路径 → 尝试托管 web/dist 前端页面
        if _serve_static(self, path):
            return
        return self._send_json({"ok": False, "error": f"未知接口: {path}"}, 404)

    def do_POST(self):
        path = urlparse(self.path).path
        body = self._read_body()

        if path == "/api/voice/transcribe":
            return self._send_json(api.voice_transcribe(body))

        try:
            params = json.loads(body.decode("utf-8")) if body else {}
        except (json.JSONDecodeError, UnicodeDecodeError):
            return self._send_json({"ok": False, "error": "无效 JSON"}, 400)

        routes = {
            "/api/ai/chat": lambda: api.ai_chat(params),
        }
        handler = routes.get(path)
        if handler:
            return self._send_json(handler())
        return self._send_json({"ok": False, "error": f"未知接口: {path}"}, 404)


def start_server(host: str = "", port: int = 0, open_browser: bool = True):
    host = host or cfg("server.host", "127.0.0.1")
    port = port or cfg("server.port", 8520)
    open_browser = open_browser and cfg("server.open_browser", True)

    ensure_dirs()
    server = HTTPServer((host, port), AgentHTTPHandler)
    url = f"http://{host}:{port}"
    if WEB_DIST_DIR.is_dir():
        logger.info("服务已启动: {} （前端已构建，直接访问即可）", url)
    else:
        logger.info("服务已启动: {} （未检测到 web/dist，前端请用 npm run dev 或先构建）", url)

    if open_browser:
        import webbrowser
        target = f"http://{host}:{port}"
        threading.Thread(target=lambda: (time.sleep(1), webbrowser.open(target)), daemon=True).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("服务已停止")
        server.shutdown()
```

- [ ] **Step 3: 验证**

Run: `python -c "import main, server; print('imports ok')"`
Expected: `imports ok`

Run（启动后冒烟）：
```bash
cd "F:/projects/ai/InfiniteLogicAssistant"
python main.py serve &
sleep 3
curl -s http://127.0.0.1:8520/api/ping
echo
curl -s http://127.0.0.1:8520/api/config
echo
curl -s http://127.0.0.1:8520/api/ai/chat -X POST -H "Content-Type: application/json" -d '{"messages":[{"role":"user","content":"hi"}]}'
echo
curl -s http://127.0.0.1:8520/api/emails -o /dev/null -w "%{http_code}"
echo
```
Expected:
- ping → `{"ok": true, "time": ...}`
- config → 含 `llm_available`/`asr_available`/`wake_word`/`vad`，无 `features`
- ai/chat → LLM 未配置时 `{"ok": false, "error": "LLM 未配置"}`（未设 key 时）；有 key 则返回文本
- emails → 404
- 响应头**无** `Access-Control-Allow-Origin`

结束服务：`kill %1`（bash）或按 Ctrl+C。

- [ ] **Step 4: 提交**

```bash
git add main.py server.py
git commit -m "refactor: 服务精简 — 移除消息/AI 高级端点与 CORS，仅保留 ping/config/ai-chat/voice-transcribe"
```

---

### Task 6: 删除死代码 + 清理数据/依赖

**Files:**
- 删除: `core/mail_api.py`、`core/mail_sender.py`、`core/mail_browser.py`、`core/monitor.py`、`core/notify.py`、`core/models.py`、`core/user_id.py`、`core/原单位.py`
- 删除: `scripts/show_notification.ps1`、`scripts/libs/gmssl-*.whl`、`scripts/libs/pycryptodomex-*.whl`
- 删除: `data/read_state.json`、`data/downloads/`、`data/monitor_state.json`、`data/monitor.lock`、`data/agent.log`（运行后自动重建）
- Rewrite: `requirements.txt`

**Interfaces:**
- Consumes: Task 2-5 已删除对上述模块的引用。
- Produces: `requirements.txt` 仅含 requests/pyyaml/loguru。

- [ ] **Step 1: 重写 requirements.txt**

```
# 无限逻辑·语音助手 依赖
# 离线安装: python -m pip install --no-index --find-links=scripts\libs -r requirements.txt

requests>=2.28.0
pyyaml>=6.0
loguru>=0.7.0
```

- [ ] **Step 2: 删除文件**

```bash
cd "F:/projects/ai/InfiniteLogicAssistant"
rm -f core/mail_api.py core/mail_sender.py core/mail_browser.py core/monitor.py core/notify.py core/models.py core/user_id.py core/原单位.py
rm -f scripts/show_notification.ps1
rm -f scripts/libs/gmssl-*.whl scripts/libs/pycryptodomex-*.whl
rm -f data/read_state.json data/monitor_state.json data/monitor.lock data/agent.log
rm -rf data/downloads
```

（注意：`core/__pycache__` 中旧编译产物一并清理，避免陈旧字节码干扰验证：`rm -rf core/__pycache__ core/llm/__pycache__ core/voice/__pycache__`）

- [ ] **Step 3: 验证**

Run: `python -c "import main, server; from core.config import get_config; print('ok')"`
Expected: `ok`

Run（全库残留扫描）:
```bash
git grep -n -iE "mail_api|mail_sender|mail_browser|core\.models|core\.user_id|core\.notify|core\.monitor|core\.原单位|原单位|加密|sensevoice|kokoro|show_notification"
```
Expected: 无输出（docs/ 与 web/node_modules 外的全库）。

Run: `ls scripts/libs`
Expected: 仅剩 certifi、charset_normalizer、colorama、idna、loguru、pyyaml、requests、urllib3、win32_setctime 的 wheel。

- [ ] **Step 4: 提交**

```bash
git add -u core scripts requirements.txt
git add core/config.py core/llm core/voice main.py server.py   # 若仍为 untracked，确保入库
git commit -m "chore: 清理消息/网络死代码、离线依赖与运行时数据"
```

（说明：在新仓库中，被删文件从未被跟踪，git 不会记录删除 diff；此提交实际入库 requirements.txt 与前端未提交部分以外的清理结果。若 `git add -u` 无内容，直接提交 requirements.txt 即可。）

---

### Task 7: 前端去消息化 + 单页化

**Files:**
- 删除: `web/src/components/AppHeader.vue`、`Sidebar.vue`、`MailList.vue`、`MailDetail.vue`、`ComposeForm.vue`、`SettingsPanel.vue`
- Rewrite: `web/src/App.vue`、`web/src/composables/useApi.ts`、`web/src/api.ts`、`web/src/types.ts`、`web/src/styles/app.css`
- Modify: `web/index.html`（标题）、`web/src/composables/useAssistant.ts`、`web/src/components/FloatingAssistant.vue`
- 保留: `web/src/main.ts`、`web/src/audio.ts`、`web/src/types/vosk.d.ts`、`web/src/types/vue-shims.d.ts`、`web/public/lib/*`

**Interfaces:**
- Consumes: 后端 `/api/ping`、`/api/config`、`/api/ai/chat`、`/api/voice/transcribe`。
- Produces: `useAssistant()` 暴露 `init/destroy/toggleWake/clearMessages/state/stateLabel/stateColor/messages/expanded/wakeEnabled/partialText/statusLine`，不再有 `setOpenComposeHandler/setNavigateTabHandler/setRefreshEmailsHandler`；`api` 暴露 `ping/getConfig/transcribe`。

- [ ] **Step 1: 全文替换 web/src/api.ts**

新内容：

```typescript
import type { ConfigResponse, PingResponse, TextResponse } from './types'
import { blobToWavBase64 } from './audio'

// ─── HTTP 封装 ───

const BASE = '/api'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, options)
  if (!res.ok) {
    // 尝试解析 JSON 错误体，失败则用 HTTP 状态码
    let message = `HTTP ${res.status}`
    try {
      const err = await res.json()
      if (err?.error) message = err.error
    } catch { /* not JSON */ }
    throw new Error(message)
  }
  const data = await res.json()
  return data as T
}

async function get<T>(path: string): Promise<T> {
  return request<T>(path)
}

async function post<T>(path: string, data?: unknown): Promise<T> {
  return request<T>(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: data ? JSON.stringify(data) : undefined,
  })
}

// ─── API 端点 ───

export const api = {
  ping: () => get<PingResponse>('/ping'),
  getConfig: () => get<ConfigResponse>('/config'),

  // 语音
  transcribe: async (blob: Blob): Promise<TextResponse> => {
    const base64Wav = await blobToWavBase64(blob)
    return post<TextResponse>('/voice/transcribe', { audio_base64: base64Wav })
  },
}
```

- [ ] **Step 2: 全文替换 web/src/types.ts**

新内容：

```typescript
export interface ApiResponse {
  ok: boolean
  error?: string
}

export interface PingResponse extends ApiResponse {
  time: string
}

export interface ConfigResponse extends ApiResponse {
  llm_available: boolean
  llm_profile: string
  asr_available: boolean
  asr_profile: string
  wake_word: WakeWordConfig
  vad: VadConfig
}

export interface TextResponse extends ApiResponse {
  text: string
}

export interface WakeWordConfig {
  enabled: boolean
  keyword: string
  sensitivity: number
  model_path: string
}

export interface VadConfig {
  silence_threshold: number
  silence_duration_ms: number
  max_duration_ms: number
}
```

- [ ] **Step 3: 全文替换 web/src/composables/useApi.ts**

新内容：

```typescript
import { ref } from 'vue'
import { api } from '../api'
import type { ConfigResponse } from '../types'

/**
 * 配置管理 composable（读取 /api/config）
 */
export function useConfig() {
  const config = ref<ConfigResponse | null>(null)

  async function initConfig() {
    try {
      config.value = await api.getConfig()
    } catch (e) {
      console.error('initConfig', e)
    }
  }

  return { config, initConfig }
}
```

- [ ] **Step 4: 全文替换 web/src/App.vue**

新内容：

```vue
<template>
  <div class="page">
    <div class="hero">
      <h1 class="title">无限逻辑 · 语音助手</h1>
      <p class="subtitle">唤醒词：小逻小逻</p>
    </div>
    <FloatingAssistant :asst="asst" />
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'

import FloatingAssistant from './components/FloatingAssistant.vue'
import { useConfig } from './composables/useApi'
import { useAssistant } from './composables/useAssistant'

const app = useConfig()
const asst = useAssistant()

onMounted(async () => {
  await app.initConfig()
  asst.init()
})

onUnmounted(() => {
  asst.destroy()
})
</script>

<style scoped>
.page {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: radial-gradient(ellipse at top, #1e293b 0%, #0f172a 60%, #020617 100%);
  color: #e2e8f0;
  overflow: hidden;
  user-select: none;
}
.hero {
  text-align: center;
  pointer-events: none;
}
.title {
  font-size: clamp(2rem, 6vw, 3.2rem);
  font-weight: 700;
  letter-spacing: 0.04em;
  margin: 0 0 0.75rem;
  background: linear-gradient(135deg, #a5b4fc 0%, #67e8f9 50%, #6ee7b7 100%);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}
.subtitle {
  font-size: clamp(0.95rem, 2vw, 1.15rem);
  color: #94a3b8;
  margin: 0;
  letter-spacing: 0.35em;
}
</style>
```

- [ ] **Step 5: 全文替换 web/src/styles/app.css**

新内容：

```css
/* 无限逻辑·语音助手 — 全局基础样式 */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
html, body, #app { height: 100%; }
body {
  font-family: "Microsoft YaHei", "PingFang SC", -apple-system, BlinkMacSystemFont, sans-serif;
  background: #020617;
  color: #e2e8f0;
  -webkit-font-smoothing: antialiased;
}
```

- [ ] **Step 6: 修改 web/index.html 标题**

将 `<title>AI 语音助手</title>` 改为 `<title>无限逻辑·语音助手</title>`。

- [ ] **Step 7: 修改 web/src/composables/useAssistant.ts**

(1) TOOLS 数组（原 34-55 行）替换为：

```typescript
// ─── 可用工具（扩展点：在此新增工具描述，并在 handleAction 中实现对应分支）───
const TOOLS = [
  {
    name: 'chat',
    description: '纯对话，无需调用工具。args: reply(回复内容)',
  },
]
```

(2) SYSTEM_PROMPT（原 58-73 行）替换为：

```typescript
const SYSTEM_PROMPT = `你是一个智能语音助手，名字叫"小逻"。用中文回复，简洁友好（一般不超过3句话）。

你的能力：
1. 日常对话 — 打招呼、解答问题、闲聊
2. 将来可扩展工具调用（如查信息、打开网页等）

当用户需要执行操作时，返回 JSON（不要加 markdown 代码块）：
{"action":"<工具名>","args":{...},"reply":"<对用户说的话>"}

如果是纯聊天，返回：
{"action":"chat","args":{"reply":"<回复>"},"reply":"<回复>"}

可用工具：
${TOOLS.map(t => `- ${t.name}: ${t.description}`).join('\n')}`
```

(3) 删除 `onRefreshEmails` 声明与其 setter（原 100 行 `let onRefreshEmails...`、108-110 行 `setRefreshEmailsHandler` 函数、662 行返回对象中的 `setRefreshEmailsHandler,`）。

(4) `handleAction` 的 `switch (action)`（原 371-447 行）替换为仅保留 chat + 默认分支：

```typescript
    try {
      switch (action) {
        case 'chat': {
          toolResult = args.reply || reply || ''
          toolCalls[0].status = 'done'
          toolCalls[0].result = toolResult
          break
        }
        default: {
          // 未知操作 — 降级为对话回复
          toolResult = reply || `收到，正在处理...`
          toolCalls[0].status = 'done'
          toolCalls[0].result = toolResult
        }
      }
    } catch (e: any) {
      toolCalls[0].status = 'failed'
      toolCalls[0].result = e.message || '执行失败'
    }
```

(5) 原 310 行注释"附加工具执行结果（含 mail_id 等）…"改为"附加工具执行结果，供后续指令引用"。

(6) 检查：文件内不得再出现 `send_email` / `check_inbox` / `get_email_detail` / `open_compose` / `sendEmail` / `getEmails` / `getEmailDetail` / `onRefreshEmails`。

- [ ] **Step 8: 修改 web/src/components/FloatingAssistant.vue**

(1) 模板：
- 52 行 `<span class="handle-title">AI 助手</span>` → `<span class="handle-title">小逻</span>`
- 82、92 行 `说 <strong>"小邮小邮"</strong> 唤醒我` → `说 <strong>"小逻小逻"</strong> 唤醒我`
- 93 行 `你可以说："帮我发消息给张三…"` → 删除该行（或改为 `你可以说："帮我查一下今天的天气"`）
- 138 行写信按钮 `<button class="act-btn" @click="onOpenCompose" title="写信">✉</button>` → 删除整行

(2) script：
- 154-156 行 `emit` 声明 `(e: 'open-compose', ...)` → 删除，并删除第 153 行 `const emit = defineEmits<{...}>()` 整块
- 263-272 行 `toolIcon` map 中删除 `send_email` / `check_inbox` / `get_email_detail` / `open_compose` 四行，仅留 `chat: '💬'`
- 274-283 行 `toolLabel` map 中删除四行，仅留 `chat: '对话'`
- 347 行 `miniRole` 中 `'小邮'` → `'小逻'`
- 405-407 行 `function onOpenCompose() {...}` → 删除整函数

(3) 检查：文件内不得再出现 `open_compose` / `open-compose` / `小邮` / `写信`。

- [ ] **Step 9: 删除 6 个旧组件**

```bash
cd "F:/projects/ai/InfiniteLogicAssistant/web"
rm -f src/components/AppHeader.vue src/components/Sidebar.vue src/components/MailList.vue src/components/MailDetail.vue src/components/ComposeForm.vue src/components/SettingsPanel.vue
```

- [ ] **Step 10: 验证（类型检查 + 构建）**

```bash
cd "F:/projects/ai/InfiniteLogicAssistant/web"
npm run build
```
Expected: `vue-tsc` 无类型错误，vite 构建成功，产物在 `web/dist/`。

Run（前端残留扫描）:
```bash
git grep -n -iE "mail|email|compose|inbox|unread|open_compose|sendEmail|getEmails" -- web/src
```
Expected: 无输出。

- [ ] **Step 11: 提交**

```bash
git add web
git commit -m "refactor: 前端单页化 — 移除 消息UI，仅保留悬浮语音助手，标题/文案改为无限逻辑·小逻"
```

---

### Task 8: 文档与脚本重写

**Files:**
- Rewrite: `README.md`、`config.yaml`、`config.yaml.example`、`start.bat`、`install_deps.bat`、`package_deploy.bat`
- Modify: `.gitignore`（追加注释头，规则基本不动）

**Interfaces:**
- Consumes: Task 2 配置结构、Task 5 命令（serve/test）。
- Produces: 用户可读的配置模板与启动脚本；`config.yaml` 与 `config.yaml.example` 内容一致（示例即模板）。

- [ ] **Step 1: 重写 config.yaml.example 与 config.yaml（内容一致）**

```yaml
# 无限逻辑·语音助手 — 配置
# 支持 ${ENV_VAR} 环境变量插值

llm:
  # 当前生效的 LLM profile 名（对应 profiles 下的键名）；改 active 切换服务商
  active: deepseek
  profiles:
    deepseek:                 # OpenAI 兼容（示例）
      provider: openai
      endpoint: "https://api.deepseek.com"
      api_key: "${LLM_API_KEY}"
      model: "deepseek-chat"
      chat_path: "/v1/chat/completions"
      max_tokens: 4096
      temperature: 0.7
      timeout: 60
    openai:                   # OpenAI 官方
      provider: openai
      endpoint: "https://api.openai.com/v1"
      api_key: "${OPENAI_API_KEY}"
      model: "gpt-4o-mini"
      chat_path: "/v1/chat/completions"
      max_tokens: 4096
      temperature: 0.7
      timeout: 60
    qwen:                     # 通义千问（DashScope 兼容模式）
      provider: openai
      endpoint: "https://dashscope.aliyuncs.com/compatible-mode/v1"
      api_key: "${QWEN_API_KEY}"
      model: "qwen-plus"
      chat_path: "/v1/chat/completions"
      max_tokens: 4096
      temperature: 0.7
      timeout: 60

voice:
  # 离线语音唤醒（浏览器端 Vosk WASM，关键词可任意改）
  wake_word:
    enabled: true
    keyword: "小逻小逻"
    sensitivity: 0.5
    model_path: "models/vosk-model-small-cn-0.22"
  # 静音检测（自动停止录音）
  vad:
    silence_threshold: 0.02
    silence_duration_ms: 1500
    max_duration_ms: 10000
  # 在线 ASR 语音转文字（OpenAI 兼容；endpoint/model 需自填）
  asr:
    active: openai
    profiles:
      openai:
        provider: openai
        endpoint: ""                    # 例: https://api.siliconflow.cn/v1
        api_key: "${ASR_API_KEY}"
        model: ""                       # 例: FunAudioLLM/SenseVoiceSmall
        language: "zh"
        timeout: 30
        chat_path: "/v1/chat/completions"
  # TTS（可选；另有浏览器端 SpeechSynthesis 播报，默认关闭）
  tts:
    enabled: false
    profiles:
      openai:
        provider: openai
        endpoint: ""                    # 例: https://api.openai.com/v1
        api_key: "${TTS_API_KEY}"
        model: "tts-1"
        voice: "alloy"
        timeout: 30
        chat_path: "/v1/audio/speech"

server:
  host: "127.0.0.1"
  port: 8520
  open_browser: true
```

- [ ] **Step 2: 重写 start.bat**

```bat
@echo off
setlocal EnableExtensions
title 无限逻辑·语音助手
cd /d "%~dp0"

echo ============================================
echo   无限逻辑·语音助手 - one-click start
echo ============================================
echo.

REM ---- 1. Check Python ----
python --version >nul 2>&1
if errorlevel 1 goto :no_python

REM ---- 2. Check / install dependencies (offline-first) ----
python -c "import yaml, loguru, requests" >nul 2>&1
if not errorlevel 1 goto :deps_ok
echo [INFO] Missing dependencies, installing offline from scripts\libs ...
python -m pip install --no-index --find-links=scripts\libs -r requirements.txt --disable-pip-version-check
if not errorlevel 1 goto :deps_ok
echo [WARN] Offline install failed, trying online source ...
python -m pip install -r requirements.txt
python -c "import yaml, loguru, requests" >nul 2>&1
if errorlevel 1 goto :deps_fail

:deps_ok

REM ---- 3. Connectivity test (LLM / ASR) ----
echo [TEST] Checking LLM / ASR connectivity ...
python main.py test
if errorlevel 1 goto :test_warn
echo [TEST] LLM / ASR connectivity OK.
goto :dist_check

:test_warn
echo [WARN] LLM / ASR connectivity test failed - see data/agent.log.
echo   Starting anyway (services will report errors when used).

:dist_check
REM ---- 4. Check frontend build ----
if exist "web\dist\index.html" goto :dist_ok
echo [INFO] No web\dist build detected.
echo   Option A: run "npm run build", then served by this server
echo   Option B: dev mode, run "cd web && npm run dev" for port 5173

:dist_ok

REM ---- 5. Start ----
echo.
echo [START] python main.py serve
echo   Browser will open http://127.0.0.1:8520
echo   Press Ctrl+C to stop
echo.
python main.py serve

pause
exit /b 0

:no_python
echo [ERROR] Python not found. Please install Python 3.10+ and add it to PATH.
pause
exit /b 1

:deps_fail
echo [ERROR] Dependency install failed. Check the scripts\libs folder or network access.
pause
exit /b 1
```

- [ ] **Step 3: 重写 install_deps.bat**

```bat
@echo off
setlocal EnableExtensions
title 无限逻辑·语音助手 - offline install
cd /d "%~dp0"

echo ============================================
echo   无限逻辑·语音助手 - offline dependency install
echo ============================================
echo.

echo [1/2] Installing Python dependencies from scripts\libs ...
python -m pip install --no-index --find-links=scripts\libs -r requirements.txt --disable-pip-version-check
if errorlevel 1 goto :fallback

echo [2/2] Dependencies installed.
echo.
echo   Done. Edit config.yaml then run: python main.py serve
pause
exit /b 0

:fallback
echo [WARN] Offline install failed, trying online source ...
python -m pip install -r requirements.txt
if errorlevel 1 goto :fail
echo [2/2] Dependencies installed via online source.
pause
exit /b 0

:fail
echo [ERROR] Dependency install failed. Check network or scripts\libs folder.
pause
exit /b 1
```

- [ ] **Step 4: 重写 package_deploy.bat**

将原文件全文中的 ` AI Voice Agent- build deploy package` 等标题替换为 `无限逻辑·语音助手 - build deploy package`；末尾 NOTE 行（原 64-65 行）改为：

```bat
echo NOTE: deploy\config.yaml contains API keys. Delete that file before sharing the package externally.
```

其余 robocopy/zip 逻辑保持不变。

- [ ] **Step 5: 重写 README.md**

```markdown
# 无限逻辑·语音助手

基于浏览器 Vosk 离线唤醒词的语音对话助手。纯浏览器 + 轻量 Python 后端，
OpenAI 兼容接口，支持网络/外网任意部署。

## 功能

| 模块 | 功能 |
|------|------|
| 悬浮球助手 | 右下角可拖拽悬浮球，语音对话 + 聊天气泡面板 + 迷你播放条 |
| 语音唤醒 | 离线 Vosk WASM 唤醒词"小逻小逻"（含同音字变体匹配），纯浏览器运行 |
| 语音输入 | ASR（OpenAI 兼容）转文字，自动填入 |
| AI 对话 | LLM（OpenAI 兼容：DeepSeek / OpenAI / 通义…）多 profile 切换 |
| 语音播报 | 浏览器 SpeechSynthesis API 播报助手回复 |

## 快速开始

```bash
# 1. 安装 Python 依赖
pip install -r requirements.txt
# 网络离线: 双击 install_deps.bat（使用 scripts/libs/ 下的离线 wheel）

# 2. 配置
cp config.yaml.example config.yaml
# 编辑 config.yaml 填入 LLM / ASR endpoint 和凭据（${ENV_VAR} 支持环境变量）

# 3. 启动（一键：前端 + 后端）
python main.py serve                  # 浏览器自动打开 http://127.0.0.1:8520
```

`python main.py serve` 同时提供前端页面（`web/dist`）与 `/api/*` 接口，打开一个端口即可使用。

**一键启动脚本**（Windows，含 LLM/ASR 连通性测试）：

```bat
start.bat
```

> 若 `web/dist` 未构建，前端需另行构建：

```bash
cd web
npm install
npm run build        # 产物在 web/dist/，serve 即托管该目录
```

开发模式（前端热更新）：

```bash
cd web
npm install && npm run dev     # 访问 http://127.0.0.1:5173 （vite 代理 /api → 8520）
```

## 语音助手使用

启动前端后，页面右下角出现可拖拽的悬浮球：

- **双击悬浮球** 或点击面板内"👂 开启"启动语音唤醒
- 说 **"小逻小逻"**（含同音字变体）激活录音
- 录音 **VAD 静音检测自动停止**（默认静音 1.5s），最长 10s 上限
- 录音经 ASR 转文字 → LLM 对话 → 结果用浏览器 TTS 语音播报

唤醒词、静音阈值等可在 `config.yaml` 的 `voice.wake_word` / `voice.vad` 中调整。

## API 端点

```
GET  /api/ping
GET  /api/config
POST /api/ai/chat          # 通用 LLM 对话（悬浮球助手使用）
POST /api/voice/transcribe # JSON 体传 audio_base64（16kHz mono WAV）
```

## 命令

```
start.bat                   一键启动（Windows，含 LLM/ASR 连通性测试）
python main.py serve        启动 Web 服务（前端 + 后端 API）
python main.py test         测试 LLM / ASR 连通性
```

## 配置

`config.yaml.example` 为完整模板，支持 `${ENV_VAR}` 环境变量插值。核心段：

- `llm`：OpenAI 兼容 LLM，多 profile（deepseek / openai / qwen），改 `active` 切换。
- `voice.asr`：OpenAI 兼容 ASR（endpoint/model 自填，DeepSeek 无 ASR 服务）。
- `voice.tts`：可选后端 TTS；默认用浏览器 SpeechSynthesis 播报。
- `voice.wake_word` / `voice.vad`：唤醒词与静音检测参数。

## 目录结构

```
无限逻辑-语音助手/
├── main.py                   入口 (serve / test)
├── server.py                 HTTP 服务（/api/* + 托管 web/dist 前端）
├── start.bat / install_deps.bat / package_deploy.bat
├── config.yaml.example       配置模板
├── requirements.txt          Python 依赖
├── core/
│   ├── config.py             配置加载（YAML + ${ENV} 插值 + 多 profile）
│   ├── logger.py             loguru 日志（控制台 + data/agent.log）
│   ├── llm/__init__.py       LLM 客户端（OpenAI 兼容）
│   └── voice/__init__.py     ASR / TTS（OpenAI 兼容）
├── scripts/libs/             离线 wheel 包
├── web/                      Vue3 + Vite + TS 前端
│   ├── public/lib/vosk.js    Vosk WASM 语音唤醒引擎
│   ├── public/lib/wake-word.js
│   ├── public/models/vosk-model-small-cn-0.22/
│   └── src/
│       ├── App.vue / main.ts
│       ├── api.ts / audio.ts / types.ts
│       ├── components/FloatingAssistant.vue
│       └── composables/useApi.ts / useAssistant.ts
└── data/                     运行时数据（agent.log）
```

## 工具扩展

悬浮球工具调用框架已预留：在 `web/src/composables/useAssistant.ts` 的 `TOOLS`
数组中登记工具描述，并在 `handleAction` 中实现对应分支即可。当前仅内置 `chat` 工具。
```

- [ ] **Step 6: 修改 .gitignore 顶部注释**

在原首行 `# 敏感配置（含 API Key）` 前增加一行：

```gitignore
# 无限逻辑·语音助手
```

其余规则保持不动。

- [ ] **Step 7: 验证**

Run: `git grep -n -iE " AI VoiceAgent|AI 消息|AI Voice|语音助手|收件箱|收件箱" -- ':!docs'`
Expected: 无输出（全库产品文案已统一）。

Run: `git grep -n -iE "原单位|加密|user_id|send_email|open_compose|check_inbox|get_email_detail|mailSendDate|queryEmail" -- ':!docs' ':!web/public'`
Expected: 无输出（web/public 下的 vosk.js 为第三方大文件，豁免）。

- [ ] **Step 8: 提交**

```bash
git add README.md config.yaml config.yaml.example start.bat install_deps.bat package_deploy.bat .gitignore
git commit -m "docs: 重写为无限逻辑·语音助手 — 外网配置模板、启动脚本与使用说明"
```

---

### Task 9: 最终验收

**Files:**
- 验证 + 修复残留 + 最终提交

- [ ] **Step 1: 全库残留扫描**

```bash
cd "F:/projects/ai/InfiniteLogicAssistant"
git grep -n -iE "原单位|加密|网络|network|mail|email|user_id|notify|monitor|sensevoice|kokoro|queryEmail" -- ':!docs' ':!web/public' ':!web/node_modules'
```
Expected: 无输出。若命中，先修复再继续。

- [ ] **Step 2: 后端冒烟**

```bash
python -c "import main, server; from core.config import get_config; print('backend imports ok')"
python main.py serve &
sleep 3
curl -s http://127.0.0.1:8520/api/ping
echo
curl -s http://127.0.0.1:8520/api/config
echo
curl -s http://127.0.0.1:8520/ -o /dev/null -w "首页 HTTP %{http_code}\n"
curl -s http://127.0.0.1:8520/api/emails -o /dev/null -w "未知接口 HTTP %{http_code}\n"
```
Expected: ping/config 返回 JSON；首页 200（若 web/dist 已构建）；未知接口 404。结束后 `kill %1`。

- [ ] **Step 3: 前端类型检查 + 构建**

```bash
cd "F:/projects/ai/InfiniteLogicAssistant/web"
npm run build
```
Expected: `vue-tsc` 无错误，vite 构建成功。

- [ ] **Step 4: 依赖文件清单核对**

```bash
ls scripts/libs
```
Expected: 无 gmssl / pycryptodomex。

- [ ] **Step 5: 提交残留修复（如有）并确认 git 状态**

```bash
cd "F:/projects/ai/InfiniteLogicAssistant"
git status
git log --oneline
```
Expected: 工作区干净；log 从 Task 1 的 init 到 Task 8 依次排列，无旧消息提交。

---

## Self-Review

**Spec coverage:**
- 删除消息/网络模块 → Task 6
- 保留语音链路 → Task 3/4/7
- LLM=DeepSeek、ASR/TTS OpenAI 兼容 → Task 2/3/4
- 唤醒词"小逻小逻" → Task 7/8
- 极简单页 + 悬浮球 → Task 7
- 产品名"无限逻辑·语音助手"，目录不变 → Task 8/1
- git 重新初始化 → Task 1
- API 4 端点 + 去 CORS → Task 5
- 依赖精简 → Task 6
- 验收（grep/npm build/冒烟）→ Task 9

**Type consistency:** `_call(messages)` 签名在 Task 3 定义、Task 5 的 server.py 使用；`transcribe_base64(b64,"wav")` Task 4 定义、Task 5 使用；`resolve_llm_profile()[0]` 等 Task 2 定义、Task 5 使用；前端 `api.transcribe` / `getConfig` / `useConfig` / `initConfig` 在 Task 7 各文件间一致。FloatingAssistant 用到的 `asst.state.value / stateColor / stateLabel / messages / toggleWake / clearMessages / init / destroy / partialText / statusLine` 均在 useAssistant 保留，无删减。

**已知取舍：** 后端 `LLMClient._call` 与前端 `handleLLM` 的 JSON 工具解析仍保留（通用工具扩展框架）；`_play_audio` 用 `start` 命令（Windows 专属，可选 TTS 功能，保留现状）。
