# 🚀 AI Workflow Automation & Multi-Agent Research Platform

A lightweight, high-performance platform for constructing automated AI workflows and generating comprehensive research reports using a multi-agent orchestration pipeline.

---

## ✨ Overview

This platform combines:

- 🤖 Multi-Agent Research System
- ⚡ Workflow Automation Engine
- 📚 Local RAG (Retrieval-Augmented Generation)
- 🔍 Semantic Search
- 🔐 Authentication & Authorization
- 📁 File Upload & Knowledge Management
- 📊 Real-Time Execution Tracking

The project is designed to run with minimal setup while providing enterprise-style workflow orchestration capabilities.

---

# 🏗️ Tech Stack

## Backend
- FastAPI
- SQLAlchemy ORM
- SQLite / PostgreSQL
- Google Gemini 4 (`gemini-4-hydrogen`) via the REST API
- JWT Authentication
- Server-Sent Events (SSE)

## Frontend
- React 18 SPA
- Tailwind CSS v4
- Vite build (JSX compiled at build time)
- Hash-locked dependencies via `package-lock.json`

## AI & Search
- Multi-Agent Pipeline
- RAG Architecture
- Vector Similarity Search
- Embedding Generation

---

# 📂 Project Structure

```text
ai-orchestrator/
│
├── backend/
│   ├── main.py
│   ├── models.py
│   ├── database.py
│   ├── auth.py
│   ├── agents.py
│   ├── gemini_client.py
│   ├── vector_store.py
│   ├── workflow_engine.py
│   ├── requirements.txt
│   ├── requirements/
│   │   ├── base.in / base.txt
│   │   ├── postgres.in / postgres.txt
│   │   ├── vector.in / vector.txt
│   │   └── dev.in / dev.txt
│   └── routes/
│       ├── auth.py
│       ├── agents.py
│       ├── workflows.py
│       ├── search.py
│       └── files.py
│
├── frontend/
│   ├── index.html
│   ├── index.css
│   ├── app.jsx
│   ├── config.js
│   ├── vite.config.js
│   ├── package.json
│   └── components/
│       ├── auth.jsx
│       ├── dashboard.jsx
│       ├── home.jsx
│       ├── workflows.jsx
│       ├── research.jsx
│       ├── files.jsx
│       └── search.jsx
│
├── Dockerfile
├── .dockerignore
├── .gitignore
├── .env.example
└── README.md
```

---

# ⚙️ Environment Configuration

## 1. Clone Repository

```bash
git clone https://github.com/<your-username>/ai-orchestrator.git
cd ai-orchestrator
```

---

## 2. Configure Environment Variables

Copy the environment template:

```bash
cp .env.example backend/.env
```

Open `backend/.env` and add:

```env
GEMINI_API_KEY=your_api_key_here
```

### Get Gemini API Key

Visit:

https://aistudio.google.com/

Generate a new API key and paste it into the `.env` file.

### Gemini models

The defaults target the current model generation:

```env
GEMINI_MODEL=gemini-4-hydrogen        # default general-purpose model
GEMINI_EMBED_MODEL=gemini-embedding-2 # multimodal embedding model
GEMINI_EMBED_DIM=768                  # must match the DB vector dimension
GEMINI_MODELS=gemini-4-hydrogen,gemini-3.5-flash-lite  # fallback chain
```

Use `python diagnose_gemini.py` to check which models your key can access.
If you switch `GEMINI_EMBED_MODEL` (or its dimension), re-index uploaded
documents: embedding spaces differ between models, so old vectors cannot be
compared with new ones.

---

## Optional: Use PostgreSQL / Supabase

Instead of SQLite:

```env
DATABASE_URL=postgresql://postgres:<password>@<host>.supabase.co:5432/postgres

SUPABASE_URL=https://<project-ref>.supabase.co

SUPABASE_SERVICE_ROLE_KEY=<service-role-key>
```

---

## Enable PGVector

Run inside Supabase SQL Editor:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

---

# 🔒 Security Notes

Never commit:

```text
.env
database credentials
API keys
service role keys
SQLite database files
```

The provided `.gitignore` already excludes these files.

---

# 🖥️ Backend Setup

Navigate to backend:

```bash
cd backend
```

## Create Virtual Environment

### Windows

```bash
python -m venv venv

venv\Scripts\activate
```

### Linux / macOS

```bash
python -m venv venv

source venv/bin/activate
```

---

## Install Dependencies

Dependencies are split into pinned, hash-locked sets:

| File | Contents |
|---|---|
| `requirements/base.txt` | Core runtime (SQLite deployments) |
| `requirements/postgres.txt` | base + `psycopg2-binary` + `pgvector` |
| `requirements/vector.txt` | base + `faiss-cpu` (optional ANN index) |
| `requirements/dev.txt` | base + `pytest` |

