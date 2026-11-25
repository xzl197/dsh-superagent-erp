@echo off
chcp 65001 >nul
REM 停止 InvenTree 服务（按 logs\server.pid 与 8123 端口结束进程）。
setlocal
set "SCRIPT=%~dp0inventree_launcher.py"
set "PYTHON="
if defined INVENTREE_APP_ROOT if exist "%INVENTREE_APP_ROOT%\.venv\Scripts\python.exe" set "PYTHON=%INVENTREE_APP_ROOT%\.venv\Scripts\python.exe"
if not defined PYTHON if exist "%~dp0..\..\..\..\.venv\Scripts\python.exe" set "PYTHON=%~dp0..\..\..\..\.venv\Scripts\python.exe"
if not defined PYTHON if exist "%~dp0..\..\..\.venv\Scripts\python.exe" set "PYTHON=%~dp0..\..\..\.venv\Scripts\python.exe"
if not defined PYTHON if exist "%~dp0..\..\.venv\Scripts\python.exe" set "PYTHON=%~dp0..\..\.venv\Scripts\python.exe"
if not defined PYTHON set "PYTHON=python.exe"
"%PYTHON%" "%SCRIPT%" --stop %*
REM 等待 2 秒，便于查看输出（ping 比 timeout 在重定向输入时更可靠）
ping -n 3 127.0.0.1 >nul
