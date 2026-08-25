# -*- coding: utf-8 -*-
"""配置校验 — Settings 强类型加载后的语义检查（detection 域）

pydantic 已保证类型/范围/枚举；这里做跨字段规则：
非 localhost 绑定必须 token、profile 缺失 / 未配密钥等。
"""
from dataclasses import dataclass, field
from typing import Any

from core.config import Settings

_LOCALHOST = ("", "127.0.0.1", "localhost", "::1")


@dataclass
class Issue:
    level: str  # error / warning / info
    key: str
    message: str

    def as_dict(self) -> dict:
        return {"level": self.level, "key": self.key, "message": self.message}


@dataclass
class ConfigHealth:
    ok: bool
    issues: list[Issue] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"ok": self.ok, "issues": [i.as_dict() for i in self.issues]}


def _active_profile(section: Any) -> tuple[str, Any] | None:
    """返回 (profile_name, profile)；无 profile 返回 None。"""
    if not section.profiles:
        return None
    active = section.active or next(iter(section.profiles))
    if active not in section.profiles:
        active = next(iter(section.profiles))
    return active, section.profiles[active]


def validate(settings: Settings) -> ConfigHealth:
    issues: list[Issue] = []

    # server：非 localhost 绑定必须 api_token（否则拒绝启动）
    host = settings.server.host
    if host not in _LOCALHOST and not settings.server.api_token:
        issues.append(Issue("error", "server.api_token",
                            "非 localhost 绑定必须设置 api_token（否则拒绝启动）"))

    # LLM / ASR / TTS：profile 完整性 + 密钥
    for key, section in (("llm", settings.llm), ("asr", settings.voice.asr), ("tts", settings.voice.tts)):
        active = _active_profile(section)
        if active is None:
            issues.append(Issue("warning", key, "未配置任何 profile"))
            continue
        name, p = active
        if not (p.endpoint and p.model):
            issues.append(Issue("warning", f"{key}.profiles.{name}", "endpoint 或 model 缺失，服务不可用"))
        elif not p.api_key:
            issues.append(Issue("warning", f"{key}.profiles.{name}", "未配置 api_key（config.secrets.yaml 或环境变量）"))

    if not settings.voice.tts.enabled:
        issues.append(Issue("info", "voice.tts.enabled", "TTS 未启用（默认浏览器本地语音播报）"))

    return ConfigHealth(ok=all(i.level != "error" for i in issues), issues=issues)
