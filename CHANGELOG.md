# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.1] - 2025-07-30

### Added
- 备份列表改为文件树层级展示，按文件夹嵌套渲染，自动展开所有文件夹
- 备份变更对比（Diff）功能：展示备份与下一版本之间的 Git 风格 unified diff
- 新增 `/backups/{bid}/diff` API 端点，返回备份变更对比数据
- 备份 ID 和内容哈希完整显示，不再截断
- 全局字体增大：页面标题、元数据、Diff 查看器、备份内容预览等统一提升字号

### Changed
- 回滚安全机制优化：当前内容已存在备份记录时跳过 `pre_restore` 快照创建，避免冗余
- 前端文件树组件使用 `useEffect` 替代 render 中的副作用调用（React 反模式修复）
- 备份列表项显示完整 `backup_id`，不再使用 `substring(0, 8)` 截断

### Fixed
- 修复前端 base64 内容解码乱码问题：使用 `TextDecoder('utf-8')` 替代 `atob` 直接解码
- 修复 diff 计算失败时前端错误显示"无变更"的问题，增加独立的错误提示
- 修复后端 `get_backup_diff` 缺少 `hashlib` 导入导致计算失败的问题
- 修复 API 路径不匹配：后端备份路由统一使用 `/connections/` 前缀

### Documentation
- 主 README.md 补充 diff API 端点、文件树展示描述、智能快照优化说明
- backend/README.md 重写，新增备份服务层、API 路由、Pydantic Schema 完整说明
- SDK README.md 新增「文件备份与回滚」章节，包含 BackupConfig/BackupRule/BackupTrigger 完整配置文档
- 更新 BACKUP_TESTING.md 测试文档

## [0.2.0] - 2025-07-25

### Added
- 文件备份与回滚功能（类 Git 文件级备份系统）
- 备份 API：列表、详情、创建、回滚、删除
- 前端备份标签页：按文件分组浏览、备份详情面板、手动创建备份
- SDK `BackupConfig`/`BackupRule`/`BackupTrigger` 配置接口
- `pre_restore` 回滚安全快照机制

## [0.1.0] - 2025-01-01

### Added
- Sandbox lifecycle management (create, list, pause, resume, delete)
- File explorer with Monaco editor, upload/download
- Command execution with SSE streaming
- Interactive terminal via WebSocket
- Unified operation history synced from sandbox
- Connection management with encrypted credentials
- Single-command startup (`start.py`) for local dev and production
- Docker multi-stage build with frontend bundling
- Port configuration via CLI flags, environment variables, and `.env` file
