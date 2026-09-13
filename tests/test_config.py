# -*- coding: utf-8 -*-
"""core/config.py — 密钥优先级 / 新字段 / 设置快照。
Tests core/config.py — API key priority, new fields, and the settings snapshot.
"""
import pytest

import core.config as c


def _mk_profile(**kw) -> dict:
    return {"provider": "openai", "endpoint": "https://x", "model": "m", **kw}


# ─── _profile_api_key 优先级 ───

def test_profile_api_key_env_priority(monkeypatch):
    """验证 profile.api_key_env 指向的环境变量优先于段全局环境变量。Verifies the env var pointed to by profile.api_key_env takes priority over the section-level global env var."""
    monkeypatch.setenv("LLM_API_KEY", "global")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "specific")
    secrets = {"llm": {"api_key": "sec_default", "profiles": {}}}
    # profile.api_key_env 指向的 env 优先
    assert c._profile_api_key("llm", "deepseek", secrets, _mk_profile(api_key_env="DEEPSEEK_API_KEY")) == "specific"
    # 无 api_key_env → 段全局 env
    assert c._profile_api_key("llm", "deepseek", secrets, _mk_profile()) == "global"


def test_profile_api_key_secrets_fallback(monkeypatch):
    """验证无环境变量时按 secrets.profiles 再到段默认值回退。Verifies the fallback from secrets.profiles to the section default when no env var is set."""
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    secrets = {"llm": {"api_key": "sec_default", "profiles": {"deepseek": "sec_ds"}}}
    # secrets.profiles[name] > secrets 段默认
    assert c._profile_api_key("llm", "deepseek", secrets, _mk_profile()) == "sec_ds"
    assert c._profile_api_key("llm", "other", secrets, _mk_profile()) == "sec_default"


def test_inject_secrets_server_token():
    """server.api_token 从 secrets 注入（防回归：曾因插入函数悬空成死代码）。
    Verifies server.api_token is injected from secrets (regression guard: it was once dead code because an inserted function dangled).
    """
    secrets = {
        "llm": {"api_key": "", "profiles": {}}, "asr": {"api_key": "", "profiles": {}},
        "tts": {"api_key": "", "profiles": {}}, "server": {"api_token": "tok"},
    }
    data = {"server": {"host": "0.0.0.0"}}
    c._inject_secrets(data, secrets)
    assert data["server"]["api_token"] == "tok"


def test_inject_secrets_asr_tts_under_voice(monkeypatch):
    """asr/tts 密钥嵌在 voice 段下也必须注入。

    曾只找顶层 data['asr']/data['tts']，而 config.yaml 把它们放在 voice 下，
    导致 ASR/TTS 密钥永远为空（写入 secrets 也不生效 → 401）。
    Verifies ASR/TTS keys nested under the voice section are still injected; previously only top-level data['asr']/data['tts'] were checked, leaving the keys empty (401).
    """
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("MIMO_API_KEY", raising=False)
    monkeypatch.delenv("ASR_API_KEY", raising=False)
    monkeypatch.delenv("TTS_API_KEY", raising=False)
    secrets = {
        "llm": {"api_key": "", "profiles": {}},
        "asr": {"api_key": "", "profiles": {"xiaomi": "tp-key"}},
        "tts": {"api_key": "", "profiles": {"openai": "tts-key"}},
        "server": {"api_token": "tok"},
    }
    data = {
        "llm": {"active": "ds", "profiles": {"ds": {"provider": "openai"}}},
        "voice": {
            "asr": {"active": "xiaomi", "profiles": {"xiaomi": {"provider": "openai", "api_key_env": "MIMO_API_KEY"}}},
            "tts": {"enabled": False, "active": "openai", "profiles": {"openai": {"provider": "openai"}}},
        },
    }
    c._inject_secrets(data, secrets)
    # env 未设（MIMO_API_KEY）→ 落到 secrets.profiles[name]
    assert data["voice"]["asr"]["profiles"]["xiaomi"]["api_key"] == "tp-key"
    assert data["voice"]["tts"]["profiles"]["openai"]["api_key"] == "tts-key"
    # llm 顶层照常
    assert data["llm"]["profiles"]["ds"]["api_key"] == ""


