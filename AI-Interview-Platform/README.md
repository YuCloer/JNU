# AI Interview Platform

A local-first workspace for resume analysis, job-description matching, and structured mock interviews.

The project is designed for candidates who want a repeatable preparation workflow without sending resume content to a third-party model by default. The frontend provides the workflow; the backend owns parsing, matching, and streaming interview orchestration.

## Capabilities

- **Resume analysis** — parse PDF/DOCX resumes, detect multi-column layouts, normalize model output, and preview structured information.
- **JD matching** — extract skills from a job description, apply proficiency and specificity weighting, and surface gaps.
- **Mock interviews** — run a five-round follow-up interview over SSE and produce scores, per-question feedback, and improvement suggestions.
- **Local deployment** — run the application with Ollama and Docker Compose; LangSmith tracing remains opt-in.

## Architecture

| Layer | Implementation |
| --- | --- |
| Frontend | Vue 3, Vite, Axios, Vue Router |
| API | FastAPI, Pydantic, SSE streaming |
| AI workflow | LangChain, LangGraph, Ollama |
| Retrieval | Chroma, bge-m3 |
| Document parsing | pdfplumber with layout-aware extraction |
| Delivery | Docker Compose |

The resume pipeline uses four defensive stages:

1. LLM extraction
2. schema and format normalization
3. regex and rule-based fallback
4. strict post-processing and allow-list filtering

This keeps malformed small-model output from invalidating the complete result.

## Repository structure

```
AI-Interview-Platform/
├── backend/
│   ├── main.py
│   ├── schemas.py
│   ├── routers/
│   └── services/
├── frontend/
│   ├── src/
│   └── package.json
└── docker-compose.yml
```

## Quick start

Requirements: Python 3.10+, Node 18+, Docker Compose, and Ollama.

```bash
ollama pull qwen2.5:3b
ollama pull bge-m3

docker compose up -d
```

For separate development servers:

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

```bash
cd frontend
npm install
npm run dev
```

The frontend is available at `http://localhost:5173`. Docker exposes the application at `http://localhost:3000` by default.

## Observability and data boundaries

LangSmith tracing is disabled by default. To enable it, copy `.env.example` to `.env`, provide a key, set `LANGSMITH_TRACING=true`, and restart the backend.

When tracing is enabled, prompts and model outputs may leave the local machine. Use redacted demo resumes unless the data owner has approved external processing. Health checks report observability status but never expose the API key.

## Current scope

- Supported uploads: PDF and DOCX, up to 10 MB per file.
- The project is optimized for local development and CPU-compatible defaults.
- Model quality depends on the selected Ollama model and local hardware.
- Advanced production concerns such as multi-user identity and hosted deployment are outside the current scope.
