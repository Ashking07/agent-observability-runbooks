# Agent Observability & Runbooks (MVP)

## Backend setup (local)
Requirements:
- Python 3.11
- Postgres

### 1) Create venv + install deps
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

### 2) Configure env
cp .env.example .env
# edit .env if needed

### 3) Run DB migrations
alembic upgrade head

### 4) Start API
uvicorn app.main:app --reload --port 8000

### 5) Health check
curl http://localhost:8000/health