def test_profile_api_key_legacy_warns(monkeypatch, capsys):
    """验证旧式 ${ENV} 写法被弃用并输出迁移提示。Verifies the legacy ${ENV} syntax is deprecated and prints a migration notice."""
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    secrets = {"llm": {"api_key": "", "profiles": {}}}
    assert c._profile_api_key("llm", "deepseek", secrets, _mk_profile(api_key="${LLM_API_KEY}")) == ""
    assert "迁移到 config.secrets.yaml" in capsys.readouterr().out


# ─── Settings 接受新字段 ───

def test_settings_accepts_vendor_presets_and_failover():
    """验证 Settings 接受 vendor_presets 与 models_failover 新字段。Verifies Settings accepts the new vendor_presets and models_failover fields."""
    s = c.Settings(
        vendor_presets={"myllm": c.VendorPreset(kind="llm", label="我的", endpoint="https://x", chat_path="/v1/chat/completions")},
        agent=c.AgentSection(models_failover=["model-b"]),
    )
    assert s.vendor_presets["myllm"].label == "我的"
    assert s.agent.models_failover == ["model-b"]


def test_profile_accepts_vendor_models_compat_api_key_env():
    """验证 LlmProfile 接受 vendor/models/compat/api_key_env 字段。Verifies LlmProfile accepts the vendor, models, compat, and api_key_env fields."""
    prof = c.LlmProfile(
        vendor="deepseek", api_key_env="DEEPSEEK_API_KEY",
        models=["deepseek-chat"], models_path="/v1/models",
        compat={"stream_options": False},
    )
    assert prof.vendor == "deepseek"
    assert prof.models == ["deepseek-chat"]
    assert prof.compat.stream_options is False


def test_compat_defaults_preserve_behavior():
    """验证 CompatConfig 默认值保持原有行为。Verifies CompatConfig defaults preserve the original behavior."""
    assert c.CompatConfig().stream_options is True
    assert c.CompatConfig().max_tokens_field == "max_tokens"


# ─── editable_snapshot：剥 api_key，留新字段 ───

def test_editable_snapshot_keeps_new_fields_strips_key(monkeypatch):
    """验证设置快照保留新字段并剥离 api_key。Verifies the editable snapshot keeps new fields and strips the api_key."""
    settings = c.Settings(llm=c.LlmSection(profiles={
        "ds": c.LlmProfile(vendor="deepseek", api_key_env="DEEPSEEK_API_KEY",
                           models=["deepseek-chat"], compat={"stream_options": False}, api_key="SECRET"),
    }))
    monkeypatch.setattr(c, "get_settings", lambda: settings)
    snap = c.editable_snapshot()
    prof = snap["llm"]["profiles"]["ds"]
    assert "api_key" not in prof
    assert prof["vendor"] == "deepseek"
    assert prof["api_key_env"] == "DEEPSEEK_API_KEY"  # 环境变量名非密钥，可透传
    assert prof["models"] == ["deepseek-chat"]
    assert prof["compat"]["stream_options"] is False  # CompatConfig 默认带 max_tokens_field
    # 密钥状态以 *_set 暴露
    assert snap["llm"]["api_key_set"]["ds"] is True


# ─── permissions 段：工具权限策略 ───


def test_permissions_section_defaults_allow_everything():
    """权限段缺省时**三档全放行、兜底也放行**（2026-09-13 按用户要求改）。

    改前的默认是「read 免询问、write/exec 询问」，那时本用例断言的是旧行为。
    现在全放行意味着无沙箱下的确认闸门默认不生效 —— 收紧靠 `rules`（deny 单调短路）
    或直接改 `tiers`。

    The permissions section defaults to **allow on every tier, fallback included** (changed
    2026-09-13 at the user's request; this case previously asserted read-allowed/write+exec-asked).
    Allow-by-default means the confirmation gate is off by default where there is no sandbox —
    tighten it with `rules` (monotonic deny) or by overriding `tiers`.
    """
    s = c.Settings()
    assert s.permissions.default_action == "allow"
    assert s.permissions.tiers.read == "allow"
    assert s.permissions.tiers.write == "allow"
    assert s.permissions.tiers.exec == "allow"
    assert s.permissions.rules == []


