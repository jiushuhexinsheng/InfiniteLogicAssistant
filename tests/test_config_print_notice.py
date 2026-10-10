# -*- coding: utf-8 -*-
"""启动提示的编码降级：控制台编码不了中文（如 CI cp1252）时不得炸启动/收集。

Encoding fallback for boot notices: a console that cannot encode Chinese (e.g. CI's
cp1252) must never crash startup or test collection.
"""
import io

import core.config.loader as loader_mod


def _cp1252_stdout():
    """严格 cp1252 输出流：写非 Latin-1 字符即抛 UnicodeEncodeError（模拟 CI 控制台）。

    Strict cp1252 stream: writing any non-Latin-1 char raises UnicodeEncodeError
    (simulates the CI console).
    """
    buf = io.BytesIO()
    stream = io.TextIOWrapper(buf, encoding="cp1252", newline="")
    return stream, buf


def test_print_notice_falls_back_on_cp1252(monkeypatch):
    """非 UTF-8 控制台 → 降级为 \\u 转义文本，不抛异常。"""
    stream, buf = _cp1252_stdout()
    monkeypatch.setattr("sys.stdout", stream)
    loader_mod._print_notice("[配置] 测试提示")
    stream.flush()
    out = buf.getvalue().decode("ascii")
    assert "\\u914d" in out, "降级输出必须是 ASCII 可表示的转义文本"


def test_print_notice_normal_console_passthrough(monkeypatch):
    """UTF-8 控制台 → 原样输出。"""
    stream, buf = _cp1252_stdout()  # 同一个流，但内容为 ASCII 时不触发降级
    monkeypatch.setattr("sys.stdout", stream)
    loader_mod._print_notice("[plain ascii] ok")
    stream.flush()
    assert buf.getvalue().decode("ascii") == "[plain ascii] ok\n"


def test_build_with_missing_config_survives_cp1252_console(tmp_path, monkeypatch):
    """CI 场景集成复现：缺 config.yaml + cp1252 控制台 → _build 照常完成（从 example
    创建并打印提示），此前该路径直接 UnicodeEncodeError 中断收集。"""
    import core.config as config_mod

    monkeypatch.setattr(config_mod, "CONFIG_FILE", tmp_path / "config.yaml")
    monkeypatch.setattr(config_mod, "EXAMPLE_FILE", config_mod.EXAMPLE_FILE)
    monkeypatch.setattr(config_mod, "SECRETS_FILE", tmp_path / "config.secrets.yaml")
    monkeypatch.setattr(config_mod, "SECRETS_EXAMPLE", config_mod.SECRETS_EXAMPLE)
    stream, buf = _cp1252_stdout()
    monkeypatch.setattr("sys.stdout", stream)
    s = loader_mod._build()
    stream.flush()
    assert s.server.port > 0
    assert (tmp_path / "config.yaml").exists()
    assert "\\u914d" in buf.getvalue().decode("ascii"), "创建提示应走降级分支"
