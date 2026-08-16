@echo off
setlocal EnableExtensions
title ÎÞÏÞÂß¼­¡¤ÓïÒôÖúÊÖ
cd /d "%~dp0"

echo ============================================
echo   ÎÞÏÞÂß¼­¡¤ÓïÒôÖúÊÖ - one-click start
echo ============================================
echo.

REM ---- 1. Check Python ----
python --version >nul 2>&1
if errorlevel 1 goto :no_python

REM ---- 2. Check / install dependencies (online-first, offline fallback) ----
python -c "import httpx, fastapi, uvicorn, yaml, loguru" >nul 2>&1
if not errorlevel 1 goto :deps_ok
echo [INFO] Missing dependencies, installing online from PyPI ...
python -m pip install -r requirements.txt --disable-pip-version-check
if not errorlevel 1 goto :deps_ok
echo [WARN] Online install failed, trying offline scripts\libs ...
python -m pip install --no-index --find-links=scripts\libs -r requirements.txt --disable-pip-version-check
python -c "import httpx, fastapi, uvicorn, yaml, loguru" >nul 2>&1
if errorlevel 1 goto :deps_fail

:deps_ok

REM ---- 3. Connectivity test (LLM / ASR) ----
echo [TEST] Checking LLM / ASR connectivity ...
python main.py test
if errorlevel 1 goto :test_warn
echo [TEST] LLM / ASR connectivity OK.
goto :dist_check

:test_warn
echo [WARN] LLM / ASR connectivity test failed - see data/agent.log.
echo   Starting anyway (services will report errors when used).

:dist_check
REM ---- 4. Check frontend build ----
if exist "web\dist\index.html" goto :dist_ok
echo [INFO] No web\dist build detected.
echo   Option A: run "npm run build", then served by this server
echo   Option B: dev mode, run "cd web && npm run dev" for port 5173

:dist_ok

REM ---- 5. Start ----
echo.
echo [START] python main.py serve
echo   Browser will open http://127.0.0.1:8520
echo   Press Ctrl+C to stop
echo.
python main.py serve

pause
exit /b 0

:no_python
echo [ERROR] Python not found. Please install Python 3.14+ and add it to PATH.
pause
exit /b 1

:deps_fail
echo [ERROR] Dependency install failed. Check network, or scripts\libs
echo        (offline bundle targets Python 3.14 / win_amd64).
pause
exit /b 1