def test_permissions_rules_can_tighten_the_default():
    """默认全放行之后，收紧手段仍然有效：一条 deny 规则能重新拦住任意命令执行。
    With allow-by-default, tightening still works: one deny rule blocks arbitrary execution again."""
    from core.config.schema import PermissionsSection
    from types import SimpleNamespace
    from core.tools.policy import decide, decide_tier

    p = PermissionsSection(rules=[{"match": "run_*", "action": "deny"}])
    assert decide("run_shell_tool", p).action == "deny"
    assert decide("write_file", p).action == "allow"
    tiers = SimpleNamespace(read="allow", write="allow", **{"exec": "ask"})
    assert decide_tier("exec", SimpleNamespace(tiers=tiers, default_action="allow", rules=[])).action == "ask"


def test_permissions_section_rejects_invalid_action():
    """非法动作被 pydantic 拒绝 —— 配置写错启动即报错，而不是静默降级。
    An invalid action is rejected by pydantic: a bad config fails at startup instead of
    silently degrading."""
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        c.Settings(permissions={"tiers": {"read": "maybe"}})


def test_permissions_section_accepts_rules():
    """规则可解析为 match + action。Rules parse into match + action."""
    s = c.Settings(permissions={"rules": [{"match": "run_*", "action": "deny"}]})
    assert s.permissions.rules[0].match == "run_*"
    assert s.permissions.rules[0].action == "deny"


def test_permissions_snapshot_exposed(monkeypatch):
    """可编辑快照必须暴露 permissions —— 否则设置页拿不到（response_model 会把它过滤掉）。
    The editable snapshot must expose permissions, or the settings page cannot read it
    (the response_model would filter it out)."""
    settings = c.Settings(permissions={"rules": [{"match": "run_*", "action": "deny"}]})
    monkeypatch.setattr(c, "get_settings", lambda: settings)
    snap = c.editable_snapshot()
    assert snap["permissions"]["tiers"]["read"] == "allow"
    assert snap["permissions"]["default_action"] == "allow"
    assert snap["permissions"]["rules"] == [{"match": "run_*", "action": "deny"}]


def test_vad_answer_timeout_default_and_bounds():
    """等待语音回答的静音超时：默认 8000ms，必须为正数（0 或负数会让等待立即超时）。
    放在 VadConfig 里 —— 与 max_duration_ms（最大录音时长）同族，且 /api/config 与
    可编辑快照都以 VadConfig 类型暴露它，故无需新增接线。
    The answer-wait silence timeout defaults to 8000ms and must be positive. It lives in
    VadConfig alongside max_duration_ms: both /api/config and the editable snapshot expose
    it through the VadConfig type, so no extra wiring is needed."""
    assert c.Settings().voice.vad.answer_timeout_ms == 8000
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        c.Settings(voice={"vad": {"answer_timeout_ms": 0}})


def test_vad_answer_timeout_reaches_frontend_payload(monkeypatch):
    """必须出现在 /api/config 的 vad 字段里 —— 前端 vadConfig 靠它取超时值。
    It must appear in /api/config's vad field, which is where the frontend's vadConfig
    reads the timeout from."""
    settings = c.Settings(voice={"vad": {"answer_timeout_ms": 12000}})
    monkeypatch.setattr(c, "get_settings", lambda: settings)
    snap = c.editable_snapshot()
    assert snap["vad"]["answer_timeout_ms"] == 12000


# ─── 唤醒词：多个关键字（2026-09-13 默认改为「衍衡」+「洛吉斯」）───


def test_wake_keywords_default_to_two():
    """默认两个唤醒词：衍衡、洛吉斯（说哪个都能唤醒）。
    Two wake keywords by default; either one wakes the engine."""
    s = c.Settings()
    assert s.voice.wake_word.keywords == ["衍衡", "洛吉斯"]


