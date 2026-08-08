@echo off
setlocal EnableExtensions
title 无限逻辑·语音助手 - build deploy package
cd /d "%~dp0"

REM ============================================================
REM  Build deploy package: copy deploy-needed files into deploy\
REM  Optionally compress deploy\ into deploy.zip
REM
REM  Usage: double-click, or run: package_deploy.bat
REM  Set DO_ZIP=0 below to skip the zip step.
REM ============================================================

set "DO_ZIP=1"
set "STAGE=%~dp0deploy"
set "ZIPFILE=%~dp0deploy.zip"

echo ============================================
echo   无限逻辑·语音助手 - build deploy package
echo ============================================
echo.

REM ---- 1. Clean old deploy dir ----
echo [1/4] Cleaning old deploy\ directory ...
if exist "%STAGE%" rmdir /s /q "%STAGE%"
mkdir "%STAGE%" 2>nul
mkdir "%STAGE%\data" 2>nul

REM ---- 2. Backend code and startup scripts ----
echo [2/4] Copying backend code and startup scripts ...
robocopy "%~dp0." "%STAGE%" main.py server.py start.bat install_deps.bat requirements.txt config.yaml /NJH /NJS /NFL /NDL >nul
robocopy "%~dp0core" "%STAGE%\core" /E /XD __pycache__ /NJH /NJS /NFL /NDL >nul
robocopy "%~dp0scripts" "%STAGE%\scripts" /E /NJH /NJS /NFL /NDL >nul

REM ---- 3. Config file (fall back to template if missing) ----
if not exist "%STAGE%\config.yaml" (
    echo   [NOTE] config.yaml not found, copied template. Fill it on the target machine.
    copy /y "%~dp0config.yaml.example" "%STAGE%\config.yaml" >nul
)

REM ---- 4. Frontend build output ----
echo [3/4] Copying frontend build output web\dist ...
if exist "%~dp0web\dist" (
    robocopy "%~dp0web\dist" "%STAGE%\web\dist" /E /NJH /NJS /NFL /NDL >nul
) else (
    echo   [WARN] web\dist not found, frontend NOT copied! Build it first: cd web ^&^& npm run build
)

echo [4/4] Deploy directory ready: %STAGE%
echo.
dir "%STAGE%"

REM ---- 5. Optional zip ----
if "%DO_ZIP%"=="1" (
    echo.
    echo Compressing to %ZIPFILE% ...
    if exist "%ZIPFILE%" del /q "%ZIPFILE%"
    powershell -NoProfile -Command "Compress-Archive -Path '%STAGE%\*' -DestinationPath '%ZIPFILE%' -Force"
    if exist "%ZIPFILE%" (echo Created: %ZIPFILE%) else (echo [WARN] zip creation failed)

)

echo.
echo NOTE: deploy\config.yaml contains API keys. Delete that file before sharing the package externally.
echo.
pause
exit /b 0
