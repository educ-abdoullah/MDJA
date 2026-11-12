@echo off
chcp 65001 >nul
setlocal
pushd "%~dp0"
title Gazette - Console de controle
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0bin\voir_pipeline.ps1" %*
set "task_result=%errorlevel%"
popd
echo.
echo Session de controle terminee. Code de sortie : %task_result%
pause
exit /b %task_result%
