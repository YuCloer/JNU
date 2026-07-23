# 智能简历分析与AI模拟面试平台

基于 Python 的 AI 应用开发实训项目。面向应届生的本地 AI 求职助手——上传简历即可获得智能解析、岗位匹配分析与多轮模拟面试，全程零云端依赖。

## 技术栈

- 前端：Vue3 + Vite + Axios
- 后端：FastAPI + SSE 流式响应
- 大模型：Ollama qwen2.5:3b（本地推理）
- LLM 框架：LangChain + LangGraph
- 向量存储：Chroma + bge-m3
- 部署：Docker Compose

## 核心功能

1. 简历智能解析：上传 PDF/Word → AI 提取结构化信息 → 可视化预览
2. JD 匹配分析：粘贴岗位描述 → 技能标签对比 → 差距分析
3. AI 模拟面试：5 轮追问式面试 → 实时流式对话 → 综合评分与改进建议

## 项目结构

```
AI-Interview-Platform/
├── backend/
│   ├── main.py              # FastAPI 入口
│   ├── schemas.py           # Pydantic 数据模型
│   ├── requirements.txt     # Python 依赖
│   ├── routers/
│   │   ├── resume.py        # 简历解析路由
│   │   ├── interview.py     # 面试对话路由（SSE）
│   │   └── jd.py            # JD 匹配路由
│   └── services/
│       ├── resume_parser.py # 简历解析（三层兜底）
│       ├── interview_agent.py # 面试 Agent（LangGraph）
│       └── jd_matcher.py    # JD 技能匹配
├── frontend/
│   ├── src/
│   │   ├── views/           # 四个页面
│   │   ├── api/             # Axios 封装
│   │   ├── router/          # Vue Router
│   │   └── components/      # 公共组件
│   └── package.json
└── docker-compose.yml
```

## 快速启动

### 环境要求

- Python 3.10+
- Node 18+
- Ollama（已安装 qwen2.5:3b）

### 本地开发

```bash
# 1. 拉取 Embedding 模型（仅首次）
ollama pull bge-m3

# 2. 启动后端
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# 3. 启动前端
cd frontend
npm install
npm run dev
```

访问 http://localhost:3000

### Docker 部署

```bash
docker compose up --build
```

访问 http://localhost:3000

## 验收标准

- 3 份不同格式简历均正确解析出姓名+学校+技能
- 完整走完 5 轮面试，追问自然不卡顿
- 流式首 token 2s 内显示
- 面试报告含评分+逐题反馈+改进建议
