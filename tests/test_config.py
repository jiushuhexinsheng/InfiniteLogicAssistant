# -*- coding: utf-8 -*-
"""core/config.py — 密钥优先级 / 新字段 / 设置快照。
Tests core/config.py — API key priority, new fields, and the settings snapshot.
"""
import pytest
from pydantic_core import PydanticUndefined

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


def test_profile_secrets_outrank_section_env(monkeypatch):
    """profile 级 secrets 条目优先于段级全局环境变量（防回归：LLM_API_KEY 段级 env 曾
    遮蔽 config.secrets.yaml 里 xiaomi-mimo-llm 的真 key，拿 deepseek key 打 mimo → 401）。
    Verifies a profile-level secrets entry outranks the section-wide env var (regression:
    LLM_API_KEY once shadowed the real xiaomi-mimo-llm key in config.secrets.yaml, sending
    the deepseek key to mimo → 401).
    """
    monkeypatch.setenv("LLM_API_KEY", "deepseek-section-key")
    monkeypatch.delenv("MIMO_API_KEY", raising=False)
    secrets = {"llm": {"api_key": "sec_default", "profiles": {"xiaomi-mimo-llm": "mimo-profile-key"}}}
    # 有 profile 级 secrets → 用它，不被段级 env 遮蔽
    assert c._profile_api_key("llm", "xiaomi-mimo-llm", secrets, _mk_profile(api_key_env="MIMO_API_KEY")) == "mimo-profile-key"
    # 无 profile 级 secrets 的 profile 仍走段级 env（deepseek 惯例：api_key_env='' → LLM_API_KEY）
    assert c._profile_api_key("llm", "deepseek", secrets, _mk_profile(api_key_env="")) == "deepseek-section-key"


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

def test_settings_rejects_vendor_presets_field():
    """vendor_presets 字段已随厂商目录退役 —— Settings extra=forbid 直接拒绝该键
    （老配置由 loader 的 _migrate_legacy_vendor_keys 在建模前剥除，见下方迁移用例）。
    The vendor_presets field retired with the catalogue — Settings (extra=forbid) rejects
    the key outright (legacy configs are stripped pre-modelling by
    _migrate_legacy_vendor_keys; see the migration case below)."""
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        c.Settings(vendor_presets={"myllm": {"kind": "llm"}})
    assert c.Settings().agent.models_failover == []   # models_failover 仍在


def test_migrate_legacy_vendor_keys_strips_and_warns(capsys):
    """老配置迁移：顶层 vendor_presets 与 profile.vendor 键被剥除并各告警一次，
    其余字段原样保留（extra=forbid 不再炸启动）。
    Legacy migration: the top-level vendor_presets and per-profile vendor keys are
    stripped with one notice each; everything else passes through unchanged (no more
    extra=forbid boot failure)."""
    from core.config.loader import _migrate_legacy_vendor_keys
    data = {
        "vendor_presets": {"custom": {"kind": "llm"}},
        "llm": {"active": "a", "profiles": {"a": {"vendor": "deepseek", "model": "m"}}},
        "voice": {"asr": {"profiles": {"b": {"vendor": "v", "model": "asr-m"}}}},
    }
    _migrate_legacy_vendor_keys(data)
    assert "vendor_presets" not in data
    assert "vendor" not in data["llm"]["profiles"]["a"]
    assert data["llm"]["profiles"]["a"]["model"] == "m"
    assert "vendor" not in data["voice"]["asr"]["profiles"]["b"]
    out = capsys.readouterr().out
    assert "vendor_presets" in out and "vendor 键" in out
    # 剥完必须能过建模
    c.Settings(**data)


