# -*- coding: utf-8 -*-
"""/voice/wake、/voice/wake/check 与音频上传审计成本口径。
/voice/wake, /voice/wake/check and the audio-upload audit cost accounting.
"""
from _helpers import _AUDIO_UPLOAD_ENDPOINTS, _NON_UPLOAD_VOICE_ENDPOINTS


# ─── /voice/wake 唤醒检测端点 ───

def test_voice_wake_matches_and_splits(client, monkeypatch):
    """唤醒端点：转写 → 匹配 → 切分，text 始终是原始转写。
    The wake endpoint transcribes, matches and splits, always returning the raw transcript."""
    import core.voice as voice_pkg

    class _Asr:
        def available(self): return True
        async def transcribe_base64(self, b64, fmt="wav"): return "衍衡，帮我查天气。"

    monkeypatch.setattr(voice_pkg, "get_asr", lambda: _Asr())
    r = client.post("/api/voice/wake", json={"audio_base64": "AAAA"})
    assert r.status_code == 200
    d = r.json()
    assert d["matched"] is True
    assert d["command"] == "帮我查天气"
    assert d["text"] == "衍衡，帮我查天气。"


def test_voice_wake_no_match(client, monkeypatch):
    """无关对话不命中，但 text 仍返回（便于排障）。
    Unrelated speech does not match, yet text still comes back for debugging."""
    import core.voice as voice_pkg

    class _Asr:
        def available(self): return True
        async def transcribe_base64(self, b64, fmt="wav"): return "今天天气怎么样。"

    monkeypatch.setattr(voice_pkg, "get_asr", lambda: _Asr())
    d = client.post("/api/voice/wake", json={"audio_base64": "AAAA"}).json()
    assert d["matched"] is False and d["command"] == ""


def test_voice_wake_without_audio(client):
    """缺 audio_base64 → 400，不调 ASR。A missing audio_base64 yields 400 without touching the ASR."""
    r = client.post("/api/voice/wake", json={})
    assert r.status_code == 400
    assert r.json()["ok"] is False


def test_voice_wake_asr_unavailable(client, monkeypatch):
    """ASR 未配置 → 明确报错，不假装成功。An unconfigured ASR reports an error rather than faking success."""
    import core.voice as voice_pkg

    class _Asr:
        def available(self): return False

    monkeypatch.setattr(voice_pkg, "get_asr", lambda: _Asr())
    d = client.post("/api/voice/wake", json={"audio_base64": "AAAA"}).json()
    assert d["ok"] is False
    assert "ASR" in d["error"]


def test_voice_wake_asr_failure_reports_error(client, monkeypatch):
    """ASR 抛异常 → ok=False 带错误信息（前端据此计熔断）。An ASR exception returns ok=False with a
    message, which is what the frontend counts toward its circuit breaker."""
    import core.voice as voice_pkg

    class _Asr:
        def available(self): return True
        async def transcribe_base64(self, b64, fmt="wav"): raise RuntimeError("上游 502")

    monkeypatch.setattr(voice_pkg, "get_asr", lambda: _Asr())
    d = client.post("/api/voice/wake", json={"audio_base64": "AAAA"}).json()
    assert d["ok"] is False and "502" in d["error"]


def test_voice_wake_writes_audit(client, monkeypatch, tmp_path):
    """每次唤醒上传都写审计 —— 这是统计上传量与成本的依据。
    Every wake upload is audited: that record is the basis for measuring upload volume and cost.

    ⚠️ patch 目标是 `core.api.voice.wake.audit`，**不是** `core.logger.audit`：voice/wake.py 用
    `from core.logger import audit` 顶层导入，名字绑定进了该子模块命名空间，改源头那个不影响它。
    Patch `core.api.voice.wake.audit`, not `core.logger.audit`: voice/wake.py imports the name at
    module level, so it is bound into that submodule's namespace and patching the source has no
    effect.
    """
    import core.voice as voice_pkg
    import core.api.voice.wake as voice_wake

    lines: list[str] = []
    monkeypatch.setattr(voice_wake, "audit", lambda msg: lines.append(msg))

    class _Asr:
        def available(self): return True
        async def transcribe_base64(self, b64, fmt="wav"): return "衍衡。"

    monkeypatch.setattr(voice_pkg, "get_asr", lambda: _Asr())
    client.post("/api/voice/wake", json={"audio_base64": "AAAA"})
    assert any(l.startswith("audio-upload via=wake") and "matched" in l for l in lines), lines


# ─── /voice/wake/check 本地 KWS 快检（判定与提取分离的前半段）───


