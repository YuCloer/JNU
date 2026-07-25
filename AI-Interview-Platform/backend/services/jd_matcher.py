"""JD匹配服务：技能标签提取与对比（含隐性技能推断）"""
import json
import re

from langchain_ollama import ChatOllama

llm_json = ChatOllama(model="qwen2.5:3b", format="json", temperature=0.3)

JD_SKILLS_PROMPT = """从以下岗位描述(JD)中提取技能要求，分为三类，返回JSON格式。

【technical 的严格定义】
technical 必须是具体的工具/方法/技术名称，即简历"技能"栏能写的东西。
✓ 正确示例：SQL、Python、Excel数据透视表、A/B测试、用户画像分析、活动策划、数据可视化、AI工具（Copilot/ChatGPT）、SOP撰写、漏斗分析
✗ 错误示例（这些是工作目标/职责，不是技能）：用户增长、数据管理体系、标准化业务流程、推广活动策划、提升渗透率、制定运营策略

【推断规则】从职责描述推断背后需要的具体技能：
- "利用AI挖掘用户行为数据" → AI工具应用、数据挖掘
- "数据反馈/核心指标敏感" → 数据分析、SQL
- "用户增长/渗透率" → A/B测试、漏斗分析
- "制定运营策略" → 活动策划、文档撰写
- "标准化业务流程" → SOP撰写、流程管理
- "具备AI应用经验" → AI工具（Copilot/ChatGPT/Midjourney）

分类：
- technical: 具体工具/方法/技术（简历技能栏能写的）
- soft: 纯软素质（沟通、协作、责任心——不写进技能栏）
- domain: 行业知识（游戏运营、电商——了解即可）

返回格式：{{"technical": [...], "soft": [...], "domain": [...]}}

岗位描述：
{jd_text}"""

# 关键词兜底词库（覆盖多岗位类型）
SKILL_KEYWORDS = {
    "technical": [
        # 编程语言
        "Python", "Java", "Go", "C++", "C#", "JavaScript", "TypeScript", "SQL", "R",
        # 后端/框架
        "React", "Vue", "Spring", "FastAPI", "Django", "Flask", "Node.js",
        # 数据库/数据
        "MySQL", "Redis", "MongoDB", "PostgreSQL", "Excel", "数据透视表",
        "Spark", "Hive", "Hadoop", "Kafka", "ETL",
        # 数据分析/BI
        "Tableau", "PowerBI", "pandas", "numpy", "数据分析", "数据挖掘",
        "A/B测试", "用户画像", "漏斗分析", "增长分析",
        # AI/机器学习
        "TensorFlow", "PyTorch", "机器学习", "深度学习", "NLP", "CV",
        "AI工具", "Copilot", "ChatGPT", "Midjourney", "Stable Diffusion",
        "Prompt", "大模型", "LLM",
        # 设计/产品
        "Figma", "Axure", "Sketch", "Photoshop", "PR", "AE",
        "原型设计", "交互设计", "UI设计",
        # 运营/营销
        "SEO", "SEM", "信息流", "投放", "ROI", "转化率",
        "内容运营", "用户运营", "活动运营", "社群运营",
        "文案撰写", "文档撰写", "SOP",
        # 工程/部署
        "Docker", "K8s", "Kubernetes", "Linux", "Git", "CI/CD",
        "微服务", "分布式", "高并发", "API", "REST",
        # 项目管理
        "Jira", "飞书", "Notion", "项目管理", "敏捷开发",
    ],
    "soft": [
        "沟通", "协作", "团队合作", "领导力", "自驱力",
        "逻辑思维", "表达能力", "抗压", "责任心",
        "跨部门", "时间管理", "快速学习", "目标导向",
    ],
    "domain": [
        "游戏运营", "游戏发行", "电商", "金融", "教育",
        "产品经理", "需求分析", "用户研究", "商业思维",
        "行业经验", "实习", "项目经验",
    ],
}

# 隐性技能推断规则（职责描述 → 推断出的具体技能）
IMPLICIT_SKILL_RULES = [
    (r"AI.*挖掘|利用AI|AI应用|AI智能", ["AI工具应用", "数据挖掘"]),
    (r"数据反馈|数据管理|数据体系|核心指标", ["数据分析", "SQL"]),
    (r"用户增长|渗透率|预约.*规模", ["漏斗分析", "A/B测试"]),
    (r"运营策略|推广活动|发行", ["活动策划", "文档撰写"]),
    (r"用户行为|行为数据|用户模型", ["用户画像分析", "数据挖掘"]),
    (r"标准化.*流程|业务流程", ["SOP撰写", "流程管理"]),
    (r"渠道资源|内外渠道", ["渠道运营", "资源整合"]),
    (r"转化效率|策略转化", ["转化分析", "A/B测试"]),
]

