# Sandbox Console

沙箱管理 Web 控制台 —— 让 AI Agent 在沙箱里干活，人类在浏览器里围观。

基于 FastAPI（后端）+ React/TypeScript（前端）构建，支持 pip 一键安装、Docker 部署或源码开发模式。前端预编译打包进 wheel，**无需 Node.js**。

> 配套 SDK：[`agent-sandbox-backends`](https://gitee.com/rainbow-zhou/agent-sandbox-backend.git)（需从本地源码安装，见下文）

## 核心功能

| 功能 | 说明 |
|------|------|
| 沙箱管理 | 创建、列表、暂停、恢复、删除沙箱 |
| 文件浏览器 | 浏览、读取、编辑（Monaco Editor）、上传、下载 |
| 命令执行器 | 执行命令，SSE 实时流式输出 stdout/stderr |
| 终端 | 基于 xterm.js + WebSocket 的交互式 Shell |
| 历史时间线 | Agent 和 Console 的所有操作统一展示，可过滤、可下钻 |
| **文件备份与回滚** | 类 Git 的文件级备份，支持自动/手动备份、内容预览、一键回滚 |
| 连接管理 | 注册多个 OpenSandbox 实例，加密存储凭证，一键测试连通性 |
| 可观测性 | 健康检查、Prometheus 指标、结构化日志 |

## 快速开始

### 前置：安装 SDK（本地源码）

SDK `agent-sandbox-backends` 尚未发布到 PyPI，需从本地源码安装。假设两个仓库平级放置：

```
sandbox-backend/
├── agents-backend/      ← SDK 源码
└── sandbox-console/     ← 本项目
```

```bash
# 安装 SDK（含 deepagents 适配器）
cd agents-backend
pip install -e ".[deepagents]"

# 安装 Web 控制台（已发布到 PyPI，可直接 pip install）
pip install sandbox-console
```

> 如果 `sandbox-console` 也想从源码安装（便于调试），见下方「源码运行」。

### 方式一：pip 安装（推荐）

```bash
pip install sandbox-console
```

启动服务：

```bash
sandbox-console-server                      # 默认 http://localhost:9090
sandbox-console-server --port 3000          # 自定义端口
sandbox-console-server --host 127.0.0.1     # 仅本机访问
```

打开 `http://localhost:9090` 即可使用。本地使用无需任何环境变量，鉴权默认关闭。

> **注意：** Console 默认端口 **9090**，避开 OpenSandbox Service 的 **8080**。

### 方式二：源码运行

需要 Python 3.11+ 和 Node.js 18+。

```bash
python start.py          # 生产模式：构建前端 + 启动服务
python start.py --dev    # 开发模式：前端热更新 (:5173) + 后端 (:9090)
```

或以可编辑模式安装后使用 CLI：

```bash
cd backend
pip install -e .
sandbox-console-server --dev
```

### Docker 部署

> Docker 构建需要 [`agent-sandbox-backends`](https://gitee.com/rainbow-zhou/agent-sandbox-backend.git) SDK 源码作为同级目录。

```bash
# 构建（从包含两个仓库的父目录执行）
docker build -f sandbox-console/docker/Dockerfile -t sandbox-console .

# 运行
docker run -d -p 9090:9090 -v sandbox-console-data:/data sandbox-console
```

或使用 Docker Compose：

```bash
cd sandbox-console
docker compose up -d
```

## 端口配置

端口可通过 **CLI 参数**、**环境变量**或 **`.env` 文件**配置（优先级：CLI > 环境变量 > .env > 默认值）。

| 参数 | CLI 参数 | 环境变量 | 默认值 | 模式 |
|------|---------|---------|--------|------|
| 后端端口 | `--port` | `EXPLORER_PORT` | `9090` | 全部 |
| 后端地址 | `--host` | `EXPLORER_HOST` | `0.0.0.0` | 全部 |
| 前端端口 | `--frontend-port` | `EXPLORER_FRONTEND_PORT` | `5173` | 仅开发模式 |

```bash
# 示例
sandbox-console-server --port 3000                              # 自定义端口
sandbox-console-server --dev --port 3000 --frontend-port 3001   # 自定义开发端口
EXPLORER_PORT=3000 sandbox-console-server                       # 通过环境变量
```

## 环境变量配置

所有配置使用 `EXPLORER_` 前缀。详见 [`.env.example`](.env.example)。

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `EXPLORER_ADMIN_TOKEN` | (空) | 管理员 Bearer Token，为空则关闭认证 |
| `EXPLORER_MASTER_KEY` | 全零 | Fernet 加密密钥（64 位十六进制），用于加密连接凭证 |
| `EXPLORER_DATABASE_URL` | `sqlite+aiosqlite:///./data/explorer.db` | 数据库连接 |
| `EXPLORER_PORT` | `9090` | 服务端口 |
| `EXPLORER_HOST` | `0.0.0.0` | 绑定地址 |
| `EXPLORER_FRONTEND_PORT` | `5173` | 前端开发端口（仅 `--dev`） |
| `EXPLORER_PUBLIC_URL` | `http://localhost:9090` | 外部访问 URL |
| `EXPLORER_CORS_ORIGINS` | (空) | CORS 允许的源，逗号分隔 |

## 文件备份与回滚

Console 内置类 Git 的文件级备份系统，与 SDK 共享沙箱内的 SQLite 历史数据库。

### 工作原理

```
Agent 写入/删除文件          Agent 执行匹配命令
       │                           │
       ▼                           ▼
  SDK BackupManager 自动触发备份   │
       │                           │
       ▼                           ▼
  备份数据写入沙箱内 history.sqlite3 (file_backups 表)
       │
       ▼
  Console 读取同一数据库 → 展示备份列表 → 支持预览/回滚/删除
```

### 备份触发方式

SDK 端通过 `BackupConfig` 配置备份规则：

```python
from agent_sandbox_backends import (
    BackupConfig, BackupRule, BackupTrigger, create_opensandbox_backend,
)

backup_config = BackupConfig(
    enabled=True,
    max_backups_per_file=15,          # 单个文件最多保留 15 个备份
    rules=(
        # 规则1：所有 .py 文件在写入/删除时自动备份
        BackupRule(
            name="python-files",
            include=("**/*.py",),
            triggers=(BackupTrigger.ON_WRITE, BackupTrigger.ON_DELETE),
            max_file_size=10 * 1024 * 1024,  # 跳过大于 10MB 的文件
        ),
        # 规则2：执行 pip install 前备份所有 src/ 下的文件
        BackupRule(
            name="before-pip-install",
            include=("src/**",),
            exclude=("src/__pycache__/**",),
            triggers=(BackupTrigger.ON_COMMAND,),
            command_patterns=(r"pip\s+install",),
        ),
    ),
)

backend = await create_opensandbox_backend(
    "http://localhost:8080",
    sandbox_name="my-agent-workspace",
    backup=backup_config,
)
```

### Console 端操作

在沙箱详情页点击「**备份**」标签页：

- **文件树层级浏览**：按文件夹层级展示有备份的文件，自动展开所有文件夹，清晰呈现目录结构
- **备份详情**：点击预览按钮查看备份元数据、原始内容预览和 Git 风格变更对比（Diff）
- **变更对比**：展示每个备份与下一版本之间的 unified diff，新增行绿色高亮、删除行红色高亮
- **一键回滚**：将文件恢复到指定备份版本，系统会自动创建当前版本快照以便撤销
- **智能快照**：回滚时自动检测当前内容是否已存在备份，避免创建冗余的 `pre_restore` 快照
- **手动创建备份**：输入文件路径和描述，手动备份任意文件
- **删除备份**：单个删除或按文件批量删除
- **完整 ID 展示**：备份 ID 和内容哈希完整显示，不做截断

### 回滚安全机制

回滚操作采用 Git 风格的安全策略：

1. 读取目标备份内容
2. **自动读取当前文件，如果内容不同则创建 `pre_restore` 快照备份**
3. **优化：如果当前内容已存在备份记录（如撤销回滚），跳过快照创建，避免冗余**
4. 将备份内容写回文件
5. 前端提示“回滚前已自动创建备份”，用户可从快照再次回滚来撤销

### 备份触发器类型

| 触发器 | 标签颜色 | 说明 |
|--------|---------|------|
| `on_write` | 蓝色 | Agent 写入文件时自动触发 |
| `on_delete` | 橙色 | Agent 删除文件时自动触发 |
| `on_command` | 紫色 | Agent 执行匹配命令时自动触发 |
| `manual` | 灰色 | 用户在 Console 手动创建 |
| `pre_restore` | 琥珀色 | 回滚前自动创建的安全快照 |

## API 概览

| 端点 | 方法 | 说明 |
|------|------|------|
| `/healthz` | GET | 健康检查 |
| `/readyz` | GET | 就绪检查（数据库检测） |
| `/api/v1/connections` | GET/POST | 连接列表/创建 |
| `/api/v1/connections/{id}/test` | POST | 测试连接 |
| `/api/v1/sandboxes` | GET/POST | 沙箱列表/创建 |
| `/api/v1/connections/{id}/sandboxes` | POST | 通过连接创建沙箱 |
| `/api/v1/connections/{id}/sandboxes/{sid}/files` | GET | 文件列表 |
| `/api/v1/connections/{id}/sandboxes/{sid}/file` | GET/PUT/DELETE | 文件 CRUD |
| `/api/v1/connections/{id}/sandboxes/{sid}/commands` | POST | 执行命令 |
| `/api/v1/connections/{id}/sandboxes/{sid}/commands/{cid}/stream` | GET | SSE 流 |
| `/api/v1/sandboxes/{cid}/{sid}/history` | GET | 操作历史 |
| `/api/v1/connections/{id}/sandboxes/{sid}/terminals` | POST | 创建终端 |
| `/api/v1/connections/{cid}/sandboxes/{sid}/backups` | GET/POST/DELETE | 文件备份列表/创建/批量删除 |
| `/api/v1/connections/{cid}/sandboxes/{sid}/backups/files` | GET | 有备份的文件列表 |
| `/api/v1/connections/{cid}/sandboxes/{sid}/backups/{bid}` | GET/DELETE | 单个备份详情/删除 |
| `/api/v1/connections/{cid}/sandboxes/{sid}/backups/{bid}/restore` | POST | 回滚文件 |
| `/api/v1/connections/{cid}/sandboxes/{sid}/backups/{bid}/diff` | GET | 获取备份与下一版本的 Git 风格 diff |

## Deep Agents 集成

配合 `agent-sandbox-backends` SDK（需本地源码安装），可以一行代码将沙箱适配为 Deep Agents Backend。

> **前提：** SDK 已通过 `pip install -e "agents-backend[deepagents]"` 安装到当前 Python 环境。

```python
import asyncio
import os

from dotenv import load_dotenv
from deepagents import create_deep_agent
from langchain.chat_models import init_chat_model

from agent_sandbox_backends import (
    BackupConfig, BackupRule, BackupTrigger,
    CleanupPolicy, create_opensandbox_backend,
)
from agent_sandbox_backends.integrations.deepagents import as_deepagents_backend

load_dotenv(override=True)

model = init_chat_model(
    model="deepseek-v4-flash",
    api_key=os.getenv("API_KEY"),
    base_url=os.getenv("BASE_URL"),
)

async def create_agent():
    backend = await create_opensandbox_backend(
        "http://localhost:8080",           # OpenSandbox Service 地址
        sandbox_name="research-workspace",
        backup=BackupConfig(
            enabled=True,
            rules=(
                BackupRule(
                    name="python-files",
                    include=("**/*.py",),
                    triggers=(BackupTrigger.ON_WRITE, BackupTrigger.ON_DELETE),
                ),
            ),
        ),
    )
    deepagents_backend = as_deepagents_backend(backend)
    return create_deep_agent(model=model, backend=deepagents_backend)

agent = asyncio.run(create_agent())
```

使用 `langgraph dev` 启动时，将上述代码封装为 LangGraph 图即可：

```python
# agent.py
from langgraph.graph import StateGraph, MessagesState

# ... 上面的 agent 创建逻辑 ...

graph = StateGraph(MessagesState)
graph.add_node("agent", agent)
graph.set_entry_point("agent")
graph.set_finish_point("agent")
app = graph.compile()
```

```bash
langgraph dev  # 启动 LangGraph 开发服务器
```

> 完整的 Agent 项目示例和 `langgraph dev` 配置详见 [备份功能测试文档](docs/BACKUP_TESTING.md)。

## 项目结构

```
sandbox-console/
├── start.py                # 统一启动脚本
├── backend/                # FastAPI 后端
│   ├── hatch_build.py      # 构建钩子：编译前端打包进 wheel
│   ├── app/
│   │   ├── cli.py          # CLI 入口 (sandbox-console-server)
│   │   ├── main.py         # 应用工厂
│   │   ├── static/         # 打包的前端静态文件
│   │   ├── core/           # 配置、安全、错误处理
│   │   ├── db/             # 数据库引擎、会话、基类
│   │   ├── models/         # ORM 模型
│   │   ├── schemas/        # Pydantic 数据模型
│   │   ├── adapters/       # 沙箱适配器 (Fake, OpenSandbox)
│   │   ├── services/       # 业务逻辑层
│   │   ├── api/v1/         # REST 路由
│   │   ├── realtime/       # WebSocket 终端
│   │   └── observability/  # 指标、健康检查
│   └── tests/             # 集成测试
├── frontend/              # React + TypeScript 前端
│   └── src/
│       ├── pages/          # 页面组件
│       ├── features/       # 功能模块（文件、命令、历史、终端、备份）
│       ├── lib/            # API 客户端、工具函数
│       └── stores/         # Zustand 状态管理
├── docker/                # Dockerfile（多阶段构建）
├── docker-compose.yml
└── docs/                  # 文档
```

## 测试

```bash
cd backend
pip install -e ".[dev]"
pytest tests/ -v
```

## 相关文档

- [沙箱管理套件介绍](docs/OpenSandbox-沙箱管理套件介绍.md)
- [文件备份与回滚功能测试文档](docs/BACKUP_TESTING.md)
- [TestPyPI 发布指南](docs/LOCAL_TESTING.md)

## 许可证

Apache-2.0 — 详见 [LICENSE](LICENSE)。
