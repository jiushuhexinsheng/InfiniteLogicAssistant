# -*- coding: utf-8 -*-
from core.voice.wake import WakeListener, is_stop_command


def test_stop_command_hit():
    for w in ("停止", "取消", "暂停", "够了", "停下", "停止这个任务"):
        assert is_stop_command(w)


def test_stop_command_miss():
    for t in ("你好", "帮我查天气", "继续", "重新开始", ""):
        assert not is_stop_command(t)


def test_listener_default_keyword():
    l = WakeListener()
    assert l.keyword  # 默认「小逻小逻」或配置值


def test_listener_start_with_nonexistent_model_fails():
    l = WakeListener(model_path="C:/no-such-vosk-model-xyz")
    assert l.start(on_utterance=None) is False
