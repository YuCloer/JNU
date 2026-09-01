# 智能简历分析与AI模拟面试平台

面向应届生的本地 AI 求职助手：上传简历即可获得结构化解析、JD 匹配分析和五轮模拟面试。项目采用 Vue 3、FastAPI 与 Ollama 构建，简历与模型推理均可保留在本机完成，不依赖第三方云端 API。

## 技术栈

- 前端：Vue3 + Vite + Axios
- 后端：FastAPI + SSE 流式响应
- 大模型：Ollama qwen2.5:3b（本地推理）
- LLM 框架：LangChain + LangGraph
- LLM 可观测性：LangSmith（可选追踪，默认关闭）
- 向量存储：Chroma + bge-m3
- PDF 解析：pdfplumber（多栏布局检测）
- 部署：Docker Compose

## 核心功能

1. 简历智能解析：上传 PDF/Word → 多栏布局检测 → AI 提取结构化信息 → 可视化预览
2. JD 匹配分析：粘贴岗位描述 → 三维加权匹配（学历20%+技能50%+经验30%）→ 动态权重技能对比 → 差距分析
3. AI 模拟面试：5 轮追问式面试 → 实时流式对话 → 综合评分与改进建议

## 简历解析架构

采用「LLM 提取 → 格式修正 → 正则兜底 → 强后处理」四层管线：

- **多栏 PDF 检测**：通过 word x 坐标分布（50-bin 直方图）自动识别分栏布局，按主内容栏→侧边栏顺序提取，避免左右栏交叉混排
- **LLM 格式修正（sanitize）**：3B 模型输出格式不稳定（skills 可能为对象数组、languages 可能为 dict、tech_stack 可能为 list），统一在 pydantic 验证前做格式转换，防止整个 LLM 结果作废
- **白名单技能过滤**：只保留已知技术词（60+）、中文技术白名单、或符合技术词特征的项，拒绝所有垃圾（日期、句子碎片、段落标题）
- **课程→技能推断**：从核心课程行提取课程名，通过 COURSE_SKILL_MAP（35+ 门课程）推断隐含技能（如 操作系统→Linux、计算机网络→TCP/IP）
- **语言能力提取**：LLM + 正则双通道，自动识别 CET/DELF/JLPT 等证书并归属正确语言
- **联系方式安全网**：预处理前先从原始文本提取邮箱/电话，防止多栏重组过程中丢失

## JD 匹配算法

技能匹配采用动态权重，而非等权计数：

```
最终权重 = 熟练度权重 × 专业度权重
```

- 熟练度（从 JD 上下文提取）：熟练/精通 = 1.0，能够/掌握 = 0.7，了解/优先 = 0.4
- 专业度（技能本身属性）：具体工具(Python/SQL/Docker) = 1.0，方法论(Prompt Engineering) = 0.8，笼统类别(AI工具/数据分析) = 0.6

JD 技能提取采用 LLM + 关键词规则始终合并策略（非仅 fallback），含 16 条隐性推断规则（如 "利用AI挖掘数据"→AI工具+数据挖掘）。

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
│       ├── resume_parser.py # 简历解析（四层管线 + 多栏检测）
│       ├── interview_agent.py # 面试 Agent（LangGraph）
│       └── jd_matcher.py    # JD 技能匹配（动态权重）
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
# 1. 拉取模型（仅首次）
ollama pull qwen2.5:3b
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

访问 http://localhost:5173

### Docker 部署

```bash
docker compose up -d
```

首次启动会自动下载 `qwen2.5:3b` 和 `bge-m3`，完成后访问 http://localhost:3000。默认配置可在 CPU 环境运行；如需 GPU 加速，请按本机 Docker 与 Ollama 的 GPU 配置启用运行时支持。

## LangSmith 可观测性

项目已接入 LangSmith 追踪，可用于查看简历解析、JD 匹配和模拟面试中的模型调用链路、输入输出与耗时。追踪默认关闭，确保本地使用时简历内容不会发送至第三方服务。

1. 复制 `.env.example` 为 `.env`，填入自己的 `LANGSMITH_API_KEY`。
2. 设置 `LANGSMITH_TRACING=true`；可用 `LANGSMITH_PROJECT` 指定项目名称。
3. 重启后端或执行 `docker compose up -d`，访问 `/api/health` 确认 `observability.enabled` 为 `true`。

启用追踪前请确认候选人已知悉其数据将被发送到 LangSmith；演示或开发建议使用脱敏简历。

## 可靠性与数据边界

- 上传文件仅支持 `.pdf` 与 `.docx`，单个文件最大 10MB。
- 后端对异常请求头、超长 JD/回答和无效面试轮次进行校验。
- 面试评分始终使用最近一道面试题与本次回答配对，避免对话记录重复导致评分偏差。
- 前端会在上传前提示超限文件，并在流式接口返回 HTTP 错误时显示可读错误信息。
- LangSmith 追踪必须同时配置开关和 API Key 才会启用，健康检查不返回密钥内容。

## 验收标准

- 多栏/单栏 PDF 简历均正确解析出姓名+学校+技能+项目经历
- 邮箱、电话、语言能力不丢失
- 技能标签无垃圾项（无日期、句子碎片、段落标题）
- 课程推断技能正确参与 JD 匹配
- 完整走完 5 轮面试，追问自然不卡顿
- 流式首 token 2s 内显示
- 面试报告含评分+逐题反馈+改进建议
- JD 匹配度按动态权重计算，专业技能权重高于笼统技能
