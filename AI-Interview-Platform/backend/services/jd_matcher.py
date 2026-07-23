"""JD匹配服务：技能标签提取与对比"""
import json

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


def extract_jd_skills(jd_text: str) -> dict:
    """从JD中提取技能标签"""
    try:
        result = llm_json.invoke(JD_SKILLS_PROMPT.format(text=jd_text[:2000]))
        data = json.loads(result.content)
        return {
            "technical": data.get("technical", []),
            "soft": data.get("soft", []),
            "domain": data.get("domain", []),
        }
    except Exception:
        return {"technical": [], "soft": [], "domain": []}


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
