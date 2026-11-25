@echo off
chcp 65001 >nul
REM 启动 InvenTree 服务并打开网页（服务已在运行时仅打开网页）。
REM 应用目录（.venv / gtk / logs）优先取 INVENTREE_APP_ROOT，否则依次在
REM 仓库上级目录中查找；找不到时使用 PATH 中的 pythonw。
setlocal
set "SCRIPT=%~dp0inventree_launcher.py"
set "PYTHONW="
if defined INVENTREE_APP_ROOT if exist "%INVENTREE_APP_ROOT%\.venv\Scripts\pythonw.exe" set "PYTHONW=%INVENTREE_APP_ROOT%\.venv\Scripts\pythonw.exe"
if not defined PYTHONW if exist "%~dp0..\..\..\..\.venv\Scripts\pythonw.exe" set "PYTHONW=%~dp0..\..\..\..\.venv\Scripts\pythonw.exe"
if not defined PYTHONW if exist "%~dp0..\..\..\.venv\Scripts\pythonw.exe" set "PYTHONW=%~dp0..\..\..\.venv\Scripts\pythonw.exe"
if not defined PYTHONW if exist "%~dp0..\..\.venv\Scripts\pythonw.exe" set "PYTHONW=%~dp0..\..\.venv\Scripts\pythonw.exe"
if not defined PYTHONW set "PYTHONW=pythonw.exe"
start "" "%PYTHONW%" "%SCRIPT%" %*
