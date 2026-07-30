# 文件备份与回滚功能测试文档

本文档详细说明 OpenSandbox 沙箱管理套件中 **类 Git 文件备份与回滚** 功能的配置方法、测试流程和验证步骤。

> **适用场景：** 使用 `deepagents` 框架 + `langgraph dev` 启动的 AI Agent 应用，通过 `agent-sandbox-backends` SDK 创建沙箱并在 `sandbox-console` Web 控制台管理备份。

---

## 目录

1. [环境准备](#1-环境准备)
2. [SDK 端备份配置](#2-sdk-端备份配置)
3. [启动 Deep Agents + LangGraph](#3-启动-deep-agents--langgraph)
4. [Console 端验证流程](#4-console-端验证流程)
5. [备份触发测试](#5-备份触发测试)
6. [回滚功能测试](#6-回滚功能测试)
7. [备份数量限制测试](#7-备份数量限制测试)
8. [API 接口测试](#8-api-接口测试)
9. [常见问题排查](#9-常见问题排查)

---

## 1. 环境准备

### 1.1 组件版本要求

| 组件 | 版本 | 说明 |
|------|------|------|
| OpenSandbox Service | 最新版 | 沙箱运行时，默认端口 8080 |
| agent-sandbox-backends | >= 0.1.0 | SDK，提供备份配置和 BackupManager |
| sandbox-console | >= 0.2.0 | Web 控制台，端口 9090 |
| deepagents | 最新版 | AI Agent 框架 |
| langgraph | 最新版 | Agent 编排框架，`langgraph dev` 启动 |
| Python | >= 3.11 | 运行环境 |

### 1.2 目录结构前提

两个仓库需要平级放置：

```
sandbox-backend/
├── agents-backend/        ← SDK 源码（本地安装）
│   ├── pyproject.toml
│   └── src/agent_sandbox_backends/
└── sandbox-console/       ← Web 控制台
```

### 1.3 安装组件

SDK `agent-sandbox-backends` 尚未发布到 PyPI，需要从本地源码安装：

```bash
# 1. 安装 SDK（含 deepagents 适配器，从本地源码）
cd agents-backend
pip install -e ".[deepagents]"

# 2. 安装 Web 控制台（已发布到 PyPI，可直接安装）
pip install sandbox-console

# 3. 安装 deepagents 和 langgraph
pip install deepagents langgraph langchain
```

> **验证 SDK 安装：**
> ```bash
> python -c "from agent_sandbox_backends import BackupConfig, BackupRule, BackupTrigger; print('SDK OK')"
> ```
> ```bash
> python -c "from agent_sandbox_backends.integrations.deepagents import as_deepagents_backend; print('deepagents adapter OK')"
> ```

### 1.4 启动各服务

```bash
# 终端 1：启动 OpenSandbox Service（默认 8080）
# 参考 OpenSandbox 官方文档

# 终端 2：启动 sandbox-console
sandbox-console-server

# 终端 3：启动 Agent 应用（见下文）
```

打开 `http://localhost:9090`，注册一个连接指向 OpenSandbox Service（`http://localhost:8080`）。

---

## 2. SDK 端备份配置

### 2.1 配置项说明

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `enabled` | bool | `False` | 是否启用备份功能 |
| `rules` | tuple[BackupRule] | 一个默认规则 | 备份规则列表，首个匹配生效 |
| `max_backups_per_file` | int | `15` | 单个文件最大备份数，超出自动删除最旧的 |
| `max_total_backup_bytes` | int | `100MB` | 所有备份总大小上限 |
| `auto_cleanup` | bool | `True` | 自动清理过期备份 |
| `compression` | str | `"identity"` | 压缩方式：`identity`/`gzip`/`zlib` |
| `compression_min_bytes` | int | `4096` | 超过此大小才压缩 |
| `auto_description_template` | str | `"{trigger} {path}"` | 自动描述模板 |

### 2.2 BackupRule 字段

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `name` | str | 必填 | 规则名称，用于展示 |
| `include` | tuple[str] | `("**/*",)` | 包含模式（gitwildmatch 语法） |
| `exclude` | tuple[str] | `()` | 排除模式 |
| `triggers` | tuple[BackupTrigger] | `(ON_WRITE, ON_DELETE)` | 触发器类型 |
| `command_patterns` | tuple[str] | `()` | ON_COMMAND 触发时的命令正则 |
| `max_file_size` | int | `10MB` | 超过此大小的文件跳过备份，0=不限 |

### 2.3 完整配置示例

```python
from agent_sandbox_backends import (
    BackupConfig,
    BackupRule,
    BackupTrigger,
    create_opensandbox_backend,
)

backup_config = BackupConfig(
    enabled=True,
    max_backups_per_file=15,
    auto_description_template="{trigger} {path} by {actor_id}",
    rules=(
        # 规则1：所有 Python 文件在写入/删除时自动备份
        BackupRule(
            name="python-files",
            include=("**/*.py",),
            exclude=("**/__pycache__/**", "**/.venv/**"),
            triggers=(BackupTrigger.ON_WRITE, BackupTrigger.ON_DELETE),
            max_file_size=5 * 1024 * 1024,  # 5MB
        ),
        # 规则2：配置文件（JSON/YAML/TOML）在写入时备份
        BackupRule(
            name="config-files",
            include=("**/*.json", "**/*.yaml", "**/*.yml", "**/*.toml"),
            triggers=(BackupTrigger.ON_WRITE,),
        ),
        # 规则3：执行 pip install 前备份 src/ 目录下所有文件
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
    sandbox_name="backup-test-workspace",
    backup=backup_config,
)
```

---

## 3. 启动 Deep Agents + LangGraph

### 3.1 项目结构

```
my-agent-project/
├── agent.py          # Agent 定义
├── langgraph.json    # LangGraph 配置
├── .env              # 环境变量
└── requirements.txt
```

### 3.2 创建 Agent 项目

在任意目录创建 Agent 项目（需确保当前 Python 环境已安装本地 SDK）：

```
my-agent-project/
├── agent.py          # Agent 定义
├── langgraph.json    # LangGraph 配置
├── .env              # 环境变量
└── requirements.txt
```

> **注意：** Agent 项目不需要在 `agents-backend` 或 `sandbox-console` 目录下，但必须确保运行 `langgraph dev` 的 Python 环境已经通过 `pip install -e "agents-backend[deepagents]"` 安装了本地 SDK。

### 3.3 agent.py

```python
"""Deep Agents + OpenSandbox + 备份功能示例"""
from __future__ import annotations

import asyncio
import os

from dotenv import load_dotenv
from deepagents import create_deep_agent
from langchain.chat_models import init_chat_model
from langgraph.graph import StateGraph, MessagesState
from langgraph.checkpoint.memory import InMemorySaver

from agent_sandbox_backends import (
    BackupConfig,
    BackupRule,
    BackupTrigger,
    create_opensandbox_backend,
)
from agent_sandbox_backends.integrations.deepagents import as_deepagents_backend

load_dotenv(override=True)

# 模型配置
model = init_chat_model(
    model=os.getenv("MODEL_NAME", "deepseek-v4-flash"),
    api_key=os.getenv("API_KEY"),
    base_url=os.getenv("BASE_URL"),
)

# 全局 backend 引用，用于 close
_backend = None


async def _get_backend():
    global _backend
    if _backend is None:
        _backend = await create_opensandbox_backend(
            os.getenv("OPENSANDBOX_URL", "http://localhost:8080"),
            sandbox_name=os.getenv("SANDBOX_NAME", "deepagents-workspace"),
            backup=BackupConfig(
                enabled=True,
                max_backups_per_file=15,
                rules=(
                    BackupRule(
                        name="python-files",
                        include=("**/*.py",),
                        triggers=(
                            BackupTrigger.ON_WRITE,
                            BackupTrigger.ON_DELETE,
                        ),
                    ),
                    BackupRule(
                        name="before-pip",
                        include=("**/*.py", "**/*.txt"),
                        triggers=(BackupTrigger.ON_COMMAND,),
                        command_patterns=(r"pip\s+install",),
                    ),
                ),
            ),
        )
    return _backend


async def _get_agent():
    backend = await _get_backend()
    deepagents_backend = as_deepagents_backend(backend)
    return create_deep_agent(model=model, backend=deepagents_backend)


def build_graph():
    """构建 LangGraph 图，供 langgraph dev 使用"""
    agent = asyncio.run(_get_agent())

    graph = StateGraph(MessagesState)
    graph.add_node("agent", agent)
    graph.set_entry_point("agent")
    graph.set_finish_point("agent")
    return graph.compile(checkpointer=InMemorySaver())


# langgraph dev 入口
app = build_graph()
```

### 3.4 langgraph.json

```json
{
  "graphs": {
    "agent": "./agent.py:app"
  },
  "env": ".env"
}
```

### 3.5 .env

```ini
# 模型配置
API_KEY=your-api-key
BASE_URL=https://api.example.com/v1
MODEL_NAME=deepseek-v4-flash

# OpenSandbox 配置
OPENSANDBOX_URL=http://localhost:8080
SANDBOX_NAME=deepagents-backup-test
```

### 3.6 启动

```bash
# 在项目根目录执行
langgraph dev
```

启动后 LangGraph Studio 默认在 `http://localhost:2024` 可访问。Agent 执行的文件写入和删除操作会自动触发备份。

---

## 4. Console 端验证流程

### 4.1 确认沙箱已创建

1. 打开 `http://localhost:9090`
2. 进入 **沙箱** 页面
3. 确认 Agent 创建的沙箱出现在列表中（名称为 `deepagents-backup-test`）

### 4.2 进入备份标签页

1. 点击沙箱右侧的「打开」按钮
2. 在详情页顶部点击「**备份**」标签
3. 初始状态下显示"暂无文件备份"

### 4.3 备份标签页功能区域

| 区域 | 说明 |
|------|------|
| 顶部工具栏 | 刷新按钮、创建备份按钮 |
| 文件列表 | 按文件路径分组，显示每个文件的备份数和最新备份时间 |
| 备份详情面板 | 点击预览按钮后从右侧滑出，显示备份元数据和内容预览 |
| 创建备份弹窗 | 手动输入文件路径和描述创建备份 |

---

## 5. 备份触发测试

### 测试 5.1：ON_WRITE 自动备份

**目标：** 验证 Agent 写入 .py 文件时自动创建备份。

**步骤：**

1. 在 LangGraph Studio 中向 Agent 发送指令：
   ```
   请在 /workspace 目录下创建一个 main.py 文件，写入 print("hello world")
   ```

2. Agent 执行 `write_file` 写入文件后，返回 Console 备份标签页

3. 点击「刷新」按钮

**预期结果：**

- 备份列表出现 `/workspace/main.py` 条目
- 展开后显示一条备份记录，触发类型标签为蓝色「写入」
- 描述字段显示自动生成的描述（如 `on_write /workspace/main.py by deepagents-backup-test`）
- 时间为刚刚操作的时间

> **注意：** 第一次写入新文件时不会创建备份（因为文件之前不存在，没有内容可备份）。备份是在**写入前**读取当前内容创建的，所以需要文件已存在且被修改时才会触发。验证方式：先让 Agent 创建文件，再让 Agent 修改文件内容，第二次修改前会自动备份原始内容。

**修正验证步骤：**

1. 让 Agent 创建 `/workspace/main.py`（首次创建，无备份）
2. 让 Agent 修改 `/workspace/main.py` 的内容（写入前自动备份原始内容）
3. 刷新 Console 备份列表 → 应出现一条 `on_write` 备份

### 测试 5.2：ON_DELETE 自动备份

**目标：** 验证 Agent 删除 .py 文件时自动创建备份。

**步骤：**

1. 确认 `/workspace/main.py` 存在
2. 向 Agent 发送指令：
   ```
   请删除 /workspace/main.py 文件
   ```
3. 返回 Console 刷新备份列表

**预期结果：**

- 备份列表出现一条新的 `on_delete` 备份（橙色「删除」标签）
- 备份内容为删除前的文件内容

### 测试 5.3：ON_COMMAND 自动备份

**目标：** 验证 Agent 执行 `pip install` 前自动备份匹配文件。

**步骤：**

1. 确保沙箱中有 `.py` 和 `.txt` 文件存在
2. 向 Agent 发送指令：
   ```
   请执行 pip install requests
   ```
3. 返回 Console 刷新备份列表

**预期结果：**

- 所有匹配 `**/*.py` 和 `**/*.txt` 的文件各出现一条 `on_command` 备份（紫色「命令」标签）
- 备份描述中包含触发的命令信息

### 测试 5.4：手动创建备份

**目标：** 验证 Console 手动创建备份功能。

**步骤：**

1. 在 Console 备份标签页点击「创建备份」
2. 在弹窗中输入：
   - 文件路径：`/workspace/main.py`（需确保文件存在）
   - 描述：`手动备份测试`
3. 点击「创建」

**预期结果：**

- 页面顶部显示绿色 Toast 提示"备份创建成功"
- 备份列表出现一条新的 `manual` 备份（灰色「手动」标签）
- 描述显示"手动备份测试"

---

## 6. 回滚功能测试

### 测试 6.1：基本回滚

**目标：** 验证回滚功能能正确恢复文件内容。

**前提：** `/workspace/main.py` 存在且有至少 2 个备份版本。

**步骤：**

1. 记录当前文件内容（通过文件标签页查看）
2. 在备份标签页展开 `/workspace/main.py`
3. 找到较早的备份版本，点击回滚按钮（蓝色旋转箭头图标）
4. 确认弹框提示"当前文件内容将被覆盖。系统会自动备份当前版本，以便撤销。"
5. 点击确认

**预期结果：**

- 页面顶部显示绿色 Toast："文件已回滚到选定备份版本，回滚前已自动创建备份 (xxxxxxxx…)"
- 备份列表新增一条琥珀色「回滚前」标签的备份（`pre_restore` 类型）
- 切换到文件标签页，确认文件内容已恢复为备份版本的内容

### 测试 6.2：撤销回滚

**目标：** 验证通过 `pre_restore` 快照可以撤销回滚操作。

**步骤：**

1. 在测试 6.1 回滚后，找到那条琥珀色「回滚前」备份
2. 点击该备份的回滚按钮
3. 确认回滚

**预期结果：**

- 文件内容恢复为回滚前的版本
- 又新增一条 `pre_restore` 备份（因为当前内容又和目标备份不同了）

### 测试 6.3：从详情面板回滚

**目标：** 验证备份详情面板中的回滚按钮。

**步骤：**

1. 点击任意备份的预览按钮（文件图标）
2. 在右侧滑出的详情面板中查看备份信息
3. 点击面板中的「回滚到此版本」按钮
4. 确认回滚

**预期结果：**

- 与测试 6.1 结果一致
- 详情面板自动关闭

### 测试 6.4：回滚相同内容（不创建快照）

**目标：** 验证当前文件内容与备份内容相同时不创建 pre_restore 快照。

**步骤：**

1. 先将文件回滚到某个版本
2. 再次对同一个备份执行回滚

**预期结果：**

- 回滚成功
- 但不新增 `pre_restore` 备份（因为当前内容与备份内容相同）
- Toast 提示"文件已回滚到选定备份版本"（无"回滚前已自动创建备份"字样）

---

## 7. 备份数量限制测试

### 测试 7.1：max_backups_per_file 自动清理

**目标：** 验证超过最大备份数后自动删除最旧备份。

**配置：** `max_backups_per_file=3`（方便测试）

**步骤：**

1. 使用以下配置创建沙箱：
   ```python
   backup=BackupConfig(
       enabled=True,
       max_backups_per_file=3,
       rules=(BackupRule(name="all", include=("**/*",), triggers=(BackupTrigger.ON_WRITE,)),),
   )
   ```

2. 让 Agent 反复修改同一个文件（如 `/workspace/counter.py`）至少 5 次
   - 每次 `write_file` 前会自动备份当前版本

3. 在 Console 查看该文件的备份数

**预期结果：**

- 该文件最多保留 3 个备份
- 最旧的备份被自动删除
- 保留的是最新的 3 个

### 测试 7.2：批量删除文件的所有备份

**目标：** 验证按文件路径批量删除备份。

**步骤：**

1. 在备份列表中找到目标文件
2. 点击文件行右侧的删除按钮（垃圾桶图标）
3. 确认"确定删除 /workspace/counter.py 的所有备份？"

**预期结果：**

- 该文件从备份文件列表中消失
- 该文件的所有备份记录被删除
- Toast 提示"已删除该文件的所有备份"

### 测试 7.3：删除单个备份

**目标：** 验证删除单个备份记录。

**步骤：**

1. 展开某个文件备份列表
2. 点击某条备份的删除按钮
3. 确认"确定删除此备份？"

**预期结果：**

- 该备份记录从列表中消失
- 其他备份不受影响
- Toast 提示"备份已删除"

---

## 8. API 接口测试

以下测试使用 `curl` 直接调用 Console 的 REST API。假设连接 ID 为 `conn-1`，沙箱 ID 为 `sbx-1`。

### 8.1 列出备份文件

```bash
curl http://localhost:9090/api/v1/connections/conn-1/sandboxes/sbx-1/backups/files
```

**响应示例：**

```json
{
  "files": [
    {
      "file_path": "/workspace/main.py",
      "backup_count": 3,
      "latest_backup_at": "2025-07-30T10:00:00Z"
    }
  ],
  "total": 1
}
```

### 8.2 列出备份记录

```bash
curl "http://localhost:9090/api/v1/connections/conn-1/sandboxes/sbx-1/backups?limit=100"
```

**响应示例：**

```json
{
  "backups": [
    {
      "backup_id": "0197a3b0-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
      "file_path": "/workspace/main.py",
      "content_hash": "a1b2c3d4...",
      "content_size": 42,
      "encoding": "identity",
      "original_size": 42,
      "description": "on_write /workspace/main.py by deepagents-workspace",
      "trigger_type": "on_write",
      "rule_name": "python-files",
      "actor_type": "agent",
      "actor_id": "deepagents-workspace",
      "command": null,
      "created_at": "2025-07-30T10:00:00Z"
    }
  ],
  "total": 1,
  "limit": 100,
  "offset": 0
}
```

### 8.3 按文件路径过滤备份

```bash
curl "http://localhost:9090/api/v1/connections/conn-1/sandboxes/sbx-1/backups?file_path=/workspace/main.py"
```

### 8.4 获取备份详情（含内容）

```bash
curl "http://localhost:9090/api/v1/connections/conn-1/sandboxes/sbx-1/backups/0197a3b0-xxxx?include_content=true"
```

**响应示例：**

```json
{
  "backup_id": "0197a3b0-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "file_path": "/workspace/main.py",
  "content_hash": "a1b2c3d4...",
  "content_size": 42,
  "encoding": "identity",
  "original_size": 42,
  "description": "on_write /workspace/main.py",
  "trigger_type": "on_write",
  "rule_name": "python-files",
  "actor_type": "agent",
  "actor_id": "deepagents-workspace",
  "command": null,
  "created_at": "2025-07-30T10:00:00Z",
  "content_base64": "cHJpbnQoImhlbGxvIHdvcmxkIikK"
}
```

### 8.5 手动创建备份

```bash
curl -X POST http://localhost:9090/api/v1/connections/conn-1/sandboxes/sbx-1/backups \
  -H "Content-Type: application/json" \
  -d '{"file_path": "/workspace/main.py", "description": "API 手动创建备份"}'
```

### 8.6 回滚文件

```bash
curl -X POST http://localhost:9090/api/v1/connections/conn-1/sandboxes/sbx-1/backups/0197a3b0-xxxx/restore
```

**响应示例：**

```json
{
  "backup_id": "0197a3b0-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "file_path": "/workspace/main.py",
  "content_hash": "a1b2c3d4...",
  "content_size": 42,
  "restored": true,
  "pre_restore_backup_id": "0197a3c0-yyyy-yyyy-yyyy-yyyyyyyyyyyy",
  "message": "文件已回滚到选定备份版本，回滚前已自动创建备份 (0197a3c0…)"
}
```

### 8.7 删除单个备份

```bash
curl -X DELETE http://localhost:9090/api/v1/connections/conn-1/sandboxes/sbx-1/backups/0197a3b0-xxxx
```

### 8.8 按文件路径批量删除

```bash
curl -X DELETE "http://localhost:9090/api/v1/connections/conn-1/sandboxes/sbx-1/backups?file_path=/workspace/main.py"
```

---

## 9. 常见问题排查

### Q: 备份列表为空，Agent 写入文件后没有备份

**原因 1：** 备份功能未启用。检查 `BackupConfig(enabled=True)`。

**原因 2：** 首次创建文件不会产生备份。备份在写入前读取当前内容，新文件没有"之前的内容"可备份。修改已存在的文件时才会触发。

**原因 3：** 文件路径不匹配规则的 `include` 模式。检查 gitwildmatch 模式是否正确。

**原因 4：** Console 查看的是旧缓存。点击刷新按钮或等待 15 秒自动刷新。

### Q: 回滚后文件内容没变

**排查：**

1. 检查 Console Toast 是否显示"文件已回滚到选定备份版本"
2. 切换到「文件」标签页重新查看文件内容
3. 如果文件内容确实没变，检查后端日志是否有 `write_file` 错误

### Q: on_command 触发的备份没有出现

**原因：** 命令正则不匹配。`command_patterns` 使用 Python `re.search`，确认正则能匹配 Agent 执行的实际命令字符串。例如 `r"pip\s+install"` 能匹配 `pip install requests` 但不能匹配 `pip3 install`（需要 `r"pip3?\s+install"`）。

### Q: pre_restore 快照没有创建

**原因：** 如果当前文件内容与目标备份内容完全相同（hash 一致），系统会跳过快照创建。这是正常行为。另外，如果文件不存在（如被删除后回滚），也会跳过。

### Q: 备份数据存储在哪里

备份数据存储在沙箱内部的 `/.agent-history/history.sqlite3` 数据库的 `file_backups` 表中。SDK 和 Console 通过同一个沙箱共享此数据库。当沙箱被删除时，备份数据也会一起删除。

### Q: 如何查看备份数据库

可以通过沙箱的命令标签页执行：

```bash
python3 -c "
import sqlite3, json
conn = sqlite3.connect('/.agent-history/history.sqlite3')
conn.row_factory = sqlite3.Row
rows = conn.execute('SELECT backup_id, file_path, trigger_type, description, created_at FROM file_backups ORDER BY created_at DESC LIMIT 20').fetchall()
for r in rows:
    print(json.dumps(dict(r), ensure_ascii=False))
conn.close()
"
```

### Q: ON_COMMAND 备份扫描慢

`ON_COMMAND` 触发器会在命令执行前扫描整个沙箱文件系统查找匹配文件。对于文件数量多的沙箱，这会显著增加命令执行延迟。优化建议：

- 收窄 `include` 模式（如 `"src/**/*.py"` 而非 `"**/*.py"`）
- 增大 `max_file_size` 限制跳过大文件
- 如果不需要 ON_COMMAND 触发，移除该触发器