def test_voice_wake_check_hit_never_touches_asr(client, monkeypatch):
    """KWS 命中 → hit=True，且**全程零 ASR 调用** —— 这是「本地判定不上传确认」的硬证据。
    A KWS hit returns hit=True with **zero ASR calls** — the hard evidence that local
    judging uploads nothing for confirmation.
    """
    import core.voice as voice_pkg
    import core.voice.kws as kws_pkg

    class _Asr:
        def available(self):
            raise AssertionError("check 端点绝不能调 ASR / the check endpoint must never call ASR")

        def transcribe_base64(self, *a, **kw):
            raise AssertionError("check 端点绝不能调 ASR / the check endpoint must never call ASR")

    monkeypatch.setattr(voice_pkg, "get_asr", lambda: _Asr())

    class _Gate:
        def detect_wav_bytes(self, wav):
            return True

    monkeypatch.setattr(kws_pkg, "get_kws", lambda: _Gate())
    d = client.post("/api/voice/wake/check", json={"audio_base64": "AAAA"}).json()
    assert d["ok"] is True and d["hit"] is True and d["bypass"] is False


def test_voice_wake_check_miss_and_bypass(client, monkeypatch):
    """未命中 hit=False；闸门旁路 hit=False + bypass=True（前端据此回退完整路径）。
    A miss returns hit=False; a gate bypass returns hit=False + bypass=True (the
    frontend falls back to the full path on it).
    """
    import core.voice.kws as kws_pkg

    class _GateMiss:
        def detect_wav_bytes(self, wav):
            return False

    class _GateBypass:
        def detect_wav_bytes(self, wav):
            return None

    monkeypatch.setattr(kws_pkg, "get_kws", lambda: _GateMiss())
    d = client.post("/api/voice/wake/check", json={"audio_base64": "AAAA"}).json()
    assert d["ok"] is True and d["hit"] is False and d["bypass"] is False

    monkeypatch.setattr(kws_pkg, "get_kws", lambda: _GateBypass())
    d = client.post("/api/voice/wake/check", json={"audio_base64": "AAAA"}).json()
    assert d["ok"] is True and d["hit"] is False and d["bypass"] is True


def test_voice_wake_check_without_audio(client):
    """缺 audio_base64 → 400。A missing audio_base64 yields 400."""
    r = client.post("/api/voice/wake/check", json={})
    assert r.status_code == 400


def test_voice_transcribe_writes_audit(client, monkeypatch):
    """/voice/transcribe 也必须逐条写审计 —— 它和 /voice/wake 一样把音频送上云。

    为什么非有不可：作答与指令两条通道都走 transcribe（前端 `transcribeSegment`），
    而作答复用频率最高。只记 wake 会让「数审计行 = 数上传次数」不成立 ——
    照 wake 行估算成本会**显著偏低**。

    /voice/transcribe must be audited line-by-line too: like /voice/wake it sends audio to the
    cloud. The answer and command channels both go through transcribe (the frontend's
    `transcribeSegment`) and answering is the most frequent path, so auditing only wakes would
    break "count audit lines = count uploads" and make cost estimates **far too low**.
    """
    import core.voice as voice_pkg
    import core.api.voice.wake as voice_wake

    lines: list[str] = []
    monkeypatch.setattr(voice_wake, "audit", lambda msg: lines.append(msg))

    class _Asr:
        def available(self): return True
        async def transcribe_base64(self, b64, fmt="wav"): return "下载目录。"

    monkeypatch.setattr(voice_pkg, "get_asr", lambda: _Asr())
    resp = client.post("/api/voice/transcribe", json={"audio_base64": "AAAA"})
    assert resp.json()["ok"] is True
    assert any(l.startswith("audio-upload via=transcribe") for l in lines), lines


