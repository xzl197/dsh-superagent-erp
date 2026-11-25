r"""Local InvenTree launcher for Windows.

Usage (double-click the batch files):
    contrib\windows\启动 InvenTree.bat    Start the server and open the browser
    contrib\windows\停止 InvenTree.bat    Stop the server
    contrib\windows\开发模式.bat          Run the auto-reloading dev server

Or run the script directly:
    python contrib\windows\inventree_launcher.py [--no-browser]
    python contrib\windows\inventree_launcher.py --stop
    python contrib\windows\inventree_launcher.py --dev

Application directory (holds .venv / gtk / logs / .tmp / .browser-profile):
- taken from the INVENTREE_APP_ROOT environment variable when set;
- otherwise located by walking up from the repository root until a directory
  containing .venv\Scripts\python.exe is found (the local deployment keeps the
  repository in the project\ sub-directory of D:\work\word_space\erp);
- if nothing is found, the repository root is used (standard development
  layout where .venv lives inside the repository).

The server listens on port 8123 by default (override with
INVENTREE_LOCAL_PORT). Edge is preferred over Chrome for opening the page;
set INVENTREE_LAUNCH_BROWSER to the absolute path of a browser executable to
override the automatic selection.

Notes on the browser arguments (verified on the deployment machine, reproduce
before changing them):
- the machine default browser (Lenovo SLBrowser) reports a permission error
  for http://localhost;
- Edge renderers spawned by the launcher (pythonw, no interactive session)
  require --no-sandbox, otherwise the window opens, GET /web returns 200 and
  no static asset is loaded at all (blank page).
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

BIND_HOST = '127.0.0.1'
HOST = 'localhost'
PORT = int(os.environ.get('INVENTREE_LOCAL_PORT', '8123'))
URL = f'http://{HOST}:{PORT}/'

# Absolute path of a browser executable, overriding the automatic selection
BROWSER_ENV = 'INVENTREE_LAUNCH_BROWSER'

# Directory holding .venv / gtk / logs
APP_ROOT_ENV = 'INVENTREE_APP_ROOT'

# This file lives in <repository>/contrib/windows/
REPO_ROOT = Path(__file__).resolve().parents[2]

_LOG_HANDLE = None


def venv_python(root: Path, gui: bool = False) -> Path | None:
    """Return the python executable of the virtual environment, if present."""
    scripts = root / '.venv' / 'Scripts'
    names = ('pythonw.exe', 'python.exe') if gui else ('python.exe', 'pythonw.exe')

    for name in names:
        candidate = scripts / name
        if candidate.exists():
            return candidate

    return None


def find_app_root() -> Path:
    """Locate the application directory used for runtime files."""
    override = os.environ.get(APP_ROOT_ENV, '').strip().strip('"')
    if override:
        return Path(override).expanduser().resolve()

    current = REPO_ROOT
    for _ in range(5):
        if venv_python(current) is not None:
            return current
        if current.parent == current:
            break
        current = current.parent

    return REPO_ROOT


def repo_root() -> Path:
    """Return the root directory of this repository."""
    return REPO_ROOT


def config_file(root: Path) -> Path | None:
    """Return the InvenTree configuration file, if one exists."""
    for candidate in (
        REPO_ROOT / 'config' / 'config.yaml',
        root / 'config' / 'config.yaml',
    ):
        if candidate.exists():
            return candidate

    return None


def log_path(root: Path) -> Path:
    """Return the launcher log file path, creating the logs directory."""
    path = root / 'logs'
    path.mkdir(parents=True, exist_ok=True)
    return path / 'launcher.log'


def log(root: Path, message: str) -> None:
    """Append one line to the launcher log, ignoring logging failures."""
    try:
        with open(log_path(root), 'a', encoding='utf-8') as handle:
            handle.write(f'{time.strftime("%Y-%m-%d %H:%M:%S")}  {message}\n')
    except Exception:
        pass


def message_box(root: Path, message: str) -> None:
    """Show a message box and record the message in the launcher log."""
    log(root, 'MESSAGE: ' + message)
    try:
        ctypes.windll.user32.MessageBoxW(None, message, 'InvenTree 启动失败', 0x10)
    except Exception:
        pass


def make_splash():
    """Show a small always-on-top window while the server boots."""
    try:
        import tkinter as tk
    except Exception:
        return None

    try:
        window = tk.Tk()
        window.title('InvenTree')
        window.geometry('460x130+120+120')
        window.attributes('-topmost', True)
        window.overrideredirect(True)
        tk.Label(
            window,
            text='正在启动 InvenTree 服务...\n首次启动约需 30-60 秒，请稍候（窗口会自动关闭）',
            font=('Microsoft YaHei UI', 10),
            justify='center',
        ).pack(expand=True, fill='both', padx=14, pady=14)
        window.update()
        return window
    except Exception:
        return None


def pump(window) -> None:
    """Process pending UI events of the splash window."""
    if window is None:
        return
    try:
        window.update()
    except Exception:
        pass


def close_splash(window) -> None:
    """Close the splash window if it is still open."""
    if window is None:
        return
    try:
        window.destroy()
    except Exception:
        pass


def browser_candidates() -> list[Path]:
    """List available browser executables, Edge before Chrome."""
    roots = [
        os.environ.get('PROGRAMFILES(X86)'),
        os.environ.get('PROGRAMFILES'),
        os.environ.get('LOCALAPPDATA'),
    ]
    relatives = (
        ('Microsoft', 'Edge', 'Application', 'msedge.exe'),
        ('Google', 'Chrome', 'Application', 'chrome.exe'),
    )

    found: list[Path] = []
    for root in roots:
        if not root:
            continue
        for parts in relatives:
            exe = Path(root).joinpath(*parts)
            if exe.exists() and exe not in found:
                found.append(exe)
    return found


def browser_profile_dir(root: Path) -> Path:
    """Return a dedicated browser profile directory.

    Keep the profile separate from the daily browser: leftover localhost site
    permissions, proxy extensions or policies in the daily profile can break
    page loading, while a clean user data directory works.
    """
    path = root / '.browser-profile'
    path.mkdir(parents=True, exist_ok=True)
    return path


def app_window_args(profile: Path, url: str) -> list[str]:
    """Build the application-window arguments for the browser.

    --no-sandbox is required, not an optimization: Edge renderers spawned by
    the launcher (pythonw, no UI session) cannot initialize the sandbox. The
    window opens and GET /web returns 200, but no /static asset is requested
    and the page stays blank. The page only contains the local InvenTree UI
    served from localhost, with no external content.
    """
    return [
        f'--user-data-dir={profile}',
        f'--app={url}',
        '--no-first-run',
        '--no-default-browser-check',
        '--no-sandbox',
        '--test-type',
        '--disable-features=LocalNetworkAccessChecks,PrivateNetworkAccessChecks,Translate,TranslateUI',
        '--window-size=1440,900',
    ]


def spawn_detached(exe: Path, args: list[str]) -> None:
    """Start the browser via ShellExecute, equivalent to a user double-click."""
    if os.name == 'nt':
        os.startfile(
            str(exe),
            'open',
            arguments=' '.join(f'"{arg}"' if ' ' in arg else arg for arg in args),
        )
    else:
        subprocess.Popen([str(exe), *args], start_new_session=True)


def quiet_browser_profile(root: Path, profile: Path) -> None:
    """Disable the browser translate prompt for the application window.

    The InvenTree HTML declares lang="en" while the browser UI is Chinese, so
    Edge offers to translate the page and the prompt covers the login form.
    Write the preference before the browser starts.
    """
    prefs = profile / 'Default' / 'Preferences'
    try:
        data = {}
        if prefs.exists():
            raw = prefs.read_text(encoding='utf-8')
            if raw.strip():
                data = json.loads(raw)
        translate = data.setdefault('translate', {})
        if translate.get('enabled') is False:
            return
        translate['enabled'] = False
        prefs.parent.mkdir(parents=True, exist_ok=True)
        prefs.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    except Exception as exc:
        log(root, f'Could not tune browser preferences: {exc}')


def open_browser(root: Path, url: str) -> None:
    """Open the web UI in an application window of Edge or Chrome."""
    candidates: list[Path] = []

    override = os.environ.get(BROWSER_ENV, '').strip().strip('"')
    if override:
        candidates.append(Path(override))
    candidates.extend(browser_candidates())

    profile = browser_profile_dir(root)
    quiet_browser_profile(root, profile)

    for exe in candidates:
        try:
            spawn_detached(exe, app_window_args(profile, url))
            log(root, f'Browser opened (app window): {exe}')
            time.sleep(1.5)
            return
        except Exception as exc:
            log(root, f'Failed to launch browser {exe}: {exc}')

    log(root, 'Falling back to system default browser')
    webbrowser.open(url)


def is_up(timeout: float = 2.0) -> bool:
    """Return True when the server API answers requests."""
    try:
        with urllib.request.urlopen(f'{URL}api/', timeout=timeout) as response:
            return response.status in (200, 401, 403)
    except Exception:
        return False


def port_listening() -> bool:
    """Return True when something is listening on the server port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.6)
        return sock.connect_ex((BIND_HOST, PORT)) == 0


