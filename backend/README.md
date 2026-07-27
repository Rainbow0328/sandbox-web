# Sandbox Console

A web console for observing and operating sandbox environments. Manage sandboxes, browse files, execute commands, and view operation history — all from a browser.

## Install

```bash
pip install sandbox-console
```

## Quick Start

```bash
sandbox-console-server                      # Start on http://localhost:9090
sandbox-console-server --port 3000          # Custom port
sandbox-console-server --host 127.0.0.1     # Localhost only
```

Open `http://localhost:9090` in your browser.

## Features

- **Sandbox Management** — Create, list, pause, resume, delete sandboxes
- **File Explorer** — Browse, read, edit (Monaco Editor), upload, download
- **Command Runner** — Execute commands with real-time SSE streaming output
- **Terminal** — Interactive shell via xterm.js + WebSocket
- **History Timeline** — Unified operation history synced from sandbox
- **Connection Management** — Register and test sandbox connections with encrypted credentials

## Configuration

All configuration via environment variables (prefix `EXPLORER_`) or `.env` file.

| Variable | Default | Description |
|---|---|---|
| `EXPLORER_PORT` | `9090` | Server port |
| `EXPLORER_HOST` | `0.0.0.0` | Bind address |
| `EXPLORER_ADMIN_TOKEN` | (empty) | Admin bearer token (empty = auth disabled) |
| `EXPLORER_MASTER_KEY` | all-zeros | Fernet encryption key (64-char hex) |
| `EXPLORER_DATABASE_URL` | `sqlite+aiosqlite:///./data/explorer.db` | Database URL |

## License

Apache-2.0