# 非技能黑名单（这些是工作目标/职责描述，不是简历技能栏能写的东西）
NON_SKILL_PATTERNS = [
    "用户增长", "数据管理体系", "标准化业务流程", "推广活动策划",
    "提升渗透率", "制定运营策略", "扩大规模", "提升效率",
    "快速上线", "阶段性运营", "整体渗透率", "活跃.*规模",
    "业务目标", "数据反馈", "运营逻辑", "商业.*思维",
    "产品思维", "工作落地", "优化和改进",
]


def _filter_non_skills(skills: list[str]) -> list[str]:
    """过滤掉不像技能的词（工作目标/职责描述）"""
    filtered = []
    for s in skills:
        s_lower = s.lower().strip()
        # 跳过黑名单命中的
        if any(re.search(p, s_lower) for p in NON_SKILL_PATTERNS):
            continue
        # 跳过太长的（超过12字大概率是句子不是技能名）
        if len(s) > 12:
            continue
        filtered.append(s)
    return filtered


def extract_jd_skills(jd_text: str) -> dict:
    """从JD中提取技能标签（LLM优先，关键词+规则兜底）"""
    try:
        result = llm_json.invoke(JD_SKILLS_PROMPT.format(jd_text=jd_text[:2000]))
        data = json.loads(result.content)
        skills = {
            "technical": _filter_non_skills(data.get("technical", [])),
            "soft": data.get("soft", []),
            "domain": data.get("domain", []),
        }
        if not any(skills.values()):
            raise ValueError("LLM返回空结果")
        return skills
    except Exception:
        return _keyword_fallback(jd_text)


def _keyword_fallback(jd_text: str) -> dict:
    """不依赖LLM的关键词匹配 + 隐性技能推断"""
    text_lower = jd_text.lower()
    result = {"technical": [], "soft": [], "domain": []}

    # 直接关键词匹配
    for category, keywords in SKILL_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in text_lower:
                result[category].append(kw)

    # 隐性技能推断
    for pattern, inferred_skills in IMPLICIT_SKILL_RULES:
        if re.search(pattern, jd_text):
            for skill in inferred_skills:
                if skill not in result["technical"]:
                    result["technical"].append(skill)

    return result


def match_position(resume_data: dict, resume_skills: list[str], jd_skills: dict, jd_text: str) -> dict:
    """岗位匹配度：学历(20%) + 技能(50%) + 经验/项目(30%) 加权"""

    # ===== 维度一：学历匹配 (20%) =====
    edu_result = _match_education(resume_data, jd_text)

    # ===== 维度二：技能匹配 (50%) =====
    technical_skills = jd_skills.get("technical", [])
    matched = []
    missing = []
    for jd_skill in technical_skills:
        if _skill_matches(jd_skill, resume_skills):
            matched.append(jd_skill)
        else:
            missing.append(jd_skill)
    skill_total = len(technical_skills)
    skill_rate = len(matched) / skill_total if skill_total > 0 else 0.0

    # ===== 维度三：经验/项目相关性 (30%) =====
    exp_result = _match_experience(resume_data, jd_text)

    # ===== 加权综合 =====
    overall = round(
        edu_result["score"] * 0.2 + skill_rate * 0.5 + exp_result["score"] * 0.3, 3
    )

    return {
        "match_rate": round(overall * 100, 1),
        "dimensions": {
            "education": edu_result,
            "skills": {"matched": matched, "missing": missing, "rate": round(skill_rate * 100, 1)},
            "experience": exp_result,
        },
        "jd_skills": jd_skills,
        "soft_requirements": jd_skills.get("soft", []),
        "domain_requirements": jd_skills.get("domain", []),
        # 兼容前端旧字段
        "matched": matched,
        "missing": missing,
    }