def test_profile_accepts_models_compat_api_key_env():
    """验证 LlmProfile 接受 models/compat/api_key_env 字段（vendor 字段已随目录删除，
    extra=allow 下残留键仍被容忍不炸）。Verifies LlmProfile accepts the models, compat and
    api_key_env fields (the vendor field retired; leftovers stay tolerated under
    extra=allow)."""
    prof = c.LlmProfile(
        vendor="deepseek", api_key_env="DEEPSEEK_API_KEY",
        models=["deepseek-chat"], models_path="/v1/models",
        compat={"stream_options": False},
    )
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
        "ds": c.LlmProfile(api_key_env="DEEPSEEK_API_KEY",
                           models=["deepseek-chat"], compat={"stream_options": False}, api_key="SECRET"),
    }))
    monkeypatch.setattr(c, "get_settings", lambda: settings)
    snap = c.editable_snapshot()
    prof = snap["llm"]["profiles"]["ds"]
    assert "api_key" not in prof
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


def test_vad_listen_idle_default_and_bounds():
    """聆听空闲超时：默认 180s（3 分钟），0=永不超时合法，负数拒绝。

    放在 VadConfig —— 收听时序同族，/api/config 与可编辑快照都以 VadConfig 暴露，
    前端 vadConfig 直接读（api 手工副本同步由
    test_wake_and_vad_duplicates_in_api_schemas_stay_in_sync 钉住）。

    Listening idle timeout: defaults to 180s (3 minutes); 0 (never) is valid,
    negatives are rejected. Lives in VadConfig (listening-timing family), exposed via
    both /api/config and the editable snapshot, so the frontend vadConfig reads it
    directly (the api hand-copy sync is pinned by the duplicate-model guard test)."""
    assert c.Settings().voice.vad.listen_idle_s == 180
    assert c.Settings(voice={"vad": {"listen_idle_s": 0}}).voice.vad.listen_idle_s == 0
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        c.Settings(voice={"vad": {"listen_idle_s": -1}})


def test_vad_listen_idle_reaches_editable_snapshot(monkeypatch):
    """必须进可编辑快照 —— 设置页的输入框从这里取值。
    Must reach the editable snapshot — the settings-page input reads it from there."""
    settings = c.Settings(voice={"vad": {"listen_idle_s": 60}})
    monkeypatch.setattr(c, "get_settings", lambda: settings)
    assert c.editable_snapshot()["vad"]["listen_idle_s"] == 60


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


# ─── 手工副本陷阱：两份模型必须逐字段一致（含默认值与 default_factory）───


def _field_signature(model_cls) -> dict:
    """字段名 → (注解, 默认值)，**default_factory 也要真的求值**。

    ⚠️ 不能直接用 `field.default`：带 `default_factory` 的字段它是 `PydanticUndefined`，
    两边于是都等于同一个哨兵值 —— `keywords: []` 与 `keywords: ["衍衡","洛吉斯"]` 会被
    判成一致，而这正是本模型最常见的漂移形状。`get_default(call_default_factory=True)`
    把工厂调出来，漂移才现形。

    Field name → (annotation, default), with **default_factory actually evaluated**. Reading
    `field.default` directly yields PydanticUndefined for a factory field, so both sides collapse to
    the same sentinel and `keywords: []` vs `keywords: ["衍衡","洛吉斯"]` compares equal — exactly
    the drift shape this model has. Calling the factory is what makes the drift visible.

    Args:
        model_cls: pydantic 模型类。The pydantic model class.

    Returns:
        字段名到 (注解, 默认值) 的映射。A mapping of field name to (annotation, default).
    """
    out = {}
    for name, field in model_cls.model_fields.items():
        try:
            default = field.get_default(call_default_factory=True)
        except Exception:  # 工厂抛错：用哨兵表示「无法求值」，两边都抛才算一致
            default = PydanticUndefined
        out[name] = (field.annotation, default)
    return out


