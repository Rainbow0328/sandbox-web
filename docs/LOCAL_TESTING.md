# 发布到 TestPyPI

本文档说明如何将 sandbox-console 构建并上传到 TestPyPI 测试平台。

---

## 1. 前置条件

| 依赖 | 版本要求 | 用途 |
|------|---------|------|
| Python | >= 3.11, < 3.15 | 运行构建工具 |
| Node.js | >= 18 | 构建前端（打包进 wheel） |
| npm | 随 Node.js 安装 | 前端依赖管理 |
| twine | 最新版 | 上传到 TestPyPI |

确认环境：

```powershell
python --version    # 3.11 ~ 3.14
node --version      # >= 18
npm --version
```

### 1.1 TestPyPI 账号

需要一个 TestPyPI 账号和 API Token：

1. 注册 https://test.pypi.org/account/register/
2. 进入 Account settings → API tokens → Add API token
3. Scope 选择 "Entire account"
4. 复制 token（以 `pypi-` 开头，只显示一次）

---

## 2. 目录结构前提

两个仓库需要平级放置：

```
sandbox-backend/
├── sandbox-console/       ← 本项目
│   ├── backend/
│   │   ├── pyproject.toml
│   │   ├── hatch_build.py
│   │   └── app/
│   └── frontend/
└── agents-backend/        ← SDK 依赖（本地源码）
    ├── pyproject.toml
    └── src/agent_sandbox_backends/
```

> 如果 `agents-backend` 不在 `../../agents-backend` 路径，构建时会自动从 PyPI 拉取 `agent-sandbox-backends`。

---

## 3. 构建发行包

### 3.1 安装构建工具

```powershell
cd d:\project\sandbox-backend\sandbox-console\backend
.\.venv\Scripts\python.exe -m pip install build twine
```

### 3.2 清理旧产物

```powershell
Remove-Item -Recurse -Force app\static -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path app\static -Force | Out-Null
Set-Content -Path app\static\.gitkeep -Value "# placeholder"
Remove-Item -Recurse -Force dist -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force *.egg-info -ErrorAction SilentlyContinue
```

### 3.3 构建 wheel + sdist

```powershell
.\.venv\Scripts\python.exe -m build
```

构建过程日志中应看到：

```
[build-frontend] Building frontend (npm run build)...
[build-frontend] Copied ...\frontend\dist → ...\backend\app\static
[build-frontend] Bundled static files from ...\backend\app\static
Successfully built sandbox_console-0.2.0-py3-none-any.whl
Successfully built sandbox-console-0.2.0.tar.gz
```

产物在 `dist/` 目录下：

```powershell
dir dist\
# sandbox_console-0.2.0-py3-none-any.whl
# sandbox-console-0.2.0.tar.gz
```

### 3.4 验证 wheel 内容

确认前端静态文件和入口点已正确打包：

```powershell
.\.venv\Scripts\python.exe -c "import zipfile; z=zipfile.ZipFile('dist/sandbox_console-0.2.0-py3-none-any.whl'); [print(n) for n in z.namelist() if 'static' in n or 'cli' in n or 'entry_points' in n]"
```

预期输出：

```
app/cli.py
app/static/index.html
app/static/assets/index-XXXX.css
app/static/assets/index-XXXX.js
sandbox_console-0.2.0.dist-info/entry_points.txt
```

---

## 4. 上传到 TestPyPI

### 4.1 方式一：命令行交互输入（推荐）

```powershell
.\.venv\Scripts\twine.exe upload --repository testpypi dist\*
```

按提示输入：

```
Enter your username: __token__
Enter your password: <粘贴你的 TestPyPI API Token>
```

> 用户名填 `__token__`，密码粘贴完整的 token（含 `pypi-` 前缀）。

### 4.2 方式二：配置文件（免交互）

创建或编辑 `~/.pypirc`（Windows: `C:\Users\<用户名>\.pypirc`）：

```ini
[testpypi]
repository = https://test.pypi.org/legacy/
username = __token__
password = pypi-你的token完整粘贴在这里
```

然后直接上传：

```powershell
.\.venv\Scripts\twine.exe upload --repository testpypi dist\*
```

上传成功后日志：

```
Uploading sandbox_console-0.2.0-py3-none-any.whl
100%|██████████████████████████████| 380k/380k [00:02<00:00, 150kB/s]
Uploading sandbox-console-0.2.0.tar.gz
100%|██████████████████████████████| 280k/280k [00:01<00:00, 180kB/s]

View at:
https://test.pypi.org/project/sandbox-console/0.2.0/
```

---

## 5. 从 TestPyPI 安装验证

### 5.1 创建全新虚拟环境

