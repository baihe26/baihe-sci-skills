@echo off
setlocal
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONDONTWRITEBYTECODE=1
set PYTHONNOUSERSITE=1
set PYTHONPATH=
set PYTHONHOME=
if not defined BAIHE_SCI_CONFIG if exist "%~dp0baihe-sci.public.local.json" set "BAIHE_SCI_CONFIG=%~dp0baihe-sci.public.local.json"
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
