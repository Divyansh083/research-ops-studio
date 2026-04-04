# Multi-Agent Research Assistant

Research workspace built with LangGraph, Groq, ChromaDB, a FastAPI backend, and a Next.js frontend.

## What It Does

- Plans research tasks with a LangGraph supervisor
- Uses web search, local RAG, dataset generation, and code execution agents
- Runs generated Python inside a dedicated sandbox under `.code_sandbox/`
- Lets users generate or upload datasets and analyze them from the UI
- Streams research progress live to the frontend

## Stack

- Frontend: Next.js
- Backend: FastAPI
- Orchestration: LangGraph
- LLM: Groq
- Embeddings: HuggingFace sentence transformers
- Vector store: ChromaDB
- Search: DuckDuckGo

## Project Layout

```text
app/         FastAPI app, LangGraph flow, tools, sandbox, ingestion
frontend/    Next.js frontend
data/        Sample, uploaded, generated, and test datasets/docs
scripts/     Project launch and setup helpers
tests/       Automated test suite
run.cmd      Windows launcher for backend + frontend
```

## Prerequisites

- Python 3.10+
- Node.js 18+
- A valid Groq API key

## Environment

Copy the environment files:

```bash
cp .env.example .env
cp frontend/.env.local.example frontend/.env.local
```

Set at least:

- `GROQ_API_KEY`
- `LLM_MODEL`

Default examples in [.env.example](C:\Users\user\Desktop\Personal_project\.env.example):

- `GROQ_API_KEY=your_groq_api_key_here`
- `LLM_MODEL=llama-3.3-70b-versatile`
- `EMBEDDING_MODEL=BAAI/bge-base-en-v1.5`

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
cd frontend
npm install
cd ..
```

### 2. Initialize the code sandbox

```bash
python -m app.sandbox.environment --setup-sandbox
```

### 3. Ingest the sample docs

```bash
python -m app.ingestion.ingest --path ./data/sample_docs
```

## Running the App

### Windows launcher

```powershell
.\run.cmd
```

Optional clean start:

```powershell
.\run.cmd clean
```

To stop only services started by the launcher:

```powershell
.\scripts\stop_all.cmd
```

`stop_all.cmd` only stops launcher-managed processes. It does not kill unrelated apps that happen to use ports `3000` or `8000`.

### Manual start

Terminal 1:

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Terminal 2:

```bash
cd frontend
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## Dataset Flow

- Local datasets under `data/` are auto-discovered
- Uploaded datasets are stored under `data/uploads/`
- Agent-generated datasets are stored under `data/generated/`
- The selected dataset is copied into the sandbox workspace before code execution

Example requests:

1. `Create a school dataset and then write and execute a Python script to analyze it.`
2. `Write and execute a Python script to analyze the available stock price dataset and explain the trend.`
3. `What are the key differences between RAG and fine-tuning for LLM customisation?`

## Code Sandbox

Generated Python is executed in the dedicated local sandbox, not in the main project interpreter.

Setup command:

```bash
python -m app.sandbox.environment --setup-sandbox
```

The sandbox is used for:

- Python package isolation
- local dataset staging
- code execution policy enforcement
- artifact generation

## Documents and RAG

Place `.pdf` or `.txt` documents in `data/sample_docs/` and ingest them with:

```bash
python -m app.ingestion.ingest --path ./data/sample_docs
python -m app.ingestion.ingest --path ./data/sample_docs --reset
```

## Testing

Run the full test suite:

```bash
python -m pytest tests -q
```

## Docker

```bash
docker compose up --build
```

Make sure your `.env` contains a valid `GROQ_API_KEY` before starting Docker.

This starts:

- API on `http://localhost:8000`
- frontend on `http://localhost:3000`

## Helpful Files

- [run.cmd](C:\Users\user\Desktop\Personal_project\run.cmd)
- [scripts/run_all.py](C:\Users\user\Desktop\Personal_project\scripts\run_all.py)
- [scripts/stop_all.cmd](C:\Users\user\Desktop\Personal_project\scripts\stop_all.cmd)
- [app/main.py](C:\Users\user\Desktop\Personal_project\app\main.py)
- [app/core/config.py](C:\Users\user\Desktop\Personal_project\app\core\config.py)
- [app/graph/llm.py](C:\Users\user\Desktop\Personal_project\app\graph\llm.py)
- [app/sandbox/environment.py](C:\Users\user\Desktop\Personal_project\app\sandbox\environment.py)
- [frontend/app/page.tsx](C:\Users\user\Desktop\Personal_project\frontend\app\page.tsx)

## Notes

- `chroma_db/` is created on first ingestion
- LangSmith tracing is optional and controlled via `.env`
- If PowerShell blocks `npm`, use `npm.cmd`