```powershell
cd d:\project\sandbox-backend\sandbox-console
python -m venv test-pypi-venv
```

### 5.2 安装

```powershell
.\test-pypi-venv\Scripts\pip.exe install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ sandbox-console
```

> `--index-url` 指向 TestPyPI（拉 sandbox-console），`--extra-index-url` 指向正式 PyPI（拉其他依赖，因为 TestPyPI 上可能没有 fastapi 等）。

### 5.3 验证命令

```powershell
.\test-pypi-venv\Scripts\sandbox-console-server.exe --help
```

### 5.4 启动服务

```powershell
.\test-pypi-venv\Scripts\sandbox-console-server.exe
```

浏览器打开 `http://localhost:9090` 确认 Web UI 正常。

### 5.5 自定义端口

```powershell
.\test-pypi-venv\Scripts\sandbox-console-server.exe --port 3000
```

---

## 6. 清理

```powershell
# 删除测试虚拟环境
Remove-Item -Recurse -Force d:\project\sandbox-backend\sandbox-console\test-pypi-venv

# 清理构建产物（恢复 .gitkeep 占位）
cd d:\project\sandbox-backend\sandbox-console\backend
Remove-Item -Recurse -Force app\static -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path app\static -Force | Out-Null
Set-Content -Path app\static\.gitkeep -Value "# placeholder"
Remove-Item -Recurse -Force dist -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force *.egg-info -ErrorAction SilentlyContinue
```

---

## 7. 发布新版本

修改版本号后重新构建上传即可。版本号在 `backend/pyproject.toml`：

```toml
version = "0.2.0"
```

改为 `0.1.1`、`0.2.0` 等，然后重复第 3、4 步。

> TestPyPI 不允许覆盖已上传的版本，每次必须递增版本号。

---

## 8. 发布到正式 PyPI（可选）

测试通过后，上传到正式 PyPI：

```powershell
.\.venv\Scripts\twine.exe upload dist\*
```

用户即可通过以下命令安装：

```powershell
pip install sandbox-console
sandbox-console-server
```

---

## 9. 常见问题

### Q: 上传报 "File already exists"

TestPyPI 不允许重复上传同一版本。需要递增 `pyproject.toml` 中的 `version` 后重新构建。

### Q: 安装时报找不到依赖

TestPyPI 上可能没有 fastapi、uvicorn 等依赖。安装时必须加 `--extra-index-url https://pypi.org/simple/`，让 pip 从正式 PyPI 拉取其他包。

### Q: 构建时报 "npm not found"

Node.js 未安装或不在 PATH 中。安装 Node.js 18+ 后重试。

### Q: 构建时报 "frontend source not found"

确保在 `backend/` 目录下执行构建，且 `frontend/` 目录与其平级。`hatch_build.py` 通过相对路径 `../frontend` 查找前端源码。

### Q: 上传报 403 Forbidden

API Token 不正确或已过期。重新在 TestPyPI 生成 Token，确保复制完整（含 `pypi-` 前缀），用户名填 `__token__`。

---

## 10. 用户使用指南（pip install 后）

以下是从用户视角的完整使用流程，适用于通过 `pip install sandbox-console` 安装后的场景。

### 10.1 安装

```bash
pip install sandbox-console
```

> 前端已预编译并嵌入 wheel，无需 Node.js，无需克隆源码。

### 10.2 启动服务

```bash
# 默认启动：监听 0.0.0.0:9090，同时提供 Web UI 和 API
sandbox-console-server

# 指定端口
sandbox-console-server --port 3000

# 仅本机访问
sandbox-console-server --host 127.0.0.1

# 同时指定
sandbox-console-server --host 127.0.0.1 --port 8088
```

启动后看到以下日志即表示成功：

```
[sandbox-console-server] Starting server on http://localhost:9090
[sandbox-console-server] Static files: .../app/static
```

浏览器打开 `http://localhost:9090` 即可使用 Web UI。

### 10.3 配置方式

配置优先级从高到低：**CLI 参数 > 环境变量 > .env 文件 > 默认值**。

#### 方式一：CLI 参数

```bash
sandbox-console-server --port 3000 --host 127.0.0.1
```

#### 方式二：环境变量

所有配置项使用 `EXPLORER_` 前缀。

```bash
# Linux / macOS
EXPLORER_PORT=3000 EXPLORER_HOST=127.0.0.1 sandbox-console-server

# Windows PowerShell
$env:EXPLORER_PORT = "3000"
$env:EXPLORER_HOST = "127.0.0.1"
sandbox-console-server
```

#### 方式三：.env 文件

