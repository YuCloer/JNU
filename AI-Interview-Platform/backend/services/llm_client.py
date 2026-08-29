"""统一LLM客户端：全项目共享单例，避免重复初始化"""
import os

from langchain_ollama import ChatOllama, OllamaEmbeddings

OLLAMA_BASE_URL = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")

llm = ChatOllama(model="qwen2.5:3b", temperature=0.7, base_url=OLLAMA_BASE_URL)
llm_json = ChatOllama(model="qwen2.5:3b", format="json", temperature=0.3, base_url=OLLAMA_BASE_URL)
# 简历提取用更低温度，输出更确定性
llm_json_strict = ChatOllama(model="qwen2.5:3b", format="json", temperature=0.1, base_url=OLLAMA_BASE_URL)
embeddings = OllamaEmbeddings(model="bge-m3", base_url=OLLAMA_BASE_URL)


def get_llm_with_temperature(temp: float) -> ChatOllama:
    """按指定温度创建临时 LLM 实例（面试追问温度递增用）"""
    return ChatOllama(model="qwen2.5:3b", temperature=temp, base_url=OLLAMA_BASE_URL)