def _match_education(resume_data: dict, jd_text: str) -> dict:
    """学历维度匹配"""
    # 从JD提取学历要求
    jd_edu = "不限"
    if re.search(r"硕士|研究生", jd_text):
        jd_edu = "硕士"
    elif re.search(r"本科|学士", jd_text):
        jd_edu = "本科"
    elif re.search(r"大专|专科", jd_text):
        jd_edu = "大专"

    # 从简历提取学历
    resume_edu = "未知"
    for edu in resume_data.get("education", []):
        degree = edu.get("degree", "")
        if "硕士" in degree or "研究生" in degree:
            resume_edu = "硕士"
            break
        elif "本科" in degree or "学士" in degree:
            resume_edu = "本科"
        elif "大专" in degree or "专科" in degree:
            if resume_edu == "未知":
                resume_edu = "大专"

    # 计算得分
    edu_levels = {"大专": 1, "本科": 2, "硕士": 3, "博士": 4}
    if jd_edu == "不限":
        score = 1.0
    elif resume_edu == "未知":
        score = 0.5  # 无法判断给半分
    else:
        jd_level = edu_levels.get(jd_edu, 2)
        resume_level = edu_levels.get(resume_edu, 0)
        score = 1.0 if resume_level >= jd_level else 0.3

    return {"required": jd_edu, "actual": resume_edu, "score": score,
            "detail": f"岗位要求{jd_edu}，简历为{resume_edu}"}


def _match_experience(resume_data: dict, jd_text: str) -> dict:
    """经验/项目相关性维度"""
    # 从JD提取关键业务词
    jd_keywords = set()
    biz_patterns = [
        r"游戏", r"运营", r"发行", r"电商", r"金融", r"教育",
        r"数据", r"AI", r"用户", r"产品", r"增长", r"营销",
    ]
    for p in biz_patterns:
        if re.search(p, jd_text):
            jd_keywords.add(p.strip("r\""))

    if not jd_keywords:
        return {"score": 0.5, "detail": "JD无明确行业要求", "hits": []}

    # 在简历项目+经历中查找命中
    resume_text = ""
    for proj in resume_data.get("projects", []):
        resume_text += proj.get("name", "") + proj.get("description", "") + proj.get("tech_stack", "")
    for exp in resume_data.get("experiences", []):
        resume_text += exp.get("company", "") + exp.get("position", "") + exp.get("description", "")

    hits = []
    for kw in jd_keywords:
        if kw.lower() in resume_text.lower():
            hits.append(kw)

    score = len(hits) / len(jd_keywords) if jd_keywords else 0.5
    return {"score": round(score, 2), "detail": f"命中{len(hits)}/{len(jd_keywords)}个行业关键词", "hits": hits}


# 保留旧接口兼容
def match_skills(resume_skills: list[str], jd_skills: dict) -> dict:
    """（旧接口）纯技能匹配"""
    technical_skills = jd_skills.get("technical", [])
    matched = []
    missing = []
    for jd_skill in technical_skills:
        if _skill_matches(jd_skill, resume_skills):
            matched.append(jd_skill)
        else:
            missing.append(jd_skill)
    total = len(technical_skills)
    match_rate = len(matched) / total if total > 0 else 0.0
    return {"matched": matched, "missing": missing, "match_rate": round(match_rate * 100, 1)}


def _skill_matches(jd_skill: str, resume_skills: list[str]) -> bool:
    """判断一个JD技能是否与简历中任一技能匹配（模糊）"""
    jd_lower = jd_skill.lower().strip()
    jd_tokens = _tokenize(jd_lower)

    for rs in resume_skills:
        rs_lower = rs.lower().strip()
        # 完整包含
        if jd_lower in rs_lower or rs_lower in jd_lower:
            return True
        # 关键词交集（至少共享一个2字以上的词素）
        rs_tokens = _tokenize(rs_lower)
        for jt in jd_tokens:
            if len(jt) >= 2 and any(jt in rt for rt in rs_tokens):
                return True
    return False


def _tokenize(skill: str) -> list[str]:
    """把技能名拆成词素列表"""
    # 按常见分隔符拆分
    parts = re.split(r"[/、+\-\s()（）]+", skill)
    tokens = []
    for p in parts:
        p = p.strip()
        if p:
            tokens.append(p)
            # 中文技能额外按2-gram拆（如"数据分析"→["数据","分析"]）
            if len(p) >= 4 and not p.isascii():
                for i in range(0, len(p) - 1, 2):
                    chunk = p[i:i+2]
                    if len(chunk) == 2:
                        tokens.append(chunk)
    return tokens
