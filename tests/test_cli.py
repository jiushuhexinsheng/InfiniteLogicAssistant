# -*- coding: utf-8 -*-
"""CLI 命令测试 — build_parser 子命令注册 + check 聚合检测退出码"""
import pytest

from cli import build_parser


def test_parser_registers_serve_and_check():
    p = build_parser()
    assert callable(p.parse_args(["serve"]).func)
    assert callable(p.parse_args(["check"]).func)


def test_parser_empty_has_no_func():
    # 无子命令时由 main() 默认 serve（parser 不强制子命令）
    assert not hasattr(build_parser().parse_args([]), "func")


def test_cmd_check_exit_1_on_failure(monkeypatch):
    from cli.check import cmd_check

    async def fake_run_all():
        return {
            "environment": {"os": "win", "hostname": "pc", "python": "3.14"},
            "config": {"ok": False, "issues": [
                {"level": "error", "key": "server.api_token", "message": "非 localhost 需 token"},
            ]},
            "connectivity": [
                {"name": "LLM", "status": "fail", "latency_ms": None, "detail": "连不上"},
                {"name": "ASR", "status": "ok", "latency_ms": 120, "detail": ""},
            ],
        }

    monkeypatch.setattr("cli.check.run_all", fake_run_all)
    with pytest.raises(SystemExit) as ei:
        cmd_check(None)
    assert ei.value.code == 1


def test_cmd_check_ok(monkeypatch):
    from cli.check import cmd_check

    async def fake_run_all():
        return {
            "environment": {"os": "win", "hostname": "pc", "python": "3.14"},
            "config": {"ok": True, "issues": []},
            "connectivity": [
                {"name": "LLM", "status": "ok", "latency_ms": 80, "detail": ""},
                {"name": "ASR", "status": "skip", "latency_ms": None, "detail": "未配置"},
                {"name": "TTS", "status": "skip", "latency_ms": None, "detail": "未配置"},
            ],
        }

    monkeypatch.setattr("cli.check.run_all", fake_run_all)
    cmd_check(None)  # 全部正常/跳过 → 不退出


@pytest.mark.asyncio
async def test_main_defaults_to_serve(monkeypatch, capsys):
    import main as main_mod

    called = {}

    def fake_serve(_args):
        called["serve"] = True

    # build_parser 里的 func 引用 cli 包命名空间的 cmd_serve，故 mock cli.cmd_serve
    monkeypatch.setattr("cli.cmd_serve", fake_serve)
    monkeypatch.setattr("sys.argv", ["main.py"])  # 无子命令 → 默认 serve
    main_mod.main()
    assert called.get("serve") is True
