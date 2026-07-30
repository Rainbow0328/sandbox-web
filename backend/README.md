# Sandbox Console — Backend

FastAPI 后端，提供沙箱管理、文件操作、命令执行、历史时间线和文件备份等 REST API。

## 安装

```bash
pip install sandbox-console
```

或从源码安装：

```bash
cd backend
pip install -e .
```

## 启动

```bash
sandbox-console-server                      # 默认 http://localhost:9090
sandbox-console-server --port 3000          # 自定义端口
sandbox-console-server --host 127.0.0.1     # 仅本机访问
sandbox-console-server --dev                # 开发模式（前端热更新）
```

## 功能模块

| 模块 | 说明 |
|------|------|
| 沙箱管理 | 创建、列表、暂停、恢复、删除沙箱 |
| 文件浏览器 | 浏览、读取、编辑、上传、下载文件 |
| 命令执行器 | 执行命令，SSE 实时流式输出 |
| 终端 | 基于 WebSocket 的交互式 Shell |
| 历史时间线 | Agent 和 Console 操作的统一历史记录 |
| **文件备份与回滚** | 类 Git 的文件级备份，支持自动/手动备份、变更对比、一键回滚 |
| 连接管理 | 注册多个 OpenSandbox 实例，加密存储凭证 |

## 文件备份与回滚

### 架构

备份数据存储在沙箱内部的 `/.agent-history/history.sqlite3` 数据库的 `file_backups` 表中。
SDK 端的 `BackupManager` 负责自动触发备份，Console 后端通过 `SandboxHistoryStore` 读取同一数据库，
提供备份列表、详情、变更对比、回滚和删除等 API。

### 后端服务层

备份相关的业务逻辑位于 `app/services/backup_service.py`，包含以下核心函数：

| 函数 | 说明 |
|------|------|
| `list_backups` | 列出沙箱的文件备份，支持按文件路径过滤和分页 |
| `list_backup_files` | 列出有备份的文件路径及备份数量 |
| `get_backup` | 获取单个备份详情，可选包含文件内容 |
| `create_backup` | 从沙箱读取文件内容，创建手动备份 |
| `restore_backup` | 回滚文件到指定备份版本，自动创建 `pre_restore` 快照 |
| `get_backup_diff` | 计算备份与下一版本之间的 Git 风格 unified diff |
| `delete_backup` | 删除单个备份 |
| `delete_backups_by_path` | 按文件路径批量删除备份 |

### 回滚安全机制

`restore_backup` 函数实现了智能快照策略：

1. 读取目标备份内容
2. 读取当前文件内容，计算 hash
3. 如果当前内容与目标备份内容相同 → 跳过快照
4. 如果当前内容已存在备份记录（如撤销回滚场景）→ 跳过快照
5. 否则创建 `pre_restore` 快照备份，写入数据库
6. 将目标备份内容写回沙箱文件

### 变更对比（Diff）

`get_backup_diff` 函数计算备份与下一版本之间的 unified diff：

- 如果存在下一个备份（按 `created_at` 排序），对比两个备份的内容
- 如果是最新备份，对比备份内容与当前文件内容
- 支持 UTF-8 文本文件的 diff，二进制文件返回 `is_binary=True`
- 使用 Python `difflib.unified_diff` 生成标准 unified diff 格式

### API 路由

路由定义在 `app/api/v1/backups.py`：

| 端点 | 方法 | 说明 |
|------|------|------|
| `/connections/{cid}/sandboxes/{sid}/backups` | GET | 备份列表（支持 `file_path` 过滤、`limit`/`offset` 分页） |
| `/connections/{cid}/sandboxes/{sid}/backups/files` | GET | 有备份的文件列表 |
| `/connections/{cid}/sandboxes/{sid}/backups/{bid}` | GET | 单个备份详情（`include_content=true` 包含内容） |
| `/connections/{cid}/sandboxes/{sid}/backups/{bid}` | DELETE | 删除单个备份 |
| `/connections/{cid}/sandboxes/{sid}/backups` | POST | 创建手动备份 |
| `/connections/{cid}/sandboxes/{sid}/backups` | DELETE | 按文件路径批量删除（`file_path` 参数） |
| `/connections/{cid}/sandboxes/{sid}/backups/{bid}/restore` | POST | 回滚文件 |
| `/connections/{cid}/sandboxes/{sid}/backups/{bid}/diff` | GET | 获取 Git 风格变更对比 |

### Pydantic Schema

数据模型定义在 `app/schemas/backup.py`：

- `BackupItem` — 备份元数据（不含内容）
- `BackupDetail` — 备份详情（可选包含 `content_base64`）
- `BackupListResponse` — 分页备份列表
- `BackupFileListResponse` — 有备份的文件列表
- `BackupCreateRequest` / `BackupCreateResponse` — 创建备份请求/响应
- `BackupRestoreResponse` — 回滚响应（含 `pre_restore_backup_id`）
- `BackupDiffResponse` — 变更对比响应（含 `diff`、`has_diff`、`is_binary`、`is_latest`）
- `BackupDeleteResponse` / `BackupDeleteByPathResponse` — 删除响应

## 配置

所有配置使用 `EXPLORER_` 前缀的环境变量或 `.env` 文件。

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `EXPLORER_PORT` | `9090` | 服务端口 |
| `EXPLORER_HOST` | `0.0.0.0` | 绑定地址 |
| `EXPLORER_ADMIN_TOKEN` | (空) | 管理员 Bearer Token，为空则关闭认证 |
| `EXPLORER_MASTER_KEY` | 全零 | Fernet 加密密钥（64 位十六进制），用于加密连接凭证 |
| `EXPLORER_DATABASE_URL` | `sqlite+aiosqlite:///./data/explorer.db` | 数据库连接 |

## 测试

```bash
cd backend
pip install -e ".[dev]"
pytest tests/ -v
```

## 许可证

Apache-2.0