def pids_on_port() -> list[str]:
    """Return the PIDs listening on the server port."""
    try:
        output = subprocess.run(
            ['netstat', '-ano'], capture_output=True, text=True, timeout=10, check=False
        ).stdout
    except Exception:
        return []

    pids: list[str] = []
    for line in output.splitlines():
        parts = line.split()
        # netstat -ano columns: Proto  Local  Foreign  State  PID
        if (
            len(parts) >= 5
            and parts[0] == 'TCP'
            and parts[1].endswith(f':{PORT}')
            and parts[3] == 'LISTENING'
            and parts[4] not in pids
        ):
            pids.append(parts[4])

    return pids


def kill_stale(root: Path) -> None:
    """Kill a stale process which still listens on the server port."""
    pids = pids_on_port()
    if not pids:
        return
    log(root, f'Killing stale process on port {PORT}: pid={pids[0]}')
    try:
        subprocess.run(
            ['taskkill', '/PID', pids[0], '/T', '/F'],
            capture_output=True,
            timeout=15,
            check=False,
        )
        time.sleep(2)
    except Exception as exc:
        log(root, f'Failed to kill stale process: {exc}')


def build_env(root: Path) -> dict:
    """Build the environment used to run the server and management commands."""
    env = dict(os.environ)
    tmp = root / '.tmp'
    tmp.mkdir(parents=True, exist_ok=True)
    env['TEMP'] = str(tmp)
    env['TMP'] = str(tmp)
    env['TMPDIR'] = str(tmp)
    env['PYTHONUTF8'] = '1'
    env['PYTHONIOENCODING'] = 'utf-8'

    gtk_bin = root / 'gtk' / 'Library' / 'bin'
    if gtk_bin.exists():
        env['WEASYPRINT_DLL_DIRECTORIES'] = str(gtk_bin)
        env['PATH'] = str(gtk_bin) + os.pathsep + env.get('PATH', '')

    venv_scripts = root / '.venv' / 'Scripts'
    env['PATH'] = str(venv_scripts) + os.pathsep + env.get('PATH', '')

    config = config_file(root)
    if config is not None:
        env['INVENTREE_CONFIG_FILE'] = str(config)

    return env


