# Sandbox Explorer

A web console for observing and operating sandbox environments. Manage sandboxes, browse files, execute commands, and view operation history — all from a browser.

Built with FastAPI (backend) + React/TypeScript (frontend), packaged as a single Docker container or runnable locally with one command.

## Features

- **Sandbox Management** — Create, list, pause, resume, delete sandboxes
- **File Explorer** — Browse, read, edit (Monaco Editor), upload, download
- **Command Runner** — Execute commands with real-time SSE streaming output
- **Terminal** — Interactive shell via xterm.js + WebSocket
- **History Timeline** — Unified operation history synced from sandbox
- **Connection Management** — Register and test sandbox connections with encrypted credentials
- **Observability** — Health checks, Prometheus metrics, structured logging

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+

### Launch (One Command)

```bash
python start.py          # Production: build frontend + serve on http://localhost:8080
python start.py --dev    # Development: hot-reload frontend (:5173) + backend (:8080)
```

That's it. No environment variables required for local development — auth is disabled by default. Open `http://localhost:8080` (production) or `http://localhost:5173` (dev) in your browser.

### Docker

> **Note:** Docker build requires the [`agent-sandbox-backends`](https://github.com/anthropic/agents-backend) SDK source as a sibling directory.

```bash
# Build (from parent directory containing both repos)
docker build -f sandbox-console/docker/Dockerfile -t sandbox-explorer .

# Run
docker run -d -p 8080:8080 -v sandbox-explorer-data:/data sandbox-explorer
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
| Backend port | `--port` | `EXPLORER_PORT` | `8080` | All |
| Backend host | `--host` | `EXPLORER_HOST` | `0.0.0.0` | All |
| Frontend port | `--frontend-port` | `EXPLORER_FRONTEND_PORT` | `5173` | Dev only |

```bash
# Examples
python start.py --port 3000                         # Custom backend port
python start.py --dev --port 3000 --frontend-port 3001  # Custom dev ports
EXPLORER_PORT=3000 python start.py                  # Via environment variable

# .env file (project root, loaded automatically)
# EXPLORER_PORT=3000
# EXPLORER_HOST=0.0.0.0
```

For Docker, set `EXPLORER_PORT` and map the same port:

```bash
docker run -p 3000:3000 -e EXPLORER_PORT=3000 sandbox-explorer
```

## Configuration

All configuration via environment variables (prefix `EXPLORER_`). See [`.env.example`](.env.example) for details.

| Variable | Default | Description |
|---|---|---|
| `EXPLORER_ADMIN_TOKEN` | (empty) | Admin bearer token (empty = auth disabled) |
| `EXPLORER_MASTER_KEY` | all-zeros | Fernet encryption key (64-char hex) |
| `EXPLORER_DATABASE_URL` | `sqlite+aiosqlite:///./data/explorer.db` | Database URL |
| `EXPLORER_PORT` | `8080` | Backend port |
| `EXPLORER_HOST` | `0.0.0.0` | Backend bind address |
| `EXPLORER_FRONTEND_PORT` | `5173` | Frontend dev port (dev mode only) |
| `EXPLORER_PUBLIC_URL` | `http://localhost:8080` | External URL |
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
│   ├── app/
│   │   ├── main.py         # App factory
│   │   ├── core/           # Config, security, errors
│   │   ├── db/             # Engine, session, base
│   │   ├── models/         # ORM models
│   │   ├── schemas/        # Pydantic IO models
│   │   ├── adapters/       # Sandbox adapters (Fake, OpenSandbox)
│   │   ├── services/       # Business logic
│   │   ├── api/v1/         # REST routes
│   │   ├── realtime/       # WebSocket terminal
│   │   └── observability/  # Metrics, health
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