def test_wake_and_vad_duplicates_in_api_schemas_stay_in_sync():
    """**手工副本陷阱**：`core/api/schemas.py` 里有 `VadConfig` 与 `WakeWordConfig` 的副本，
    不同步的话 FastAPI 的 response_model 会静默丢掉字段，前端 `/api/config` 收不到。

    两份都必须查，理由不一样：

    - `VadConfig`：漏同步 = 字段从 `/api/config` 里消失（本次踩过）。
    - `WakeWordConfig`：它**在 `EditableSnapshot` 里**，而设置页（`settings/state.ts`）
      会把整个对象原样 PATCH 回来 —— 漏同步就不只是「前端读不到」，而是**下一次保存设置时
      把漂移值写回 `config.yaml`**，把用户配置擦掉。漂移在这里更贵。

    比较「字段名 → (注解, 默认值**含 default_factory**）」：增删改名、默认值漂移、工厂返回值
    漂移（`[]` vs `["衍衡","洛吉斯"]`）、注解变化（int → float）都会红。

    ⚠️ 不比较校验约束（ge/le）：api 副本本来就**故意不带**约束（它只负责 response_model
    的字段名/类型/默认值契约），canonical 模型才做校验。拿 model_json_schema() 比会把这种
    有意差异误报成漂移。

    **The duplicate-model trap**: `core/api/schemas.py` carries copies of both `VadConfig` and
    `WakeWordConfig`. If they drift, FastAPI's response_model silently drops the field and the
    frontend never sees it in /api/config. Both are checked, for different reasons:
    `VadConfig` loses fields from /api/config, while `WakeWordConfig` sits inside
    `EditableSnapshot`, which the settings page round-trips wholesale — so drift there is not just
    "the frontend cannot read it" but **the drifted value gets written back into `config.yaml` on
    the next settings save**, erasing the user's configuration. Drift is more expensive here.

    Comparing name → (annotation, default **including default_factory**) fails on a
    missing/renamed field, a default drift, a factory-value drift (`[]` vs `["衍衡","洛吉斯"]`), or
    an annotation change.

    NOTE: validation constraints (ge/le) are intentionally **not** compared — the api copy
    deliberately carries none (it only defines the response_model contract of names/types/defaults),
    while only the canonical model validates. Comparing model_json_schema() would misreport that
    deliberate difference as drift.
    """
    from core.api import schemas as api_schemas
    from core.config import schema as cfg_schema

    pairs = [
        ("VadConfig", cfg_schema.VadConfig, api_schemas.VadConfig),
        ("WakeWordConfig", cfg_schema.WakeWordConfig, api_schemas.WakeWordConfig),
        ("CallConfig", cfg_schema.CallConfig, api_schemas.CallConfig),
    ]
    for name, cfg_model, api_model in pairs:
        assert set(_field_signature(cfg_model)) == set(_field_signature(api_model)), (
            f"{name}: 字段集合不一致（增删改名 / missing or renamed field）"
        )
        assert _field_signature(cfg_model) == _field_signature(api_model), (
            f"{name}: 注解或默认值漂移（annotation / default / default_factory drift）"
        )


def test_call_config_defaults():
    """通话模式配置默认值：开、8s 开放窗口、0.5s/0.02 能量底线。"""
    from core.config.schema import CallConfig
    c = CallConfig()
    assert c.enabled is True
    assert c.open_window_s == 8.0
    assert c.l0_min_rms == 0.02
    assert c.l0_min_seconds == 0.5
    assert c.local_asr_model.endswith("bilingual-zh-en-2023-02-20")


def test_call_config_rejects_retired_keys():
    """已失效的 Smart Turn / L2 合并键必须被拒绝（extra=forbid），
    防止旧文档引导用户写出「看着生效、实际无人读」的配置。
    Retired Smart Turn / merge_l2 keys are rejected (extra=forbid) so stale docs cannot
    lead users to write settings that look effective but are never read."""
    import pytest
    from pydantic import ValidationError
    from core.config.schema import CallConfig

    for key, value in (("smart_turn_enabled", True), ("merge_l2", False)):
        with pytest.raises(ValidationError):
            CallConfig(**{key: value})


def test_streaming_config_rejects_retired_keys():
    """未接线的 frame_ms / commit_policy 已删除：写进配置即报错。
    The unwired frame_ms / commit_policy keys are gone: writing them fails validation."""
    import pytest
    from pydantic import ValidationError
    from core.config.schema import StreamingConfig

    for key, value in (("frame_ms", 20), ("commit_policy", "all")):
        with pytest.raises(ValidationError):
            StreamingConfig(**{key: value})


