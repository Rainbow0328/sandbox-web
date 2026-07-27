# Sandbox Console

A web console for observing and operating sandbox environments. Manage sandboxes, browse files, execute commands, and view operation history — all from a browser.

Built with FastAPI (backend) + React/TypeScript (frontend), packaged as a single Docker container, pip-installable, or runnable locally with one command.

## Features

- **Sandbox Management** — Create, list, pause, resume, delete sandboxes
- **File Explorer** — Browse, read, edit (Monaco Editor), upload, download
- **Command Runner** — Execute commands with real-time SSE streaming output
- **Terminal** — Interactive shell via xterm.js + WebSocket
- **History Timeline** — Unified operation history synced from sandbox
- **Connection Management** — Register and test sandbox connections with encrypted credentials
- **Observability** — Health checks, Prometheus metrics, structured logging

## Quick Start

### Option A: pip install (Recommended)

Install the package — the frontend is pre-built and bundled inside the wheel, so **no Node.js required**.

```bash
pip install sandbox-console
```

Start the server:

```bash
sandbox-console-server                      # Start on http://localhost:9090
sandbox-console-server --port 3000          # Custom port
sandbox-console-server --host 127.0.0.1     # Bind to localhost only
```

Open `http://localhost:9090` in your browser. No environment variables required for local use — auth is disabled by default.

> **Note:** The Console defaults to port **9090** to avoid conflicting with the OpenSandbox service which runs on port **8080**.

### Option B: Run from Source

Requires Python 3.11+ and Node.js 18+.

```bash
python start.py          # Production: build frontend + serve on http://localhost:9090
python start.py --dev    # Development: hot-reload frontend (:5173) + backend (:9090)
```

Or install in editable mode and use the CLI:

```bash
cd backend
pip install -e .
sandbox-console-server --dev    # Dev mode with hot-reload
```

### Docker

> **Note:** Docker build requires the [`agent-sandbox-backends`](https://github.com/anthropic/agents-backend) SDK source as a sibling directory.

```bash
# Build (from parent directory containing both repos)
docker build -f sandbox-console/docker/Dockerfile -t sandbox-console .

# Run
docker run -d -p 9090:9090 -v sandbox-console-data:/data sandbox-console
```

Or with Docker Compose:

```bash
cd sandbox-console
docker compose up -d
```

## Port Configuration

Ports can be configured via **CLI flags**, **environment variables**, or **`.env` file** (priority: CLI > env > `.env` > defaults).

| Parameter | CLI Flag | Env Variable | Default | Mode |
|---|---|---|---|---|
| Backend port | `--port` | `EXPLORER_PORT` | `9090` | All |
| Backend host | `--host` | `EXPLORER_HOST` | `0.0.0.0` | All |
| Frontend port | `--frontend-port` | `EXPLORER_FRONTEND_PORT` | `5173` | Dev only |

```bash
# Examples (pip install)
sandbox-console-server --port 3000                              # Custom port
sandbox-console-server --dev --port 3000 --frontend-port 3001   # Custom dev ports
EXPLORER_PORT=3000 sandbox-console-server                       # Via environment variable

# Examples (from source)
python start.py --port 3000                                  # Custom backend port
python start.py --dev --port 3000 --frontend-port 3001       # Custom dev ports
EXPLORER_PORT=3000 python start.py                           # Via environment variable

# .env file (project root or CWD, loaded automatically)
# EXPLORER_PORT=3000
# EXPLORER_HOST=0.0.0.0
```

For Docker, set `EXPLORER_PORT` and map the same port:

```bash
docker run -p 3000:3000 -e EXPLORER_PORT=3000 sandbox-console
```

## Configuration

All configuration via environment variables (prefix `EXPLORER_`). See [`.env.example`](.env.example) for details.

| Variable | Default | Description |
|---|---|---|
| `EXPLORER_ADMIN_TOKEN` | (empty) | Admin bearer token (empty = auth disabled) |
| `EXPLORER_MASTER_KEY` | all-zeros | Fernet encryption key (64-char hex) |
| `EXPLORER_DATABASE_URL` | `sqlite+aiosqlite:///./data/explorer.db` | Database URL |
| `EXPLORER_PORT` | `9090` | Backend port (OpenSandbox service uses 8080) |
| `EXPLORER_HOST` | `0.0.0.0` | Backend bind address |
| `EXPLORER_FRONTEND_PORT` | `5173` | Frontend dev port (dev mode only) |
| `EXPLORER_PUBLIC_URL` | `http://localhost:9090` | External URL |
| `EXPLORER_CORS_ORIGINS` | (empty) | Comma-separated CORS origins |

## API Overview

| Endpoint | Method | Description |
|---|---|---|
| `/healthz` | GET | Health check |
| `/readyz` | GET | Readiness (DB check) |
| `/api/v1/connections` | GET/POST | List/create connections |
| `/api/v1/connections/{id}/test` | POST | Test connection |
| `/api/v1/sandboxes` | GET/POST | List / direct create sandboxes |
| `/api/v1/connections/{id}/sandboxes` | POST | Create sandbox via connection |
| `/api/v1/connections/{id}/sandboxes/{sid}/files` | GET | List files |
| `/api/v1/connections/{id}/sandboxes/{sid}/file` | GET/PUT/DELETE | File CRUD |
| `/api/v1/connections/{id}/sandboxes/{sid}/commands` | POST | Execute command |
| `/api/v1/connections/{id}/sandboxes/{sid}/commands/{cid}/stream` | GET | SSE stream |
| `/api/v1/sandboxes/{cid}/{sid}/history` | GET | Operation history |
| `/api/v1/connections/{id}/sandboxes/{sid}/terminals` | POST | Create terminal |

## Project Structure

```
sandbox-console/
├── start.py                # Unified startup script
├── backend/                # FastAPI backend
│   ├── hatch_build.py     # Build hook: compiles frontend into wheel
│   ├── app/
│   │   ├── cli.py         # CLI entry point (sandbox-console-server)
│   │   ├── main.py        # App factory
│   │   ├── static/        # Bundled frontend (built by hatch_build.py)
│   │   ├── core/          # Config, security, errors
│   │   ├── db/            # Engine, session, base
│   │   ├── models/        # ORM models
│   │   ├── schemas/       # Pydantic IO models
│   │   ├── adapters/      # Sandbox adapters (Fake, OpenSandbox)
│   │   ├── services/      # Business logic
│   │   ├── api/v1/        # REST routes
│   │   ├── realtime/      # WebSocket terminal
│   │   └── observability/ # Metrics, health
│   └── tests/             # Integration tests
├── frontend/              # React + TypeScript frontend
│   └── src/
│       ├── pages/          # Connections, Sandboxes, SandboxDetail
│       ├── features/       # Files, Commands, History, Terminal
│       ├── lib/            # API client, utils
│       └── stores/         # Zustand stores
├── docker/                # Dockerfile (multi-stage)
└── docker-compose.yml
```

## Testing

```bash
cd backend
pip install -e ".[dev]"
pytest tests/ -v
```

## License

Apache-2.0 — See [LICENSE](LICENSE).
