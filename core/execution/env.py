# -*- coding: utf-8 -*-
"""执行层子进程环境：白名单继承，避免把 API Key / token 泄漏给被执行的命令。

Subprocess environment for the execution layer: an allow-list inheritance so API
keys and tokens never leak into commands/scripts the model runs.

被执行的 shell/Python 子进程默认只继承启动、路径与本地化所需的基础变量；
需要额外变量的用户可在 `tools.env_passthrough` 显式列出键名。

Executed shell/Python children inherit only the basics needed for startup, PATH and
localisation. Extra variables can be opted in via `tools.env_passthrough`.
"""
from __future__ import annotations

import os

from core import config

# 跨平台基础变量：启动、路径、临时目录、本地化。
# Cross-platform basics: process startup, PATH, temp dirs, localisation.
_BASE_KEYS = frozenset({
    "PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "COMSPEC",
    "TEMP", "TMP", "TMPDIR", "USERPROFILE", "HOMEDRIVE", "HOMEPATH", "HOME",
    "APPDATA", "LOCALAPPDATA", "PROGRAMDATA", "PROGRAMFILES", "PROGRAMFILES(X86)",
    "COMMONPROGRAMFILES", "PSMODULEPATH", "NUMBER_OF_PROCESSORS",
    "PROCESSOR_ARCHITECTURE", "OS", "USERNAME", "USERDOMAIN", "USER", "LOGNAME",
    "SHELL", "LANG", "LC_ALL", "LC_CTYPE", "TZ",
})


def subprocess_env() -> dict[str, str]:
    """构造子进程环境：白名单 + 显式放行键 + UTF-8 输出约定。

    Build the child environment: allow-list + explicit passthrough + UTF-8 output.

    Returns:
        可直接传给 `subprocess` / `asyncio.create_subprocess_*` 的 env 字典。
        An env dict ready for `subprocess` / `asyncio.create_subprocess_*`.
    """
    env = {key: os.environ[key] for key in _BASE_KEYS if key in os.environ}
    for key in getattr(config.settings.tools, "env_passthrough", []) or []:
        if key in os.environ:
            env[key] = os.environ[key]
    # 子进程输出统一 UTF-8：Python 走 -X utf8，其它程序也能按 UTF-8 解码。
    # Uniform UTF-8 child output: Python runs with -X utf8, other programs can be
    # decoded as UTF-8 too.
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUTF8", "1")
    return env
