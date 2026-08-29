"""统一LLM客户端：全项目共享单例，避免重复初始化"""
from langchain_ollama import ChatOllama, OllamaEmbeddings

llm = ChatOllama(model="qwen2.5:3b", temperature=0.7)
llm_json = ChatOllama(model="qwen2.5:3b", format="json", temperature=0.3)
# 简历提取用更低温度，输出更确定性
llm_json_strict = ChatOllama(model="qwen2.5:3b", format="json", temperature=0.1)
embeddings = OllamaEmbeddings(model="bge-m3")


def get_llm_with_temperature(temp: float) -> ChatOllama:
    """按指定温度创建临时 LLM 实例（面试追问温度递增用）"""
    return ChatOllama(model="qwen2.5:3b", temperature=temp)
