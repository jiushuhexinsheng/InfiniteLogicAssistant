@echo off
setlocal EnableExtensions
title 无限逻辑·语音助手 - dependency install
cd /d "%~dp0"

echo ============================================
echo   无限逻辑·语音助手 - dependency install
echo   (online PyPI first, offline scripts\libs fallback)
echo ============================================
echo.

echo [1/2] Installing dependencies from online PyPI ...
python -m pip install -r requirements.txt --disable-pip-version-check
if not errorlevel 1 goto :online_ok

echo [WARN] Online install failed, trying offline scripts\libs ...
python -m pip install --no-index --find-links=scripts\libs -r requirements.txt --disable-pip-version-check
if not errorlevel 1 goto :offline_ok

echo [ERROR] Dependency install failed. Check network, or scripts\libs
echo        (offline bundle targets Python 3.14 / win_amd64).
pause
exit /b 1

:online_ok
echo [2/2] Dependencies installed (online source).
echo.
echo   Done. Edit config.yaml then run: python main.py serve
pause
exit /b 0

:offline_ok
echo [2/2] Dependencies installed (offline scripts\libs source).
echo.
echo   Done. Edit config.yaml then run: python main.py serve
pause
exit /b 0
