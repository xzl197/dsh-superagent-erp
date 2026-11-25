# Windows 本地启动脚本

本目录提供在本机运行 InvenTree 的启动脚本，替代此前只保存在个人电脑上的
`启动 InvenTree.bat`、`停止 InvenTree.bat`、`开发模式.bat` 和启动器。

| 文件 | 用途 |
| --- | --- |
| `启动 InvenTree.bat` | 启动服务并打开网页（已运行时只打开网页） |
| `停止 InvenTree.bat` | 按 `logs\server.pid` 和 8123 端口停止服务 |
| `开发模式.bat` | Django 调试服务器 + 自动重载（Ctrl+C 退出） |
| `inventree_launcher.py` | 三个批处理脚本共用的启动器实现 |

## 运行前提

- Windows 10/11，已安装 Python 3.12（批处理会优先使用应用目录下的
  `.venv\Scripts\pythonw.exe`，找不到时回退到 `PATH` 中的 `pythonw`）。
- 应用目录中存在 Python 虚拟环境 `.venv`（后端依赖与 `invoke` 已安装）。
- 首次运行前已完成数据库迁移和静态资源收集，可参考
  [CONTRIBUTING.md](../../CONTRIBUTING.md#development-setup)。
- 需要生成 PDF 报表/标签时，应用目录下需有 GTK 运行时 `gtk\Library\bin`。

## 应用目录

启动器需要一个“应用目录”来存放 `.venv`、`gtk`、`logs`、`.tmp` 和
`.browser-profile`。查找顺序：

1. 环境变量 `INVENTREE_APP_ROOT` 指定的目录；
2. 从仓库根目录逐级向上查找包含 `.venv\Scripts\python.exe` 的目录
   （本机部署布局为 `D:\work\word_space\erp`，仓库位于其 `project\` 子目录）；
3. 都找不到时使用仓库根目录（`.venv` 直接建在仓库里的标准开发布局）。

## 使用

双击对应批处理即可，也可以带参数运行（参数会传给启动器）：

```bat
REM 只启动服务、不打开浏览器（用于自动化测试）
启动 InvenTree.bat --no-browser

REM 停止服务（双击即可，无需参数）
停止 InvenTree.bat

REM 开发模式
开发模式.bat
```

`启动 InvenTree.bat` 默认用 Edge（其次 Chrome）的应用窗口打开
<http://localhost:8123/>；服务已在运行时只打开网页，不会重复启动。

直接用 Python 运行：

```bat
python contrib\windows\inventree_launcher.py
python contrib\windows\inventree_launcher.py --no-browser
python contrib\windows\inventree_launcher.py --stop
python contrib\windows\inventree_launcher.py --dev
```

| 环境变量 | 说明 |
| --- | --- |
| `INVENTREE_APP_ROOT` | 应用目录（`.venv` / `gtk` / `logs` 所在目录） |
| `INVENTREE_LOCAL_PORT` | 服务端口，默认 `8123` |
| `INVENTREE_LAUNCH_BROWSER` | 指定浏览器 exe 绝对路径，覆盖自动选择结果 |

## 日志

- `logs\launcher.log`：启动器步骤、浏览器选择、失败原因；
- `logs\server.log`：服务日志；
- `logs\server.pid`：当前服务进程 PID。

## 修改前端后让页面生效

启动器运行的是编译后的前端静态资源。修改 `src/frontend` 或翻译文件后，
需要重新编译前端并收集静态文件，然后重启服务：

```bat
cd src\frontend
yarn run compile
yarn run build

cd ..\backend\InvenTree
python manage.py collectstatic --no-input
```

如果 `manage.py` 报 `cannot load library 'libgobject-2.0-0'`，说明
WeasyPrint 找不到 GTK：把应用目录下的 `gtk\Library\bin` 同时加入 `PATH`
和 `WEASYPRINT_DLL_DIRECTORIES` 环境变量（启动器和 `开发模式.bat` 会自动设置）。

## 已知问题

- **页面纯白（只有标题、没有登录框）**：由启动器（`pythonw`，无交互会话）
  派生的 Edge 渲染进程必须带 `--no-sandbox`，否则静态资源全部不加载。
  修改 `app_window_args()` 前请先复现该问题。
- **“权限不足 / 无法访问此页面”**：说明这次打开的是系统默认浏览器
  （本机为联想 SLBrowser），不是启动器的 Edge/Chrome 应用窗口；查看
  `logs\launcher.log` 末行是否为 `Browser opened (app window)`。
- **启动超时**：先看 `logs\server.log` 最后 20 行，常见原因是端口被占用、
  依赖文件被移动或杀毒软件拦截。可先执行 `停止 InvenTree.bat` 再重试。