Install the default set:

```bash
pip install --require-hashes -r requirements.txt
```

Or pick what you need:

```bash
pip install --require-hashes -r requirements/postgres.txt
pip install --require-hashes -r requirements/vector.txt
```

Without `faiss-cpu` the app automatically uses the numpy brute-force
similarity path in `backend/vector_store.py`.

The lock files are generated from the `*.in` files:

```bash
uv pip compile requirements/base.in --universal --generate-hashes \
    --python-version 3.10 -o requirements/base.txt
```

---

## Run Server

```bash
python main.py
```

Backend runs at:

```text
http://localhost:8000
```

The SQLite database will be created automatically.

---

# 🎨 Frontend Setup

The frontend is a standard Vite + React app. JSX is compiled at build time;
there is no runtime Babel or service-worker transpilation.

---

## Option A (Recommended) — build once, serve from FastAPI

```bash
cd frontend
npm ci
npm run build
```

Start the backend:

```bash
cd ../backend
python main.py
```

Open:

```text
http://localhost:8000
```

FastAPI serves `frontend/dist` automatically. Set `FRONTEND_DIR` to point at a
different build output.

---

## Option B — Vite development server

```bash
cd frontend
npm run dev
```

Open:

```text
http://localhost:5173
```

Vite proxies `/api` to `http://localhost:8000`. Override the target with
`VITE_BACKEND_URL`.

---

# 🐳 Docker

```bash
docker build -t ai-orchestrator .
docker run --rm -p 8000:8000 --env-file backend/.env \
  -v "$PWD/uploads:/app/backend/uploaded_files" \
  ai-orchestrator
```

The image is a three-stage build:

1. `node:22-slim` builds the frontend with Vite.
2. `python:3.11-slim` installs the hash-locked Python dependencies into a venv.
3. `python:3.11-slim` copies only the venv, backend and built frontend, then
   runs as the non-root `app` user.

Notes:

- The default command uses a single worker because the FAISS index, caches and
  WebSocket registry are in-process.
- The Dockerfile installs `requirements/postgres.txt`. Switch to `base.txt` for
  a SQLite-only image.
- Bind-mount `orchestrator.db` if you need SQLite data to survive the container.

---

# 🤖 Multi-Agent Research Pipeline

The Research module uses a chain of specialized AI agents:

### 1. Planner Agent

Creates structured research sections.

### 2. Research Agent

Collects information and notes.

### 3. Critic Agent

Reviews findings for:

- Bias
- Logic gaps
- Missing information

### 4. Writer Agent

Generates the final report.

### 5. Citation Agent

Adds references and bibliography.

---

## Real-Time Streaming

Progress is streamed using:

```text
Server-Sent Events (SSE)
```

Users can watch research progress live.

---

# ⚙️ Workflow Automation Engine

Build custom DAG workflows using:

- Triggers
- LLM Nodes
- Delay Nodes
- API Request Nodes
- Conditional Logic

### Variable Binding

```text
{{node_id.output}}
```

Outputs can be passed between nodes dynamically.

---

# 📚 Local RAG (Retrieval-Augmented Generation)

Upload your documents through the Files Manager.

The system will:

1. Chunk documents
2. Generate embeddings
3. Store vectors
4. Enable semantic retrieval

Supported use cases:

- Knowledge bases
- Internal documentation
- Research archives
- Company policies

---

# 🔍 Semantic Search

Search across uploaded knowledge using vector similarity.

Features:

- Context-aware retrieval
- Similarity ranking
- Fast local lookup
- AI-enhanced responses

---

# 🔐 Authentication

Supports:

- JWT Authentication
- Password Hashing (bcrypt)
- Protected API Routes
- Session Management

---

# 📈 Future Enhancements

Planned features:

- Role-Based Access Control (RBAC)
- WebSockets
- Redis Caching
- Celery Workers
- Agent Marketplace
- Kubernetes Deployment
- LangGraph Integration
- OpenTelemetry Observability
- Multi-Tenant Architecture

---

# 🤝 Contributing

1. Fork the repository
2. Create a feature branch

```bash
git checkout -b feature/new-feature
```

3. Commit changes

```bash
git commit -m "Add new feature"
```

4. Push

```bash
git push origin feature/new-feature
```

5. Open a Pull Request

---

# 📜 License

MIT License

Feel free to use, modify, and distribute.

---

# ⭐ Support

If you found this project useful:

⭐ Star the repository

🍴 Fork the project

🛠️ Contribute improvements

📢 Share it with others