def test_wake_legacy_singular_keyword_is_folded():
    """旧的单数 `keyword` 配置必须仍能启动 —— 折进 keywords。

    ⚠️ 这条不是洁癖：`WakeWordConfig` 是 `extra="forbid"`，直接删掉 `keyword` 字段会让
    **所有已有 config.yaml 启动即 ValidationError**。老配置只写了一个词，取它当唯一唤醒词。

    The legacy singular `keyword` must still boot — it is folded into `keywords`. This is not
    fastidiousness: `WakeWordConfig` uses `extra="forbid"`, so simply removing the `keyword` field
    would make **every existing config.yaml fail validation at startup**. An old config names a
    single word, so it becomes the only wake keyword.
    """
    s = c.Settings(voice={"wake_word": {"keyword": "小逻小逻"}})
    assert s.voice.wake_word.keywords == ["小逻小逻"]


def test_wake_explicit_keywords_win_over_legacy():
    """同时给了新旧两种写法时以 `keywords` 为准，旧字段不合并、不报错。
    When both forms are present, `keywords` wins; the legacy field is neither merged nor an error."""
    s = c.Settings(voice={"wake_word": {"keyword": "小逻小逻", "keywords": ["衍衡"]}})
    assert s.voice.wake_word.keywords == ["衍衡"]


def test_wake_unknown_field_still_rejected():
    """extra="forbid" 仍然生效（只有 `keyword` 是特例），拼错的字段照旧启动即报错。
    extra="forbid" still applies (only `keyword` is special-cased): a misspelled field still fails
    at startup."""
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        c.Settings(voice={"wake_word": {"keywrod": "衍衡"}})


# ─── 唤醒上传的成本控制字段（子项目 1）───


def test_vad_wake_cost_control_defaults():
    """VAD 段新增两个成本控制字段：最短语音时长与上传节流。

    放在 vad 段而非新建段：这两个都是「收听时序」参数，与既有字段同族，该段已有
    「同族参数放一起」的先例（见 answer_timeout_ms 的注释）。

    Two cost-control fields join the VAD section: a minimum speech duration and an upload throttle.
    They live here rather than in a new section because they are listening-timing parameters like
    their neighbours — the section already set that precedent (see the answer_timeout_ms comment).
    """
    v = c.VadConfig()
    assert v.min_speech_ms == 300
    assert v.upload_throttle_ms == 500


def test_vad_wake_cost_control_bounds():
    """负值被 pydantic 拒绝 —— 配置写错启动即报错，而不是静默降级。
    Negative values are rejected by pydantic: a bad config fails at startup instead of degrading."""
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        c.VadConfig(min_speech_ms=-1)
    with pytest.raises(ValidationError):
        c.VadConfig(upload_throttle_ms=-1)


def test_vad_duplicate_in_api_schemas_stays_in_sync():
    """**手工副本陷阱**：`core/api/schemas.py` 里有 VadConfig 的副本，不同步的话
    FastAPI 的 response_model 会静默丢掉新字段，前端 `/api/config` 收不到。

    逐字段比较「字段名 → (注解, 默认值)」：任何一边漏改（增删改名）、默认值漂移
    （config 300 vs api 1000）、或注解变化（int → float）都会红。

    ⚠️ 不比较校验约束（ge/le）：api 副本本来就**故意不带**约束（它只负责 response_model
    的字段名/类型/默认值契约），canonical 模型才做校验。拿 model_json_schema() 比会把这种
    有意差异误报成漂移。

    **The duplicate-model trap**: `core/api/schemas.py` carries a copy of VadConfig. If they drift,
    FastAPI's response_model silently drops the new field and the frontend never sees it in
    /api/config. This case compares each field's name → (annotation, default), so a missing/renamed
    field, a default drift, or an annotation change on either side fails.

    NOTE: validation constraints (ge/le) are intentionally **not** compared — the api copy
    deliberately carries none (it only defines the response_model contract of names/types/defaults),
    while only the canonical model validates. Comparing model_json_schema() would misreport that
    deliberate difference as drift.
    """
    from core.api import schemas as api_schemas
    from core.config import schema as cfg_schema

    def signature(model_cls):
        return {name: (field.annotation, field.default) for name, field in model_cls.model_fields.items()}

    assert signature(cfg_schema.VadConfig) == signature(api_schemas.VadConfig)
