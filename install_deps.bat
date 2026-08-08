@echo off
setlocal EnableExtensions
title 无限逻辑·语音助手 - offline install
cd /d "%~dp0"

echo ============================================
echo   无限逻辑·语音助手 - offline dependency install
echo ============================================
echo.

echo [1/2] Installing Python dependencies from scripts\libs ...
python -m pip install --no-index --find-links=scripts\libs -r requirements.txt --disable-pip-version-check
if errorlevel 1 goto :fallback

echo [2/2] Dependencies installed.
echo.
echo   Done. Edit config.yaml then run: python main.py serve
pause
exit /b 0

:fallback
echo [WARN] Offline install failed, trying online source ...
python -m pip install -r requirements.txt
if errorlevel 1 goto :fail
echo [2/2] Dependencies installed via online source.
pause
exit /b 0

:fail
echo [ERROR] Dependency install failed. Check network or scripts\libs folder.
pause
exit /b 1
