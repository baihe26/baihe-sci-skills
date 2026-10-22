@echo off
setlocal
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONDONTWRITEBYTECODE=1
set PYTHONNOUSERSITE=1
set PYTHONPATH=
set PYTHONHOME=
rem All entrypoints use runtime_config.py; existing personal settings retain priority.
if defined BAIHE_SCI_PYTHON (
  "%BAIHE_SCI_PYTHON%" "%~dp0工作台\源码\workbench.py" %*
) else (
  if exist "%~dp0运行环境\Python\python.exe" (
    "%~dp0运行环境\Python\python.exe" "%~dp0工作台\源码\workbench.py" %*
  ) else (
    python "%~dp0工作台\源码\workbench.py" %*
  )
)
exit /b %errorlevel%
