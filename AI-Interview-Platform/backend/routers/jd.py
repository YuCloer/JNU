"""JD匹配路由"""
from fastapi import APIRouter, HTTPException

from schemas import JDAnalyzeRequest
from services.jd_matcher import extract_jd_skills, match_skills

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
    jd_skills = extract_jd_skills(jd_text)

    # 获取简历技能
    resume_skills = request.resume_data.get("skills", [])

    # 计算匹配度
    match_result = match_skills(resume_skills, jd_skills)

    return {
        "status": "ok",
        "jd_skills": jd_skills,
        "resume_skills": resume_skills,
        "match": match_result,
    }
