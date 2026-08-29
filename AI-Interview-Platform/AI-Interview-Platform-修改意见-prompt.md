---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: 280c1ea30953ad340ba32f22d4b3a756_e486ff958c1e11f1a642525400287e28
    ReservedCode1: +2aDewQY1Kt0l8jufha6Pss9yml0JaW1C5Q+rj16TZRAjs+Sg/8a7y0eMvduAfzZIOKQS1iDkpE0xjPztbSGMtlh940SHFstXVETPohRrq56AlHKESVUq17MdqK52Q4hRBldVr6GM8YmACYnkfVYp3B3tLUqYA2OradmrtikfWuWTJ42g5bDZGdJDxE=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: 280c1ea30953ad340ba32f22d4b3a756_e486ff958c1e11f1a642525400287e28
    ReservedCode2: +2aDewQY1Kt0l8jufha6Pss9yml0JaW1C5Q+rj16TZRAjs+Sg/8a7y0eMvduAfzZIOKQS1iDkpE0xjPztbSGMtlh940SHFstXVETPohRrq56AlHKESVUq17MdqK52Q4hRBldVr6GM8YmACYnkfVYp3B3tLUqYA2OradmrtikfWuWTJ42g5bDZGdJDxE=
---

你正在维护项目 D:\Program Files\PyCharm\AI-Interview-Platform（智能简历分析与AI模拟面试平台，FastAPI + Vue3 + Ollama Qwen2.5:3b + LangGraph）。

请按以下清单逐一修改，每完成一项输出"✅ 已完成：xxx"。

---

## 1. 修复 /api/health 健康检查（backend/main.py）

当前 health 端点只检查 LLM 连通性，未检查 Embedding（bge-m3）。
修改 `health_check` 函数：增加对 Embedding 的连通性验证（调用 `embeddings.embed_query("test")`），
失败时 status 降为 "degraded" 并返回 `embedding_error` 字段。
同时需要从 `services.llm_client` 导入 `embeddings` 单例。

---

## 2. 补充 requirements.txt（backend/requirements.txt）

检查 backend/requirements.txt 是否包含 `pdfplumber`。
当前 `resume_parser.py` 实际使用 pdfplumber 作为 PDF 提取主力（PyPDF2 仅为 fallback），
如果 requirements.txt 中缺少 pdfplumber，请添加。

---

## 3. 追问策略温度递增（backend/services/interview_agent.py）

方案要求："轮次越多温度越高增加变体"（防止追问机械重复）。

修改 `astream_next_question` 和 `get_next_question` 函数：
- 根据当前 round_num 动态调整 llm 的 temperature：round 1-2 使用默认 0.7，round 3 使用 0.85，round 4-5 使用 1.0
- 在 services/llm_client.py 中增加一个 `get_llm_with_temperature(temp)` 工厂函数，或临时创建 ChatOllama 实例

---

## 4. SSE 断连自动重连（frontend/src/views/InterviewView.vue）

方案要求："EventSource 自动重连 + 状态断点恢复"。

当前代码使用 fetch + ReadableStream 实现 SSE，断开后无重连机制。
请增加以下逻辑：
- 在 catch 块中捕获网络错误后，显示"连接中断，xx 秒后自动重连"提示
- 使用指数退避策略（2s / 4s / 8s，最多重试 3 次）
- 重连时从 history 的最后一轮恢复，避免重复问题
- 重试 3 次仍失败后显示"请刷新页面重试"

---

## 5. 补充 Chroma 服务到 docker-compose.yml

方案要求的 docker-compose 包含：Ollama + FastAPI + Chroma + Nginx+Vue。
当前 docker-compose.yml 缺少 Chroma 向量数据库服务。

请在 docker-compose.yml 中增加 chroma 服务：
```yaml
chroma:
  image: chromadb/chroma:latest
  ports:
    - "8001:8000"
  volumes:
    - chroma_data:/chroma/chroma
  environment:
    - IS_PERSISTENT=TRUE
```
backend 的 depends_on 增加 chroma，environment 增加 `CHROMA_HOST=http://chroma:8000`。
volumes 增加 `chroma_data:`。

---

## 6. 简历预览页可编辑字段扩展（frontend/src/views/UploadView.vue）

方案要求简历预览卡片"可编辑字段"。当前仅基本信息（姓名/邮箱/手机）可编辑。
请将以下区域也改为可编辑：
- 技能标签：每个 tag 旁增加删除按钮（×），底部增加输入框+添加按钮
- 教育经历：每个条目增加"编辑"按钮，弹出内联编辑表单（学校/专业/学历/起止日期）
- 项目经历：每个条目增加"编辑"按钮，可修改名称/角色/描述/技术栈

---

## 7. 面试报告改进建议数量兜底（backend/services/interview_agent.py）

方案要求改进建议 ≥ 3 条。当前 `REPORT_PROMPT` prompt 中已要求 3 条，但兜底代码仅返回 2 条：
```
"improvements": ["建议补充更多项目细节", "注意量化成果"],
```
请改为 3 条兜底建议，例如增加"建议提前准备岗位相关技术问题的回答思路"。

---

## 8. 异常覆盖补充

### 8.1 简历解析超时友好提示（backend/routers/resume.py）
当前上传接口有 60s 超时，但前端只显示通用"解析失败"。请在 catch 中判断超时类型，
返回更友好的错误信息："解析超时，请确认 Ollama 服务运行正常，或尝试简化简历格式后重试"。

### 8.2 文件格式不支持的后端校验（backend/routers/resume.py）
当前仅前端检查扩展名，后端应将文件格式校验也加上：在 `extract_text_from_file` 中捕获 `ValueError`，
返回 400 错误 "仅支持 PDF 和 Word(.docx) 格式"。

### 8.3 Ollama 模型不可达的前端全局拦截（frontend/src/api/index.js）
在 Axios 响应拦截器中增加：当后端返回 500 且包含 "ollama" 或 "模型" 关键字时，
通过 alert 或 toast 提示用户"模型服务不可达，请确认 Ollama 已启动"。

---

## 9. UI 打磨

### 9.1 空态处理
- 面试页面（InterviewView.vue）：当 messages 为空且 loading 时，显示骨架屏或"正在准备面试问题..."
- 报告页面（ReportView.vue）：当 rounds 为空时，显示"暂无面试记录"并引导用户去面试

### 9.2 过渡动效
- 全局样式（style.css）：为 `.card` 添加 `transition: all 0.2s ease`
- 面试聊天气泡：新消息添加 `slide-up` 动画（从下方淡入上滑）

### 9.3 移动端适配
- 全局样式增加 @media (max-width: 480px) 断点
- 导航栏：brand 缩小字号，links 间距缩小
- main-content：减小 padding
- 面试聊天区：高度从 420px 调整为 calc(100vh - 320px)
- 简历信息网格：从 3 列改为 1 列

---

## 10. 补充 README.md 启动说明

检查 D:\Program Files\PyCharm\AI-Interview-Platform\README.md，
确保包含以下内容（有则跳过，无则补充）：
- 环境要求：Python 3.10+, Node 18+, Ollama
- 启动步骤：
  1. `ollama pull qwen2.5:3b && ollama pull bge-m3`
  2. `cd backend && pip install -r requirements.txt && uvicorn main:app --port 8000`
  3. `cd frontend && npm install && npm run dev`
  4. 访问 http://localhost:5173
- Docker 启动：`docker compose up -d`

---

请按顺序逐一修改，完成后报告修改的文件和行数变更。
*（内容由AI生成，仅供参考）*
