# 📬 Job Tracker

> AI-powered job application tracker — reads your Gmail, extracts application data with a LangGraph agent, stores it in a database, and displays it on a clean dashboard.

---

## Architecture

```
job-tracker/
├── backend/          # FastAPI + LangGraph agent + SQLAlchemy
│   └── app/
│       ├── graph/    # LangGraph state, nodes, graph assembly
│       ├── gmail/    # Gmail OAuth client & message fetcher
│       ├── db/       # ORM models & DB session
│       └── main.py   # FastAPI entrypoint
└── frontend/         # React + TypeScript + Vite dashboard
    └── src/
        ├── components/
        ├── pages/
        ├── hooks/
        ├── services/
        ├── store/
        ├── types/
        └── utils/
```

---

## Quick Start

### Backend

```bash
cd backend

# Using pip
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Or using Poetry
poetry install

# Configure environment
cp .env.example .env
# → fill in GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, OPENAI_API_KEY, etc.

# Run
uvicorn app.main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

---

## Stack

| Layer       | Technology                              |
|-------------|----------------------------------------|
| Agent       | LangGraph + LangChain                  |
| Email       | Gmail API (OAuth 2.0)                  |
| Backend     | FastAPI + SQLAlchemy + Alembic         |
| Database    | SQLite (dev) / PostgreSQL (prod)       |
| Frontend    | React 18 + TypeScript + Vite           |
| State       | Zustand + TanStack Query               |

---

## Gmail OAuth Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project → Enable **Gmail API**
3. Create **OAuth 2.0 credentials** → Download `credentials.json`
4. Place `credentials.json` in `backend/`
5. Set `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` in `.env`

---

## License

MIT
