# -*- coding: utf-8 -*-
"""配置校验 — Settings 强类型加载后的语义检查（detection 域）。Config validation — semantic checks after strong-typed Settings loading (detection domain).

pydantic 已保证类型/范围/枚举；这里做跨字段规则：
pydantic already guarantees types/ranges/enums; here we enforce cross-field rules:
非 localhost 绑定必须 token、profile 缺失 / 未配密钥等。
non-localhost binds require a token, missing profiles / unset API keys, etc.
"""
import fnmatch
from dataclasses import dataclass, field
from typing import Any

from core.config import Settings
from core.tools.base import TOOLS  # 从 base 导入，避免 core.tools.__init__ 循环

_LOCALHOST = ("", "127.0.0.1", "localhost", "::1")


@dataclass
class Issue:
    """一条配置问题记录。A single configuration issue record."""

    level: str  # error / warning / info
    key: str
    message: str

    def as_dict(self) -> dict:
        """转为可序列化字典。Convert to a serializable dict."""
        return {"level": self.level, "key": self.key, "message": self.message}


@dataclass
class ConfigHealth:
    """配置健康度汇总。Aggregated configuration health summary."""

    ok: bool
    issues: list[Issue] = field(default_factory=list)

    def as_dict(self) -> dict:
        """转为可序列化字典（含每条问题）。Convert to a serializable dict (including each issue)."""
        return {"ok": self.ok, "issues": [i.as_dict() for i in self.issues]}


def _active_profile(section: Any) -> tuple[str, Any] | None:
    """返回 (profile_name, profile)；无 profile 返回 None。Return (profile_name, profile); None if there is no profile."""
    if not section.profiles:
        return None
    active = section.active or next(iter(section.profiles))
    if active not in section.profiles:
        active = next(iter(section.profiles))
    return active, section.profiles[active]


def validate(settings: Settings) -> ConfigHealth:
    """执行配置语义校验并汇总问题。Run semantic config validation and aggregate issues."""
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

    # permissions：规则 match 必须至少命中一个已注册工具，否则是拼写错误会被静默忽略
    # （既不报错也不生效），用户会以为策略已生效。
    # permissions: a rule's match must hit at least one registered tool; otherwise a typo
    # is silently ignored (neither erroring nor taking effect) and the user believes the
    # policy is in force.
    tool_names = [t["name"] for t in TOOLS.meta()]
    for rule in settings.permissions.rules:
        if not any(fnmatch.fnmatchcase(n, rule.match) for n in tool_names):
            issues.append(Issue(
                "warning", f"permissions.rules[{rule.match}]",
                f"规则 match「{rule.match}」匹配不到任何已注册工具，该规则不会生效（是否拼写错误？）",
            ))

    return ConfigHealth(ok=all(i.level != "error" for i in issues), issues=issues)
