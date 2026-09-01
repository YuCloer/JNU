import asyncio

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from routers import resume, interview, jd
from services.llm_client import llm, embeddings, get_langsmith_status

app = FastAPI(title="智能简历分析与AI模拟面试平台")

# CORS：仅允许本地开发前端访问，生产部署时改为实际域名
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10MB


@app.middleware("http")
async def limit_upload_size(request: Request, call_next):
    """拒绝超过10MB的请求体，防止大文件DoS"""
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_UPLOAD_SIZE:
                return JSONResponse(status_code=413, content={"detail": "文件过大，最大支持10MB"})
        except ValueError:
            return JSONResponse(status_code=400, content={"detail": "无效的 Content-Length 请求头"})
    return await call_next(request)

app.include_router(resume.router, prefix="/resume", tags=["简历解析"])
app.include_router(interview.router, prefix="/interview", tags=["模拟面试"])
app.include_router(jd.router, prefix="/jd", tags=["JD匹配"])


@app.get("/api/health")
async def health_check():
    """健康检查：验证 Ollama LLM 和 Embedding 是否可用"""
    status = {
        "llm": "qwen2.5:3b",
        "embedding": "bge-m3",
        "observability": get_langsmith_status(),
        "status": "ok",
    }
    try:
        await asyncio.to_thread(llm.invoke, "hi")
    except Exception:
        status["status"] = "degraded"
        status["llm_error"] = "Ollama 不可达，请确认 ollama serve 已启动"
    try:
        await asyncio.to_thread(embeddings.embed_query, "test")
    except Exception:
        status["status"] = "degraded"
        status["embedding_error"] = "Embedding 模型不可达，请确认 bge-m3 已拉取"
    return status
