# Agent Reach Web

A premium web console for [Agent Reach](https://github.com/Panniantong/Agent-Reach) — your personal command center for internet access tools.

## Architecture

```
agent-reach-web/
├── backend/          # Python FastAPI server
│   ├── main.py       # Entry point (serves static UI + API)
│   ├── config.py     # Settings from .env
│   ├── static/       # Vanilla JS frontend (index.html)
│   ├── services/     # CLI runner & Agent Reach wrappers
│   └── routes/       # API endpoints
└── deploy/           # OracleVM deployment files
```

## Local Development

```bash
cd backend
python -m venv .venv
.venv/Scripts/activate       # Windows
# source .venv/bin/activate  # Linux/Mac
pip install -r requirements.txt
cp .env.example .env         # Edit with your settings
uvicorn main:app --reload --port 8000
```

Open http://localhost:8000 — the UI is served directly from the backend!

## OracleVM Deployment

See [deploy/DEPLOY.md](deploy/DEPLOY.md) for full instructions.