def test_voice_section_has_call():
    from core.config.schema import VoiceSection
    assert hasattr(VoiceSection(), "call")


# ─── ASR 三模式（2026-10-12）：本地 / 云端 / 混合 ───


def test_asr_mode_default_cloud_and_rejects_invalid():
    """`voice.asr.mode` 默认 `cloud`（与旧行为逐字一致），非法值由 Literal 拒绝。

    `voice.asr.mode` defaults to `cloud` (identical to the legacy behaviour); an invalid
    value is rejected by the Literal."""
    from core.config.schema import AsrSection
    assert AsrSection().mode == "cloud"
    assert c.Settings(voice={"asr": {"mode": "hybrid"}}).voice.asr.mode == "hybrid"
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        c.Settings(voice={"asr": {"mode": "offline"}})


def test_asr_local_model_default_matches_fetch_script():
    """`voice.asr.local_model` 默认值必须与下载脚本的 `DEST` 一致 —— 否则用户跑了脚本、
    模型仍报「找不到」，且错误文案指向一个不存在的目录。

    The default must match the fetch script's `DEST`; otherwise the user runs the script
    and still gets "model missing", pointing at a directory that does not exist."""
    import importlib.util
    from pathlib import Path
    from core.config.schema import AsrSection
    root = Path(c.ROOT_DIR)
    spec = importlib.util.spec_from_file_location(
        "_fetch_local_asr_model", root / "scripts" / "fetch_local_asr_model.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # __main__ 守卫使 main() 不执行
    assert AsrSection().local_model == mod.DEST.relative_to(root).as_posix()


def test_migrate_legacy_call_local_asr_model_moves_to_asr():
    """旧键 `voice.call.local_asr_model` → `voice.asr.local_model` 的迁移。

    三条不变量：① 旧键被显式写过且新键缺席 → 值搬过去；② 新键已存在 → 旧键不覆盖；
    ③ YAML 根本没写旧键 → 不迁移（旧键在模型里有**非空默认值**，若在建模后的对象上判空
    会恒真 —— 这正是必须在原始字典上判断的原因）。

    Migration invariants: a user-written old key with no new key moves over; an existing
    new key wins; a config that never mentioned the old key does not migrate (the old key
    has a non-empty model default, so probing the modelled object would always be true —
    which is exactly why the raw dict must be checked)."""
    from core.config.loader import _migrate_legacy_local_asr_model

    d1 = {"voice": {"call": {"local_asr_model": "models/mine"}}}
    _migrate_legacy_local_asr_model(d1)
    assert d1["voice"]["asr"]["local_model"] == "models/mine"
    assert d1["voice"]["call"]["local_asr_model"] == "models/mine"  # 旧键保留（extra=forbid）

    d2 = {"voice": {"call": {"local_asr_model": "models/old"},
                    "asr": {"local_model": "models/new"}}}
    _migrate_legacy_local_asr_model(d2)
    assert d2["voice"]["asr"]["local_model"] == "models/new"

    d3 = {"voice": {"call": {"enabled": True}}}
    _migrate_legacy_local_asr_model(d3)
    assert "local_model" not in d3["voice"].get("asr", {})


def test_asr_mode_reaches_editable_snapshot(monkeypatch):
    """`mode`/`local_model` 必须进可编辑快照 —— 设置页 ASR 卡的控件从这里取值；
    `local_model_present` 是只读展示标记（不得回送，回送会被 extra=forbid 拒绝）。

    `mode`/`local_model` must reach the editable snapshot (the settings page reads them
    from there); `local_model_present` is a read-only display flag."""
    settings = c.Settings(voice={"asr": {"mode": "hybrid", "local_model": "models/x"}})
    monkeypatch.setattr(c, "get_settings", lambda: settings)
    snap = c.editable_snapshot()
    assert snap["asr"]["mode"] == "hybrid"
    assert snap["asr"]["local_model"] == "models/x"
    assert isinstance(snap["asr"]["local_model_present"], bool)
