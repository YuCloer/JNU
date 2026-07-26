"""JD匹配服务：技能标签提取与对比（含隐性技能推断）"""
import json
import re

from services.llm_client import llm_json

JD_SKILLS_PROMPT = """从JD提取技能要求，返回JSON。

示例输入：
数据运营实习生
职责：负责用户行为数据分析，搭建数据看板，进行A/B测试优化转化率。
要求：熟练使用SQL和Excel，了解Python优先，具备数据敏感度。

示例输出：
{{"technical":["SQL","Excel","Python","数据分析","A/B测试","数据看板","用户行为分析"],"soft":["数据敏感度"],"domain":["互联网运营"]}}

规则：
- technical必须是短词（≤8字），是简历技能栏能写的具体工具/方法
- 不要写句子，不要写工作职责
- 从职责推断具体技能："利用AI挖掘数据"→"AI工具","数据挖掘"
- "编写Prompt"→"Prompt Engineering"
- "大语言模型原理"→"LLM"
- "搭建运营管理模型"→"数据建模","用户画像"

分类：technical=具体工具方法, soft=软素质, domain=行业知识

提取以下JD：
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
    (r"AI.*挖掘|利用AI|AI应用|AI智能|AI模型", ["AI工具", "数据挖掘"]),
    (r"数据反馈|数据管理|数据体系|核心指标", ["数据分析", "SQL"]),
    (r"用户增长|渗透率|预约.*规模", ["漏斗分析", "A/B测试"]),
    (r"运营策略|推广活动|发行", ["活动策划", "文档撰写"]),
    (r"用户行为|行为数据|用户模型|用户生命周期", ["用户画像", "数据挖掘"]),
    (r"标准化.*流程|业务流程", ["SOP撰写", "流程管理"]),
    (r"渠道资源|内外渠道", ["渠道运营", "资源整合"]),
    (r"转化效率|策略转化|付费转化", ["转化分析", "A/B测试"]),
    (r"LTV|流失预警|生命周期.*模型", ["数据建模", "用户画像"]),
    (r"内容生产|素材.*生产|宣传素材", ["AIGC", "内容运营"]),
    (r"竞品.*监控|竞品.*分析", ["竞品分析"]),
    (r"Prompt|提示词", ["Prompt Engineering"]),
    (r"大语言模型|LLM|大模型", ["LLM"]),
    (r"触达策略|智能触达|消息推送", ["策略运营", "自动化"]),
    (r"数据看板|报表|可视化", ["数据可视化", "数据看板"]),
    (r"AI.*提效|AI化|AI工具使用", ["AI工具", "Copilot"]),
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
        s = s.strip()
        if not s:
            continue
        s_lower = s.lower()
        # 跳过黑名单命中的
        if any(re.search(p, s_lower) for p in NON_SKILL_PATTERNS):
            continue
        # 跳过太长的（中文>10字、英文多词>20字符 大概率是句子）
        if " " in s:
            if len(s) > 20:
                continue
        elif len(s) > 10:
            continue
        # 跳过含动词的句子片段（"编写XX"、"搭建XX"、"解决XX"）
        if re.search(r"^(编写|搭建|解决|制定|提升|推动|建立|输出|进行|负责)", s):
            continue
        # 跳过含"的"字短语（"大语言模型基本原理和架构"）
        if "的" in s and len(s) > 6:
            continue
        # 跳过含连词的短语（"XX和XX"、"XX与XX"不是技能名）
        if re.search(r"[和与及]", s) and len(s) > 5:
            continue
        filtered.append(s)
    return filtered


def extract_jd_skills(jd_text: str) -> dict:
    """从JD中提取技能标签（LLM + 关键词规则 始终合并）"""
    # 第一层：LLM提取
    llm_skills = {"technical": [], "soft": [], "domain": []}
    try:
        result = llm_json.invoke(JD_SKILLS_PROMPT.format(jd_text=jd_text[:2000]))
        data = json.loads(result.content)
        llm_skills = {
            "technical": _filter_non_skills(data.get("technical", [])),
            "soft": data.get("soft", []),
            "domain": data.get("domain", []),
        }
    except Exception:
        pass

    # 第二层：关键词 + 隐性规则推断（始终执行，补充LLM遗漏）
    rule_skills = _keyword_fallback(jd_text)

    # 合并去重（LLM优先，规则补充）
    merged = {"technical": [], "soft": [], "domain": []}
    for cat in ["technical", "soft", "domain"]:
        seen = set()
        for s in llm_skills.get(cat, []) + rule_skills.get(cat, []):
            s_lower = s.lower().strip()
            if s_lower not in seen:
                seen.add(s_lower)
                merged[cat].append(s)

    # 确保technical不为空
    if not merged["technical"]:
        merged["technical"] = rule_skills.get("technical", [])

    # 修正3B模型分类错误：把明显的软素质词从technical移到soft
    _SOFT_RECLASSIFY = re.compile(
        r"^(逻辑思维|表达能力|沟通能力|自驱力|抗压|责任心|领导力|团队协作|"
        r"团队合作|快速学习|目标导向|时间管理|跨部门协作|产品体验优化|"
        r"技术概念理解|数据敏感度|学习能力|执行力|主动性|耐心|细心)$"
    )
    reclassified = []
    for s in merged["technical"]:
        if _SOFT_RECLASSIFY.match(s.strip()):
            if s not in merged["soft"]:
                merged["soft"].append(s)
            reclassified.append(s)
    for s in reclassified:
        merged["technical"].remove(s)

    # 合并"至少一种"类的或选技能（Python/Java/Go 至少一种 → 单个 "Python/Java/Go"）
    merged["technical"] = _merge_alternative_skills(merged["technical"], jd_text)

    return merged


def _merge_alternative_skills(skills: list[str], jd_text: str) -> list[str]:
    """检测JD中"至少一种/任一"表述，将或选技能合并为单个 A/B/C 项。
    合并后匹配逻辑只需命中其中一个即算匹配。"""
    # 匹配模式：X/Y/Z 至少一种 | X、Y、Z 任选其一 | 熟悉 X 或 Y | X or Y (at least one)
    alt_patterns = [
        # "Python/Java/Go 至少一种"
        r"([\w+#./、]+(?:[/、][\w+#.]+)+)\s*(?:至少一种|任选其一|其中之一|任一)",
        # "至少一种语言" 前面列举的（如 "熟悉 Python/Java/Go 至少一种语言"）
        r"([\w+#.]+(?:[/、][\w+#.]+)+)\s*(?:至少|任选|其一)",
        # "X 或 Y 或 Z"（中文"或"连接）
        r"([\w+#.]+(?:\s*或\s*[\w+#.]+)+)",
    ]

    # 收集所有或选组
    or_groups = []  # 每组是一个 set of skill names (lowercase)
    for pat in alt_patterns:
        for m in re.finditer(pat, jd_text):
            fragment = m.group(1)
            # 拆分出各个技能名
            parts = re.split(r"[/、\s]*或\s*|[/、]+", fragment)
            parts = [p.strip() for p in parts if p.strip()]
            if len(parts) >= 2:
                or_groups.append({p.lower() for p in parts})

    if not or_groups:
        return skills

    # 对每个或选组，找出 skills 中属于该组的项，合并为一个
    result = list(skills)
    for group in or_groups:
        # 找当前 skills 中哪些属于这个或选组
        matched_in_group = []
        for s in result:
            s_lower = s.lower().strip()
            if s_lower in group or any(g in s_lower or s_lower in g for g in group):
                matched_in_group.append(s)
        if len(matched_in_group) >= 2:
            # 合并为 "A/B/C" 形式，从 result 中移除原始项
            merged_label = "/".join(matched_in_group)
            for s in matched_in_group:
                if s in result:
                    result.remove(s)
            result.append(merged_label)

    return result


def _keyword_fallback(jd_text: str) -> dict:
    """不依赖LLM的关键词匹配 + 隐性技能推断"""
    text_lower = jd_text.lower()
    result = {"technical": [], "soft": [], "domain": []}

    # 直接关键词匹配
    for category, keywords in SKILL_KEYWORDS.items():
        for kw in keywords:
            kw_lower = kw.lower()
            # 短英文关键词（≤3字符）需要词边界，避免 "R" 匹配任意含r的文本
            if len(kw) <= 3 and kw.isascii() and kw.isalpha():
                if re.search(r"(?<![a-zA-Z])" + re.escape(kw_lower) + r"(?![a-zA-Z])", text_lower):
                    result[category].append(kw)
            elif kw_lower in text_lower:
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

    # ===== 维度二：技能匹配 (50%) — 动态权重 =====
    technical_skills = jd_skills.get("technical", [])
    weights = _compute_skill_weights(technical_skills, jd_text)
    matched = []
    missing = []
    matched_weight = 0.0
    total_weight = sum(weights.values()) if weights else 1.0
    for jd_skill in technical_skills:
        if _skill_matches(jd_skill, resume_skills):
            matched.append(jd_skill)
            matched_weight += weights.get(jd_skill, 0.6)
        else:
            missing.append(jd_skill)
    skill_rate = matched_weight / total_weight if total_weight > 0 else 0.0

    # ===== 维度三：经验/项目相关性 (30%) =====
    exp_result = _match_experience(resume_data, jd_text)

    # ===== 加权综合 =====
    overall = round(
        edu_result["score"] * 0.2 + skill_rate * 0.5 + exp_result["score"] * 0.3, 3
    )

    return {
        "match_rate": round(overall * 100, 1),
        "dimension_weights": {"education": 0.2, "skills": 0.5, "experience": 0.3},
        "dimensions": {
            "education": edu_result,
            "skills": {
                "matched": matched, "missing": missing,
                "rate": round(skill_rate * 100, 1),
                "weights": {s: round(w, 2) for s, w in weights.items()},
            },
            "experience": exp_result,
        },
        "jd_skills": jd_skills,
        "soft_requirements": jd_skills.get("soft", []),
        "domain_requirements": jd_skills.get("domain", []),
        # 兼容前端旧字段
        "matched": matched,
        "missing": missing,
    }


# ===== 技能动态权重 =====

# JD中熟练度关键词 → 权重
_PROFICIENCY_PATTERNS = [
    (r"熟练|精通|熟悉|丰富.*经验|深入", 1.0),
    (r"能够|掌握|具备|有.*经验|实际.*案例", 0.7),
    (r"了解|知道|优先|加分|prefer", 0.4),
]

# 具体工具/语言名（高专业度）
_SPECIFIC_SKILL_PATTERN = re.compile(
    r"^(Python|Java|SQL|Go|C\+\+|JavaScript|TypeScript|Rust|React|Vue|"
    r"FastAPI|Django|Flask|Spring|Docker|K8s|Linux|Git|MySQL|Redis|"
    r"MongoDB|PyTorch|TensorFlow|LangChain|Ollama|Figma|Excel|Tableau|"
    r"Spark|Kafka|Node\.js|Webpack|Vite|Flutter|Android|iOS|"
    r"Copilot|ChatGPT|Midjourney|Stable Diffusion|"
    r"Prompt Engineering|A/B测试|SEO|SEM|ETL|CI/CD|"
    r"pandas|numpy|scikit-learn|OpenCV|YOLO)$",
    re.IGNORECASE
)

# 笼统/通用技能（低专业度）
_GENERIC_SKILLS = {
    "ai工具", "数据分析", "数据挖掘", "数据建模", "用户画像",
    "内容运营", "策略运营", "活动策划", "文档撰写", "竞品分析",
    "转化分析", "自动化", "数据可视化", "数据看板", "漏斗分析",
    "sop撰写", "流程管理", "渠道运营", "资源整合", "aigc",
}


def _compute_skill_weights(skills: list[str], jd_text: str) -> dict[str, float]:
    """为每个JD技能计算动态权重 = 熟练度权重 × 专业度权重"""
    weights = {}
    for skill in skills:
        # 1. 熟练度权重：在JD中找该技能附近的熟练度关键词
        prof_weight = _get_proficiency_weight(skill, jd_text)
        # 2. 专业度权重：具体工具 > 方法论 > 笼统类别
        spec_weight = _get_specificity_weight(skill)
        weights[skill] = round(prof_weight * spec_weight, 3)
    return weights


def _get_proficiency_weight(skill: str, jd_text: str) -> float:
    """从JD文本中找技能附近的熟练度描述"""
    skill_lower = skill.lower()
    # 在JD中找包含该技能的句子/片段
    # 取技能名前后40字符作为上下文
    idx = jd_text.lower().find(skill_lower)
    if idx == -1:
        # 尝试模糊匹配（技能名的核心部分）
        core = re.sub(r"[/()（）\s]", "", skill_lower)
        if len(core) >= 2:
            idx = jd_text.lower().find(core[:min(6, len(core))])
    if idx == -1:
        return 0.6  # 默认中等

    context = jd_text[max(0, idx - 40):idx + len(skill) + 40]
    for pattern, weight in _PROFICIENCY_PATTERNS:
        if re.search(pattern, context):
            return weight
    return 0.6


def _get_specificity_weight(skill: str) -> float:
    """判断技能的专业度：具体工具=1.0, 方法论=0.8, 笼统类别=0.6"""
    # 具体工具/语言名
    if _SPECIFIC_SKILL_PATTERN.match(skill):
        return 1.0
    # 笼统/通用类别
    if skill.lower() in _GENERIC_SKILLS:
        return 0.6
    # 其他（方法论、中等具体度）
    return 0.8


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
    """经验/项目相关性维度：三层评估"""
    experiences = resume_data.get("experiences", [])
    projects = resume_data.get("projects", [])
    details = []
    score_parts = []

    # ===== 第一层：JD是否要求实习/项目经验，候选人是否有 =====
    jd_wants_internship = bool(re.search(r"实习|intern|实践经[历验]", jd_text, re.IGNORECASE))
    jd_wants_projects = bool(re.search(r"项目经[历验]|项目经验|project", jd_text, re.IGNORECASE))

    has_internship = len(experiences) > 0
    has_projects = len(projects) > 0

    if jd_wants_internship or jd_wants_projects:
        if jd_wants_internship and has_internship:
            score_parts.append(1.0)
            details.append(f"要求实习经历，简历有{len(experiences)}段实习")
        elif jd_wants_internship and not has_internship:
            score_parts.append(0.2)
            details.append("要求实习经历，简历无实习")
        if jd_wants_projects and has_projects:
            score_parts.append(1.0)
            details.append(f"要求项目经验，简历有{len(projects)}个项目")
        elif jd_wants_projects and not has_projects:
            score_parts.append(0.2)
            details.append("要求项目经验，简历无项目")
    else:
        # JD没明确要求，但有实习/项目仍加分
        if has_internship or has_projects:
            score_parts.append(0.8)
            details.append(f"JD未明确要求，简历有{len(experiences)}段实习+{len(projects)}个项目")
        else:
            score_parts.append(0.4)
            details.append("JD未明确要求，简历也无实习/项目")

    # ===== 第二层：JD职责关键词 vs 简历经历描述 =====
    # 从JD提取职责/业务关键词（动态提取，非写死列表）
    jd_keywords = set()
    # 通用行业/职能词
    biz_patterns = [
        r"游戏", r"运营", r"发行", r"电商", r"金融", r"教育",
        r"数据", r"AI", r"用户", r"产品", r"增长", r"营销",
        r"后端", r"前端", r"架构", r"测试", r"安全", r"嵌入式",
        r"设计", r"需求", r"协作", r"管理", r"分析",
    ]
    for p in biz_patterns:
        if re.search(p, jd_text):
            jd_keywords.add(p.strip("r\""))

    # 在简历项目+经历中查找命中
    resume_text = ""
    for proj in projects:
        resume_text += proj.get("name", "") + proj.get("description", "") + proj.get("tech_stack", "")
    for exp in experiences:
        resume_text += exp.get("company", "") + exp.get("position", "") + exp.get("description", "")

    if jd_keywords:
        hits = [kw for kw in jd_keywords if kw.lower() in resume_text.lower()]
        kw_score = len(hits) / len(jd_keywords)
        score_parts.append(kw_score)
        details.append(f"行业关键词命中{len(hits)}/{len(jd_keywords)}: {','.join(hits[:5])}")
    else:
        details.append("JD无明确行业关键词")

    # ===== 第三层：经历数量加分（有实质内容 > 空白） =====
    total_exp = len(experiences) + len(projects)
    if total_exp >= 3:
        score_parts.append(1.0)
    elif total_exp >= 2:
        score_parts.append(0.8)
    elif total_exp >= 1:
        score_parts.append(0.6)
    else:
        score_parts.append(0.2)

    final_score = round(sum(score_parts) / len(score_parts), 2) if score_parts else 0.5
    return {"score": final_score, "detail": "；".join(details), "hits": list(jd_keywords) if jd_keywords else []}


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