def start_server(root: Path):
    """Start the detached Django server and record its PID."""
    global _LOG_HANDLE

    python = venv_python(root, gui=True)
    if python is None:
        raise FileNotFoundError(
            f'未找到 Python 虚拟环境：{root}\\.venv\n请先按 CONTRIBUTING.md 创建虚拟环境。'
        )

    manage = repo_root() / 'src' / 'backend' / 'InvenTree' / 'manage.py'

    if not manage.exists():
        raise FileNotFoundError(f'manage.py not found: {manage}')

    log_dir = root / 'logs'
    log_dir.mkdir(parents=True, exist_ok=True)

    _LOG_HANDLE = open(  # noqa: SIM115
        log_dir / 'server.log', 'a', encoding='utf-8', buffering=1
    )
    _LOG_HANDLE.write(f'\n=== start {time.strftime("%Y-%m-%d %H:%M:%S")} ===\n')
    _LOG_HANDLE.flush()

    flags = 0
    if os.name == 'nt':
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP

    proc = subprocess.Popen(
        [str(python), str(manage), 'runserver', f'{BIND_HOST}:{PORT}', '--noreload'],
        cwd=str(manage.parent),
        env=build_env(root),
        stdout=_LOG_HANDLE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        creationflags=flags,
    )

    (log_dir / 'server.pid').write_text(str(proc.pid), encoding='utf-8')
    log(root, f'Server started: pid={proc.pid}')
    return proc


