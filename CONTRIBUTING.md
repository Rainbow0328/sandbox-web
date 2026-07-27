# Contributing to Sandbox Console

## Development Setup

### Prerequisites

- Python 3.11+
- Node.js 18+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

### Quick Start

```bash
git clone https://github.com/Rainbow0328/sandbox-web.git
cd sandbox-web
python start.py --dev
```

### Manual Setup

```bash
# Backend
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .\.venv\Scripts\activate
pip install -e ".[dev]"

# Frontend
cd ../frontend
npm install --legacy-peer-deps
```

## Code Style

### Backend (Python)

- Linter: [ruff](https://docs.astral.sh/ruff/) (line length: 100, target: py311)

```bash
cd backend
ruff check app/ --fix
ruff format app/
```

### Frontend (TypeScript)

- TypeScript strict mode

```bash
cd frontend
npx tsc --noEmit
```

## Testing

```bash
cd backend
python -m pytest tests/ -v
```

## Pull Request Process

1. Create a feature branch from `main`: `git checkout -b feat/your-feature`
2. Ensure all tests pass and linting is clean
3. Write clear commit messages (conventional commits preferred)
4. Open a PR with a description of what changed and why

### Commit Message Convention

```
feat: add new sandbox lifecycle operation
fix: resolve connection data loss on restart
docs: update API reference
refactor: rename Provider to Connection
```

## Reporting Issues

- **Bugs**: Use GitHub Issues with the bug report template
- **Security**: See [SECURITY.md](SECURITY.md) — do NOT open public issues for security vulnerabilities
- **Feature requests**: Use GitHub Issues with the feature request template
