# -*- coding: utf-8 -*-
"""单进程/单实例守卫：第二个进程（多 worker / 重复启动）必须被拒绝。

Single-instance guard: a second process (extra workers / duplicate start) must be
refused — sessions and SSE resume state live in this process's memory only.
"""
import os

import pytest

import server as server_module


@pytest.fixture
def isolated_lock(tmp_path, monkeypatch):
    """把锁文件重定向到 tmp（不碰真实 data/.server.lock）。"""
    monkeypatch.setattr(server_module.config, "ROOT_DIR", tmp_path, raising=False)
    return tmp_path / "data" / ".server.lock"


def test_second_acquire_rejected_then_released(isolated_lock):
    """首个获取成功；未释放前再获取 → RuntimeError；关闭释放后可再次获取。"""
    fh1 = server_module._acquire_instance_lock()
    try:
        assert isolated_lock.exists()
        # 通过持锁句柄自身读（第二句柄读被锁字节会被 Windows 拒绝——恰好证明锁生效）
        fh1.seek(0)
        assert fh1.read() == str(os.getpid())
        with pytest.raises(RuntimeError, match="另一个服务实例已在运行"):
            server_module._acquire_instance_lock()
    finally:
        fh1.close()
    # 释放后可重新获取（崩溃/退出时 OS 自动释放，不留陈旧锁）
    fh2 = server_module._acquire_instance_lock()
    fh2.close()


def test_lock_path_under_data_dir(isolated_lock):
    """锁文件固定在 <ROOT>/data/.server.lock（data 已 gitignore）。"""
    fh = server_module._acquire_instance_lock()
    fh.close()
    assert isolated_lock.name == ".server.lock"
    assert isolated_lock.parent.name == "data"
