# -*- coding: utf-8 -*-
"""/api/voice/answer：结构化确认 choice 透传。Structured-choice pass-through on /api/voice/answer."""


# ─── /api/voice/answer：结构化确认 choice 透传 ───


def test_voice_answer_passes_structured_choice(client):
    """按钮回传的 choice 原样透传到会话通道；空 choice 视为未选择。
    The choice returned by buttons is passed through to the session channel unchanged;
    an empty choice counts as no selection.
    """
    import asyncio

    from core.api import state
    from core.orchestrator.control import StopController
    from core.orchestrator.pipeline import EventQueueChannel
    from core.orchestrator.session import Answer, Session

    session = Session(session_id="ans-choice")
    channel = EventQueueChannel(asyncio.Queue(), "ans-choice")
    session.channel = channel
    state.register(session, StopController())
    try:
        r = client.post("/api/voice/answer", json={"session_id": "ans-choice", "text": "", "choice": "yes"})
        assert r.status_code == 200
        assert channel.answers.get_nowait() == Answer(text="", choice="yes")

        # 空字符串 choice 视为未选择（不去猜用户意图）
        r2 = client.post("/api/voice/answer", json={"session_id": "ans-choice", "text": "随便吧", "choice": ""})
        assert r2.status_code == 200
        assert channel.answers.get_nowait() == Answer(text="随便吧", choice=None)
    finally:
        state.cleanup("ans-choice")


def test_voice_answer_accepts_arbitrary_choice(client):
    """choice 不限于 yes/no —— 权限策略的「允许一次 / 永久允许」等取值必须能透传。
    choice is not limited to yes/no: values such as the permission policy's
    allow-once / allow-always must pass through. 取值合法性由消费方自行校验。
    """
    import asyncio

    from core.api import state
    from core.orchestrator.control import StopController
    from core.orchestrator.pipeline import EventQueueChannel
    from core.orchestrator.session import Answer, Session

    session = Session(session_id="ans-arb")
    channel = EventQueueChannel(asyncio.Queue(), "ans-arb")
    session.channel = channel
    state.register(session, StopController())
    try:
        r = client.post("/api/voice/answer", json={"session_id": "ans-arb", "text": "", "choice": "always"})
        assert r.status_code == 200
        assert channel.answers.get_nowait() == Answer(text="", choice="always")
    finally:
        state.cleanup("ans-arb")


def test_voice_answer_unknown_session_404(client):
    """未知会话返回 404。An unknown session returns 404."""
    r = client.post("/api/voice/answer", json={"session_id": "nope", "text": "确认"})
    assert r.status_code == 404


def test_voice_answer_rejects_stale_qid_409(client):
    """携带的 qid 与待答问题不符 → 409（防陈旧语音作答错配）；匹配/缺省则 200。
    A mismatched qid gets 409 (a stale voice answer cannot be mismatched); a matching
    or absent qid gets 200.
    """
    import asyncio

    from core.api import state
    from core.orchestrator.control import StopController
    from core.orchestrator.pipeline import EventQueueChannel
    from core.orchestrator.session import Session

    session = Session(session_id="ans-qid")
    channel = EventQueueChannel(asyncio.Queue(), "ans-qid")
    channel.pending_qid = "q_current"
    session.channel = channel
    state.register(session, StopController())
    try:
        # 陈旧 qid → 409 且不投递
        r = client.post("/api/voice/answer",
                        json={"session_id": "ans-qid", "text": "错", "qid": "q_stale"})
        assert r.status_code == 409
        assert channel.answers.empty()
        # 匹配 qid → 200 且投递
        r2 = client.post("/api/voice/answer",
                         json={"session_id": "ans-qid", "text": "对", "qid": "q_current", "source": "voice"})
        assert r2.status_code == 200
        assert not channel.answers.empty()
    finally:
        state.cleanup("ans-qid")
