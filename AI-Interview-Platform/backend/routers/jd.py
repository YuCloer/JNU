"""JD匹配路由"""
import asyncio

from fastapi import APIRouter, HTTPException

from schemas import JDAnalyzeRequest
from services.jd_matcher import extract_jd_skills, match_position

router = APIRouter()

# 预设岗位模板
JD_TEMPLATES = {
    "sde": """岗位职责：
1. 负责后端服务的设计与开发
2. 参与系统架构设计与技术选型
3. 编写高质量、可维护的代码

任职要求：
- 熟悉 Python/Java/Go 至少一种语言
- 了解常用数据结构与算法
- 熟悉 Linux 基本操作
- 了解数据库（MySQL/Redis）
- 有团队协作经验，良好的沟通能力
- 加分项：了解 Docker/K8s、微服务架构""",

    "pm": """岗位职责：
1. 负责产品需求分析与PRD撰写
2. 推动跨部门协作，跟进项目进度
3. 分析用户反馈，持续优化产品体验

任职要求：
- 较强的逻辑思维与表达能力
- 熟练使用 Axure/Figma 等原型工具
- 了解基本的技术概念（API、数据库）
- 有数据分析意识
- 自驱力强，能适应快节奏
- 加分项：有实习/项目经验""",

    "data": """岗位职责：
1. 负责数据清洗、分析与可视化
2. 建立数据指标体系，输出分析报告
3. 支持业务决策，挖掘数据价值

任职要求：
- 熟悉 Python（pandas/numpy）
- 掌握 SQL
- 了解机器学习基础
- 熟悉至少一种可视化工具（Tableau/PowerBI）
- 良好的业务理解能力
- 加分项：了解大数据生态（Spark/Hive）""",
}


@router.get("/templates")
async def get_templates():
    """获取预设JD模板列表"""
    return {"templates": {k: v[:50] + "..." for k, v in JD_TEMPLATES.items()}}


@router.post("/analyze")
async def analyze_jd(request: JDAnalyzeRequest):
    """分析JD并与简历技能对比"""
    jd_text = request.jd_text.strip()
    if not jd_text:
        raise HTTPException(status_code=400, detail="JD文本不能为空")

    # 检查是否是模板key
    if jd_text in JD_TEMPLATES:
        jd_text = JD_TEMPLATES[jd_text]

    # 提取JD技能
    jd_skills = await asyncio.to_thread(extract_jd_skills, jd_text)

    # 从简历全部字段提取能力标签（不只是skills数组）
    resume_skills = _build_resume_capabilities(request.resume_data)

    # 岗位匹配度（学历20% + 技能50% + 经验30%）
    match_result = await asyncio.to_thread(
        match_position, request.resume_data, resume_skills, jd_skills, jd_text
    )

    return {
        "status": "ok",
        "jd_skills": jd_skills,
        "resume_skills": resume_skills,
        "match": match_result,
    }


def _build_resume_capabilities(resume_data: dict) -> list[str]:
    """从简历全部字段提取能力标签，不只是skills数组"""
    caps = []

    # 1. 显式技能栏
    caps.extend(resume_data.get("skills", []))

    # 2. 教育背景 → 学历本身就是一种资质
    for edu in resume_data.get("education", []):
        degree = edu.get("degree", "")
        if "本科" in degree or "学士" in degree:
            caps.append("本科学历")
        elif "硕士" in degree or "研究生" in degree:
            caps.append("硕士学历")
        major = edu.get("major", "")
        if major:
            caps.append(major)

    # 3. 项目经历 → 从tech_stack和description中提取工具/方法
    for proj in resume_data.get("projects", []):
        tech = proj.get("tech_stack", "")
        if tech:
            # tech_stack可能是逗号分隔的字符串
            for t in tech.replace("、", ",").replace("/", ",").split(","):
                t = t.strip()
                if t and len(t) <= 15:
                    caps.append(t)
        desc = proj.get("description", "")
        # 从项目描述中推断隐含能力
        if any(kw in desc for kw in ["AI", "ai", "模型", "LLM", "大模型", "Ollama", "LangChain"]):
            caps.append("AI工具应用")
        if any(kw in desc for kw in ["数据", "分析", "统计", "可视化"]):
            caps.append("数据分析")
        if any(kw in desc for kw in ["Git", "git", "GitHub", "版本控制"]):
            caps.append("Git")
        if any(kw in desc for kw in ["API", "接口", "后端", "FastAPI", "Flask"]):
            caps.append("API开发")
        if any(kw in desc for kw in ["文档", "README", "说明"]):
            caps.append("文档撰写")

    # 4. 工作/实习经历
    for exp in resume_data.get("experiences", []):
        desc = exp.get("description", "")
        if any(kw in desc for kw in ["数据", "分析", "报表"]):
            caps.append("数据分析")
        if any(kw in desc for kw in ["策划", "活动", "运营"]):
            caps.append("活动策划")
        if any(kw in desc for kw in ["团队", "协作", "跨部门"]):
            caps.append("团队协作")

    # 去重（不区分大小写）
    seen = set()
    unique = []
    for c in caps:
        key = c.lower().strip()
        if key and key not in seen:
            seen.add(key)
            unique.append(c.strip())
    return unique
