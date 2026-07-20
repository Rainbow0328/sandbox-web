# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
