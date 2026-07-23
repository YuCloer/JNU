from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from langchain_ollama import ChatOllama, OllamaEmbeddings

from routers import resume, interview, jd

app = FastAPI(title="智能简历分析与AI模拟面试平台")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 全局 LLM 实例
llm = ChatOllama(model="qwen2.5:3b", temperature=0.7)
llm_json = ChatOllama(model="qwen2.5:3b", format="json", temperature=0.3)
embeddings = OllamaEmbeddings(model="bge-m3")

app.include_router(resume.router, prefix="/resume", tags=["简历解析"])
app.include_router(interview.router, prefix="/interview", tags=["模拟面试"])
app.include_router(jd.router, prefix="/jd", tags=["JD匹配"])


@app.get("/api/health")
async def health_check():
    return {"llm": "qwen2.5:3b", "embedding": "bge-m3", "status": "ok"}
