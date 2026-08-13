# -*- mode: python ; coding: utf-8 -*-
# 桌面悬浮球打包 spec — PyInstaller onefile
# 说明：exe 运行时按 exe 所在目录找 config.yaml / data（core.config 已做 frozen 处理）
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = [
    'desktop_py.api', 'desktop_py.ball', 'desktop_py.mini_panel',
    'desktop_py.sse', 'desktop_py.tray', 'desktop_py.theme', 'desktop_py.backend_runner',
    'server',
    'core.config', 'core.logger', 'core.status', 'core.recent',
    'core.agent.base', 'core.agent.coordinator', 'core.agent.legacy',
    'core.mcp.manager', 'core.mcp.client',
    'core.scheduler.runner', 'core.scheduler.scheduler',
    'core.voice.manager', 'core.voice.wake',
    'core.execution.envprobe', 'core.execution.shell', 'core.execution.python',
    'core.execution.fs', 'core.execution.gui',
    'core.rag.indexer', 'core.rag.retriever',
    'core.memory.context', 'core.memory.extract', 'core.memory.facts',
    'core.tools.base', 'core.tools.basic', 'core.tools.mcp_bridge',
    'core.tools.memory_tools', 'core.tools.schedule_tools', 'core.tools.skill_tools',
    'core.tools.gui_tools', 'core.tools.calculator', 'core.tools.datetime_tool',
    'core.tools.search', 'core.tools.weather',
    'core.orchestrator.session', 'core.orchestrator.intent', 'core.orchestrator.task',
    'core.orchestrator.clarify', 'core.orchestrator.confirm', 'core.orchestrator.executor',
    'core.orchestrator.control', 'core.orchestrator.pipeline',
]
hiddenimports += collect_submodules('uvicorn')

a = Analysis(
    ['desktop_py/main.py'],
    pathex=['.'],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    # 可选重依赖：排除可离线装/懒加载的，缺了后端相关功能优雅降级（语音/mcp/gui 在打包版暂缺）
    excludes=[
        'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets', 'PySide6.QtMultimedia',
        'PySide6.QtCharts', 'PySide6.Qt3DCore',
        'mcp', 'vosk', 'sounddevice', 'pyautogui', 'pygetwindow', 'pyscreeze', 'PIL',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='无限逻辑悬浮球',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    icon='desktop_py/icon.ico',
)

coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=True, name='无限逻辑悬浮球')
