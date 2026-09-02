# -*- coding: utf-8 -*-
"""CLI 命令测试 — build_parser 子命令注册 + check 聚合检测退出码。
CLI command tests — build_parser subcommand registration and check aggregate detection exit codes.
"""
import pytest

from cli import build_parser


def test_parser_registers_serve_and_check():
    """验证 build_parser 注册了 serve 与 check 两个子命令。Verifies build_parser registers the serve and check subcommands."""
    p = build_parser()
    assert callable(p.parse_args(["serve"]).func)
    assert callable(p.parse_args(["check"]).func)


def test_parser_empty_has_no_func():
    """验证无子命令时 parse_args 不附带 func，由 main 默认 serve。Verifies parse_args carries no func without a subcommand so main defaults to serve."""
    # 无子命令时由 main() 默认 serve（parser 不强制子命令）
    assert not hasattr(build_parser().parse_args([]), "func")


def test_cmd_check_exit_1_on_failure(monkeypatch):
    """验证 check 聚合检测存在失败项时以退出码 1 结束。Verifies cmd_check exits with code 1 when the aggregate check reports failures."""
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
    """验证 check 聚合检测全部正常或跳过时不退出。Verifies cmd_check does not exit when all aggregate checks are ok or skipped."""
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
    """验证 main 在无子命令时默认调用 serve。Verifies main defaults to calling serve when no subcommand is given."""
    import main as main_mod

    called = {}

    def fake_serve(_args):
        called["serve"] = True

    # build_parser 里的 func 引用 cli 包命名空间的 cmd_serve，故 mock cli.cmd_serve
    monkeypatch.setattr("cli.cmd_serve", fake_serve)
    monkeypatch.setattr("sys.argv", ["main.py"])  # 无子命令 → 默认 serve
    main_mod.main()
    assert called.get("serve") is True