def test_audio_upload_audit_prefix_is_shared(client, monkeypatch):
    """钉住**成本口径本身**：审计行数必须等于真实上传次数，否则 README / Security 里
    「数审计行估成本」的指引就是错的。

    具体钉三件事：
      ① **分类完备**：`/api/voice/` 下每个 POST 端点，要么在「携带音频」表里，要么在
         「不携带音频」白名单里。新增端点若两边都不在，**本例会红** —— 逼作者做一次明确
         判断，而不是悄悄漏计（原先的版本只数自己发起的两次调用，新增端点漏审计照样通过，
         所以它证明的其实不是「行数 = 上传次数」）。
      ② **不多不少**：每个上传端点调用一次，恰好产生一行；行数 == 上传端点数。
      ③ **前缀共用**：这些行的 `via=` 取值集合恰好等于表里的取值集合，可一条 grep 数全。

    ⚠️ 诚实边界：把某个**新**端点判为「不携带音频」仍是人的判断（白名单是手写的），
    本例不能替人做这个判断 —— 它保证的是「这个判断必须被做出并被写下来」。

    This test pins **the accounting rule itself**: audit lines must equal real uploads, or the
    "count audit lines to estimate cost" guidance in README/Security is wrong. It pins three
    things: (1) **classification is total** — every POST endpoint under `/api/voice/` is either in
    the audio table or in the non-audio allow-list; an unclassified new endpoint fails this test,
    forcing an explicit decision instead of a silent undercount (the earlier version only counted
    its own two calls, so a new unaudited endpoint would still pass — it did not actually pin
    "lines == uploads"); (2) **exactly one line per call**, with the line count equal to the number
    of upload endpoints; (3) **the prefix is shared**, so a single grep counts them all.

    Honest limit: classifying a *new* endpoint as "carries no audio" remains a human judgement
    (the allow-list is hand-written). This test cannot make that judgement — it guarantees the
    judgement has to be made and written down.
    """
    import core.voice as voice_pkg
    import core.api.voice.wake as voice_wake

    # ① 分类完备：/api/voice/ 下的 POST 端点集合必须被 _helpers 中两张表完全覆盖。
    # Classification is total: the POST endpoints under /api/voice/ must be fully covered by the
    # two tables in _helpers.
    #
    # 收集走 OpenAPI schema 而非 app.routes：starlette 1.6 起 include_router 的子路由
    # 被包进 _IncludedRouter（path=None，真实路由藏在 original_router 且是无前缀的相对
    # 路径），扁平遍历 app.routes 收集到空集、全表误报 stale。OpenAPI 是公开契约、带
    # 全路径，对路由内部结构不敏感。
    # Collected via the OpenAPI schema rather than app.routes: since starlette 1.6,
    # include_router wraps sub-routes in _IncludedRouter (path=None; the real routes sit
    # in original_router as prefix-less relative paths), so flat app.routes traversal
    # collects nothing and the whole table is misreported as stale. OpenAPI is the public
    # contract, carries full paths, and is immune to route-internals changes.
    spec = client.app.openapi()
    declared = {
        path for path, ops in spec.get("paths", {}).items()
        if "post" in ops and path.startswith("/api/voice/")
    }
    classified = set(_AUDIO_UPLOAD_ENDPOINTS) | set(_NON_UPLOAD_VOICE_ENDPOINTS)
    assert declared == classified, (
        f"/api/voice/ 下未分类的 POST 端点：{declared - classified}；已失效的分类：{classified - declared}。"
        f"新增端点若携带音频，请用 `audio-upload via=` 前缀记审计并加进 _AUDIO_UPLOAD_ENDPOINTS；"
        f"确实不携带音频则加进 _NON_UPLOAD_VOICE_ENDPOINTS 并写明理由。"
        f"Unclassified POST endpoints under /api/voice/: {declared - classified}; stale entries: "
        f"{classified - declared}."
    )

    lines: list[str] = []
    monkeypatch.setattr(voice_wake, "audit", lambda msg: lines.append(msg))

    class _Asr:
        def available(self): return True
        async def transcribe_base64(self, b64, fmt="wav"): return "衍衡。"

    monkeypatch.setattr(voice_pkg, "get_asr", lambda: _Asr())

    # call/segment 的审计命名空间在 core.api.voice.call（不在 wake），且它要过 L0
    # （会话 + 焦点/窗口）才会上云 —— 把审计收进 lines、执行件换成零网络假件、开会话。
    import core.api.voice.call as voice_call
    monkeypatch.setattr(voice_call, "audit", lambda msg: lines.append(msg))
    monkeypatch.setattr(voice_call, "_local_transcribe", None)  # 跳过 L1（本地模型/Smart Turn）

    async def _fake_judge(t, r, relax):
        return "command"
    monkeypatch.setattr(voice_call, "_judge", _fake_judge)

    # ② 每个上传端点恰好一行。Exactly one line per upload endpoint.
    # call/segment 服务端校验 wav（时长/RMS）且要求焦点，单独给它合法音频体。
    import base64, io, math, struct, wave
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
        w.writeframes(b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * 220 * i / 16000)))
                               for i in range(16000)))
    wav_b64 = base64.b64encode(buf.getvalue()).decode()
    assert client.post("/api/voice/call/start").json()["ok"] is True  # 开会话：段落才进漏斗
    for path in _AUDIO_UPLOAD_ENDPOINTS:
        body = ({"audio_base64": wav_b64, "tab_focused": True}
                if path == "/api/voice/call/segment" else {"audio_base64": "AAAA"})
        resp = client.post(path, json=body)
        assert resp.status_code == 200 and resp.json()["ok"] is True, (path, resp.text)
    voice_call.reset_session_state()

    uploads = [l for l in lines if l.startswith("audio-upload via=")]
    assert len(uploads) == len(_AUDIO_UPLOAD_ENDPOINTS), uploads
    # ③ 前缀共用、取值集合吻合。Shared prefix with a matching set of via= values.
    assert {l.split()[1] for l in uploads} == {f"via={v}" for v in _AUDIO_UPLOAD_ENDPOINTS.values()}, lines