def wait_until_up(root: Path, proc, timeout: float = 180.0) -> bool:
    """Wait for the server to answer, returning False on timeout or early exit."""
    deadline = time.time() + timeout
    splash = make_splash()

    try:
        while time.time() < deadline:
            pump(splash)

            if is_up():
                return True

            if proc.poll() is not None:
                log(root, f'Server process exited early: code={proc.returncode}')
                return False

            for _ in range(10):
                pump(splash)
                time.sleep(0.1)
    finally:
        close_splash(splash)

    log(root, 'Timeout waiting for server to become ready')
    return False


def stop_server(root: Path) -> int:
    """Stop the running server using the PID file and the listening port."""
    stopped = False
    pid_file = root / 'logs' / 'server.pid'

    if pid_file.exists():
        pid = pid_file.read_text(encoding='utf-8').strip()
        if pid:
            print(f'正在停止 InvenTree 服务 PID={pid} ...')
            subprocess.run(
                ['taskkill', '/PID', pid, '/T', '/F'], capture_output=True, check=False
            )
            stopped = True
        pid_file.unlink(missing_ok=True)
    else:
        print('未找到运行记录，尝试按端口结束进程...')

    for pid in pids_on_port():
        print(f'结束占用端口 {PORT} 的进程 PID={pid} ...')
        subprocess.run(
            ['taskkill', '/PID', pid, '/T', '/F'], capture_output=True, check=False
        )
        stopped = True

    log(root, f'Stop requested (stopped={stopped})')
    print('已停止。' if stopped else '未发现正在运行的 InvenTree 服务。')
    return 0


def dev_server(root: Path, open_page: bool) -> int:
    """Run the auto-reloading Django development server in the foreground."""
    python = venv_python(root)
    if python is None:
        print(f'未找到 Python 虚拟环境：{root}\\.venv')
        print('请先按 CONTRIBUTING.md 的说明创建虚拟环境并安装开发依赖。')
        return 2

    invoke = root / '.venv' / 'Scripts' / 'invoke.exe'
    command = [str(invoke)] if invoke.exists() else [str(python), '-m', 'invoke']

    if port_listening():
        kill_stale(root)

    if open_page:
        open_browser(root, URL)

    print(f'开发模式: Django 调试服务器 + 自动重载 (Ctrl+C 退出) {URL}')
    log(root, 'Starting development server')

    return subprocess.call(
        [*command, 'dev.server', '--address', f'{BIND_HOST}:{PORT}'],
        cwd=str(repo_root()),
        env=build_env(root),
    )


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Parse the launcher command line arguments."""
    parser = argparse.ArgumentParser(description='InvenTree 本地启动器（Windows）')
    parser.add_argument(
        '--stop', action='store_true', help='停止正在运行的 InvenTree 服务'
    )
    parser.add_argument(
        '--dev', action='store_true', help='以开发模式启动（Django 自动重载）'
    )
    parser.add_argument(
        '--no-browser', action='store_true', help='只启动服务，不打开浏览器'
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run the launcher and return a process exit code."""
    args = parse_args(argv)
    root = find_app_root()
    log(root, f'Launcher started (app_root={root}, repo_root={repo_root()})')

    if args.stop:
        return stop_server(root)

    if args.dev:
        return dev_server(root, open_page=not args.no_browser)

    if is_up():
        log(root, 'Server already running')
        if not args.no_browser:
            open_browser(root, URL)
        return 0

    if port_listening():
        kill_stale(root)

    try:
        proc = start_server(root)
    except Exception as exc:
        message_box(
            root, f'无法启动 InvenTree 服务：\n{exc}\n\n请查看日志：{log_path(root)}'
        )
        return 2

    if not wait_until_up(root, proc):
        message_box(
            root,
            'InvenTree 服务启动失败或超时。\n\n'
            f'服务日志：{root / "logs" / "server.log"}\n'
            f'启动日志：{log_path(root)}',
        )
        return 3

    if not args.no_browser:
        open_browser(root, URL)

    time.sleep(6)
    if proc.poll() is not None:
        log(
            root,
            f'Server exited shortly after startup (code={proc.returncode}); retrying once',
        )
        try:
            proc = start_server(root)
        except Exception as exc:
            message_box(root, f'InvenTree 服务异常退出，重启失败：\n{exc}')
            return 4

        if not wait_until_up(root, proc):
            message_box(
                root,
                f'InvenTree 服务无法保持运行，请查看 {root / "logs" / "server.log"}',
            )
            return 5

    return 0


if __name__ == '__main__':
    sys.exit(main())
