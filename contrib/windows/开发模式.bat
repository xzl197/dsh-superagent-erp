@echo off
chcp 65001 >nul
REM 开发模式：Django 调试服务器 + 自动重载（Ctrl+C 退出）。
REM 先结束占用 8123 端口的残留进程，再启动开发服务器。
setlocal
set "SCRIPT=%~dp0inventree_launcher.py"
set "PYTHON="
if defined INVENTREE_APP_ROOT if exist "%INVENTREE_APP_ROOT%\.venv\Scripts\python.exe" set "PYTHON=%INVENTREE_APP_ROOT%\.venv\Scripts\python.exe"
if not defined PYTHON if exist "%~dp0..\..\..\..\.venv\Scripts\python.exe" set "PYTHON=%~dp0..\..\..\..\.venv\Scripts\python.exe"
if not defined PYTHON if exist "%~dp0..\..\..\.venv\Scripts\python.exe" set "PYTHON=%~dp0..\..\..\.venv\Scripts\python.exe"
if not defined PYTHON if exist "%~dp0..\..\.venv\Scripts\python.exe" set "PYTHON=%~dp0..\..\.venv\Scripts\python.exe"
if not defined PYTHON set "PYTHON=python.exe"
"%PYTHON%" "%SCRIPT%" --dev %*
