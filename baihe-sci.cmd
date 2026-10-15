@echo off
setlocal
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONDONTWRITEBYTECODE=1
if defined BAIHE_SCI_PYTHON (
  "%BAIHE_SCI_PYTHON%" "%~dp0工作台\源码\workbench.py" %*
) else (
  python "%~dp0工作台\源码\workbench.py" %*
)
exit /b %errorlevel%
