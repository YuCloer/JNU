"""JD匹配服务：技能标签提取与对比"""
import json
import re

from langchain_ollama import ChatOllama

llm_json = ChatOllama(model="qwen2.5:3b", format="json", temperature=0.3)

JD_SKILLS_PROMPT = """从以下岗位描述(JD)中提取所有技能要求，分为三类，返回JSON格式。

分类：
- technical: 技术技能（编程语言、框架、工具等）
- soft: 软技能（沟通、协作、领导力等）
- domain: 领域知识（行业经验、业务理解等）

返回格式：{{"technical": [...], "soft": [...], "domain": [...]}}

岗位描述：
{jd_text}"""

# 关键词兜底词库（LLM不可用时用正则匹配）
SKILL_KEYWORDS = {
    "technical": [
        "Python", "Java", "Go", "C++", "JavaScript", "TypeScript", "SQL",
        "React", "Vue", "Spring", "FastAPI", "Django", "Flask",
        "MySQL", "Redis", "MongoDB", "PostgreSQL",
        "Docker", "K8s", "Kubernetes", "Linux", "Git",
        "Spark", "Hive", "Hadoop", "Kafka",
        "TensorFlow", "PyTorch", "pandas", "numpy",
        "微服务", "分布式", "高并发", "API", "REST",
        "Tableau", "PowerBI", "Figma", "Axure",
    ],
    "soft": [
        "沟通", "协作", "团队合作", "领导力", "自驱力",
        "逻辑思维", "表达能力", "抗压", "责任心",
        "跨部门", "项目管理", "时间管理",
    ],
    "domain": [
        "数据分析", "机器学习", "深度学习", "NLP", "CV",
        "产品经理", "需求分析", "用户研究",
        "大数据", "数据可视化", "数据治理",
        "实习", "项目经验", "行业经验",
    ],
}


def extract_jd_skills(jd_text: str) -> dict:
    """从JD中提取技能标签（LLM优先，关键词兜底）"""
    try:
        result = llm_json.invoke(JD_SKILLS_PROMPT.format(jd_text=jd_text[:2000]))
        data = json.loads(result.content)
        skills = {
            "technical": data.get("technical", []),
            "soft": data.get("soft", []),
            "domain": data.get("domain", []),
        }
        # LLM返回全空也走兜底
        if not any(skills.values()):
            raise ValueError("LLM返回空结果")
        return skills
    except Exception:
        return _keyword_fallback(jd_text)


def _keyword_fallback(jd_text: str) -> dict:
    """不依赖LLM的关键词匹配兜底"""
    text_lower = jd_text.lower()
    result = {"technical": [], "soft": [], "domain": []}
    for category, keywords in SKILL_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in text_lower:
                result[category].append(kw)
    return result


def match_skills(resume_skills: list[str], jd_skills: dict) -> dict:
    """计算简历技能与JD技能的匹配度"""
    all_jd_skills = []
    for category_skills in jd_skills.values():
        all_jd_skills.extend([s.lower().strip() for s in category_skills])

    resume_lower = [s.lower().strip() for s in resume_skills]

    matched = []
    missing = []
    for skill in all_jd_skills:
        # 模糊匹配：简历技能包含JD技能关键词，或反过来
        if any(skill in rs or rs in skill for rs in resume_lower):
            matched.append(skill)
        else:
            missing.append(skill)

    total = len(all_jd_skills)
    match_rate = len(matched) / total if total > 0 else 0.0

    return {
        "matched": matched,
        "missing": missing,
        "match_rate": round(match_rate * 100, 1),
        "jd_skills": jd_skills,
    }
