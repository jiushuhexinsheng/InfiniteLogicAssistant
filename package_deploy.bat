@echo off
setlocal EnableExtensions
title InfiniteLogic Voice Assistant - build deploy package
cd /d "%~dp0"

REM ============================================================
REM  Build deploy package: copy deploy-needed files into deploy\
REM  Optionally compress deploy\ into deploy.zip
REM
REM  Usage: double-click, or run: package_deploy.bat
REM  Skip zip: package_deploy.bat 0   (or set DO_ZIP=0 below)
REM
REM  NOTE: if the backend is running FROM deploy\, stop it first
REM        or zipping will fail because data\ and memory\ are locked.
REM ============================================================

set "DO_ZIP=1"
if not "%1"=="" set "DO_ZIP=%1"
set "STAGE=%~dp0deploy"
set "ZIPFILE=%~dp0deploy.zip"

echo ============================================
echo   InfiniteLogic Voice Assistant - build deploy package
echo ============================================
echo.

REM ---- 1. Clean old deploy dir ----
echo [1/5] Cleaning old deploy\ directory ...
if exist "%STAGE%" rmdir /s /q "%STAGE%" 2>nul
if exist "%STAGE%" goto :clean_warn
goto :after_clean

:clean_warn
echo   [WARN] Old deploy\ not fully removed: files under data\ or memory\
echo          are locked by a running backend. Stop the backend first,
echo          then re-run this script; otherwise zipping will fail.
echo.

:after_clean
mkdir "%STAGE%" 2>nul

REM ---- 2. Backend code and startup scripts ----
REM 注意：不复制 config.yaml（可能含明文密钥）！部署包一律使用 config.yaml.example 模板
REM       （见步骤 3），密钥在目标机器上用环境变量或自行填写。
echo [2/5] Copying backend code and startup scripts ...
robocopy "%~dp0." "%STAGE%" main.py server.py start.bat install_deps.bat requirements.txt /NJH /NJS /NFL /NDL >nul
robocopy "%~dp0core" "%STAGE%\core" /E /XD __pycache__ /NJH /NJS /NFL /NDL >nul
robocopy "%~dp0scripts" "%STAGE%\scripts" /E /NJH /NJS /NFL /NDL >nul
robocopy "%~dp0skills" "%STAGE%\skills" /E /NJH /NJS /NFL /NDL >nul

REM ---- 3. Config file (template only, never the local one with keys) ----
if not exist "%STAGE%\config.yaml" (
    echo   [NOTE] copying config.yaml.example as config.yaml template. Fill it on the target machine.
    copy /y "%~dp0config.yaml.example" "%STAGE%\config.yaml" >nul
)

REM ---- 4. Frontend build output ----
echo [3/5] Copying frontend build output web\dist ...
if exist "%~dp0web\dist" goto :copy_web
echo   [WARN] web\dist not found, frontend NOT copied! Build it first: cd web ^&^& npm run build
goto :after_web
:copy_web
robocopy "%~dp0web\dist" "%STAGE%\web\dist" /E /NJH /NJS /NFL /NDL >nul
:after_web

REM ---- 5. Cleanup runtime artifacts (never ship logs / local db) ----
echo [4/5] Cleaning runtime artifacts (logs / memory db) from deploy\ ...
if exist "%STAGE%\data\*.log" del /q "%STAGE%\data\*.log" 2>nul
if exist "%STAGE%\data\*.sqlite" del /q "%STAGE%\data\*.sqlite" 2>nul
if exist "%STAGE%\data\*.db" del /q "%STAGE%\data\*.db" 2>nul
if exist "%STAGE%\memory" rd /s /q "%STAGE%\memory" 2>nul

echo [5/5] Deploy directory ready: %STAGE%
echo.
dir "%STAGE%"

REM ---- 6. Optional zip ----
if not "%DO_ZIP%"=="1" goto :after_zip
echo.
echo Compressing to %ZIPFILE% ...
if exist "%ZIPFILE%" del /q "%ZIPFILE%"
powershell -NoProfile -Command "Compress-Archive -Path '%STAGE%\*' -DestinationPath '%ZIPFILE%' -Force"
if exist "%ZIPFILE%" goto :zip_ok
echo.
echo   [FAIL] Zipping failed. Most common cause: backend still running.
echo          Stop the backend first, then re-run package_deploy.bat.
goto :after_zip
:zip_ok
echo Created: %ZIPFILE%

:after_zip
echo.
echo NOTE: deploy\config.yaml is the TEMPLATE (config.yaml.example) — no keys inside.
echo       Set keys via environment variables on the target machine before use.
echo.
pause
exit /b 0