在启动命令的当前工作目录下创建 `.env` 文件，CLI 会自动加载：

```ini
# .env
EXPLORER_PORT=3000
EXPLORER_HOST=127.0.0.1
EXPLORER_ADMIN_TOKEN=your-secret-token
EXPLORER_MASTER_KEY=your-64-char-hex-key
```

### 10.4 全部 CLI 参数

```
sandbox-console-server --help
```

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--port` | 服务端口 | `9090` |
| `--host` | 绑定地址 | `0.0.0.0` |
| `--dev` | 开发模式（vite + uvicorn 双进程，需源码） | 关闭 |
| `--build-only` | 仅构建前端，不启动服务 | 关闭 |
| `--frontend-port` | 前端开发服务器端口（仅 `--dev` 模式） | `5173` |

### 10.5 全部环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `EXPLORER_PORT` | `9090` | 服务端口 |
| `EXPLORER_HOST` | `0.0.0.0` | 绑定地址 |
| `EXPLORER_ADMIN_TOKEN` | (空) | 管理员 Bearer Token，为空则关闭认证 |
| `EXPLORER_MASTER_KEY` | 全零 | Fernet 加密密钥（64 位十六进制），用于加密连接凭据 |
| `EXPLORER_DATABASE_URL` | `sqlite+aiosqlite:///./data/explorer.db` | 数据库连接 |
| `EXPLORER_PUBLIC_URL` | `http://localhost:9090` | 外部访问 URL |
| `EXPLORER_CORS_ORIGINS` | (空) | CORS 允许的源，逗号分隔 |
| `EXPLORER_FRONTEND_PORT` | `5173` | 前端开发端口（仅 `--dev`） |
| `EXPLORER_STATIC_DIR` | 自动检测 | 前端静态文件目录（一般无需手动设置） |

### 10.6 生产环境配置示例

```ini
# .env (生产环境)
EXPLORER_PORT=9090
EXPLORER_HOST=0.0.0.0

# 安全：设置管理员 Token（留空则关闭认证）
EXPLORER_ADMIN_TOKEN=a1b2c3d4e5f6...

# 安全：设置加密密钥（用于加密连接密码等敏感信息）
# 生成方式: python -c "import secrets; print(secrets.token_hex(32))"
EXPLORER_MASTER_KEY=your-64-char-hex-string-here...

# 公开访问地址
EXPLORER_PUBLIC_URL=https://console.example.com

# 数据库（可选 PostgreSQL）
# EXPLORER_DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/sandbox_console

# CORS（如果前后端分离部署）
# EXPLORER_CORS_ORIGINS=https://console.example.com
```

### 10.7 停止服务

在终端按 `Ctrl+C` 即可优雅关闭。

### 10.8 验证服务状态

```bash
# 健康检查
curl http://localhost:9090/healthz
# {"status":"ok"}

# 就绪检查（含数据库连接检测）
curl http://localhost:9090/readyz
# {"status":"ready"}

# 指标
curl http://localhost:9090/metrics
```

### 10.9 常用场景

#### 场景一：本地快速试用

```bash
pip install sandbox-console
sandbox-console-server
# 打开 http://localhost:9090
```

无需任何配置，认证默认关闭，SQLite 数据库自动创建在 `./data/explorer.db`。

#### 场景二：团队内部部署

```bash
pip install sandbox-console

# 生成密钥
python -c "import secrets; print('Token:', secrets.token_hex(24)); print('Key:', secrets.token_hex(32))"

# 创建 .env
cat > .env << 'EOF'
EXPLORER_PORT=9090
EXPLORER_HOST=0.0.0.0
EXPLORER_ADMIN_TOKEN=<生成的Token>
EXPLORER_MASTER_KEY=<生成的Key>
EXPLORER_PUBLIC_URL=http://your-server:9090
EOF

# 启动
sandbox-console-server
```

#### 场景三：指定端口避免冲突

```bash
# OpenSandbox 服务占用 8080，Console 默认 9090
# 如需改用其他端口
sandbox-console-server --port 3000
```

#### 场景四：后台运行（Linux/macOS）

```bash
nohup sandbox-console-server --port 9090 > console.log 2>&1 &
```

#### 场景五：Systemd 服务（Linux）

创建 `/etc/systemd/system/sandbox-console.service`：

```ini
[Unit]
Description=Sandbox Console Server
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/sandbox-console
ExecStart=/opt/sandbox-console/venv/bin/sandbox-console-server
Restart=always
RestartSec=5
Environment=EXPLORER_ADMIN_TOKEN=your-token
Environment=EXPLORER_MASTER_KEY=your-key

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable sandbox-console
sudo systemctl start sandbox-console
```
