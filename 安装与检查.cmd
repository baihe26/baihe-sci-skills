@echo off
setlocal
chcp 65001 >nul
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0安装\准备环境.ps1" %*
set "RESULT=%errorlevel%"
if not "%RESULT%"=="0" echo 安装或检查未完成，请将上方错误交给本机Codex处理；不要覆盖已有环境。
pause
exit /b %RESULT%
