@echo off
setlocal
title CountyFlow AI
set "PROJECT_ROOT=%~dp0"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%PROJECT_ROOT%scripts\start-full.ps1"
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo.
    pause >nul
)

endlocal & exit /b %EXIT_CODE%
