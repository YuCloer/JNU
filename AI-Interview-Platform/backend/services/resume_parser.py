"""简历解析服务：分段提取 + 极简prompt + 强后处理"""
import json
import re

from langchain_ollama import ChatOllama
from pydantic import ValidationError

from schemas import ResumeSchema

llm_json = ChatOllama(model="qwen2.5:3b", format="json", temperature=0.1)

# ===== 极简 prompt（3B模型只能跟住短指令）=====

EXTRACT_PROMPT = """从简历文本提取信息，返回JSON。

示例输入：
张三
手机：13800001111 邮箱：zhang@qq.com
教育背景
2021.09-2025.06 武汉大学 计算机科学 本科
技能：Python, SQL, Git
实习经历
2024.07-2024.09 字节跳动 数据分析师实习生
负责用户行为数据看板搭建
项目经历
AI简历分析平台 负责人
技术栈：FastAPI, Vue3, Ollama

示例输出：
{{"name":"张三","email":"zhang@qq.com","phone":"13800001111","education":[{{"school":"武汉大学","major":"计算机科学","degree":"本科","start_date":"2021.09","end_date":"2025.06"}}],"skills":["Python","SQL","Git"],"experiences":[{{"company":"字节跳动","position":"数据分析师实习生","duration":"2024.07-2024.09","description":"负责用户行为数据看板搭建"}}],"projects":[{{"name":"AI简历分析平台","role":"负责人","description":"","tech_stack":"FastAPI, Vue3, Ollama"}}]}}

现在提取以下简历，只返回JSON：
{text}"""


def extract_text_from_file(file_content: bytes, filename: str) -> str:
    """根据文件类型提取纯文本"""
    if filename.endswith(".pdf"):
        return _extract_pdf(file_content)
    elif filename.endswith(".docx"):
        return _extract_docx(file_content)
    else:
        raise ValueError(f"不支持的文件格式: {filename}")


def _extract_pdf(content: bytes) -> str:
    """优先用 pdfplumber（中文支持好），失败退回 PyPDF2"""
    import io
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            text = ""
            for page in pdf.pages:
                text += (page.extract_text() or "") + "\n"
            if text.strip():
                return text
    except ImportError:
        pass
    # fallback
    import PyPDF2
    reader = PyPDF2.PdfReader(io.BytesIO(content))
    text = ""
    for page in reader.pages:
        text += (page.extract_text() or "") + "\n"
    return text


def _extract_docx(content: bytes) -> str:
    import docx
    import io
    doc = docx.Document(io.BytesIO(content))
    paragraphs = []
    for p in doc.paragraphs:
        if p.text.strip():
            paragraphs.append(p.text.strip())
    # 也提取表格内容（很多简历用表格排版）
    for table in doc.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if cells:
                paragraphs.append(" ".join(cells))
    return "\n".join(paragraphs)


def extract_resume(raw_text: str) -> dict:
    """解析简历：LLM提取 → 后处理修正 → 正则兜底"""
    # 预处理：清理多余空白
    cleaned = _preprocess_text(raw_text)

    # 第一层：LLM
    parsed = None
    try:
        result = llm_json.invoke(EXTRACT_PROMPT.format(text=cleaned[:3500]))
        data = json.loads(result.content)
        validated = ResumeSchema(**data)
        parsed = validated.model_dump()
    except Exception:
        pass

    # 第二层：正则兜底
    if parsed is None:
        parsed = {
            "name": "",
            "email": _regex_email(cleaned),
            "phone": _regex_phone(cleaned),
            "education": [],
            "skills": [],
            "experiences": [],
            "projects": [],
        }

    # ===== 强后处理：用正则校验/补全每个字段 =====
    parsed["name"] = _ensure_name(parsed.get("name", ""), cleaned)
    parsed["email"] = parsed.get("email") or _regex_email(cleaned)
    parsed["phone"] = parsed.get("phone") or _regex_phone(cleaned)

    # 教育：LLM没提取到就用正则补
    if not parsed.get("education"):
        parsed["education"] = _regex_education(cleaned)

    # 技能：LLM提取 + 正则补全，统一过滤
    llm_skills = parsed.get("skills") or []
    regex_skills = _regex_skills(cleaned)
    # 合并去重（LLM优先，正则补充）
    merged = list(llm_skills)
    for s in regex_skills:
        if s not in merged:
            merged.append(s)
    parsed["skills"] = _filter_skills(merged)

    # 经历：LLM没提取到就用正则补
    if not parsed.get("experiences"):
        parsed["experiences"] = _regex_experiences(cleaned)

    # 项目：LLM没提取到就用正则补
    if not parsed.get("projects"):
        parsed["projects"] = _regex_projects(cleaned)

    return parsed


def _preprocess_text(text: str) -> str:
    """清理PDF提取的乱序空白和多栏混排"""
    # 去掉连续空格（保留单个）
    text = re.sub(r"[ \t]{2,}", " ", text)
    # 去掉空行堆积
    text = re.sub(r"\n{3,}", "\n\n", text)
    # 清理标题行中的 · 分隔（如 "暨南大学 · 计算机 · 2027 届"）
    # 把这些行保留但标记，不让 · 后面的内容被误认为技能
    text = text.strip()
    return text


# ===== 姓名 =====

_NAME_BLACKLIST = {
    "个人简历", "求职简历", "基本信息", "个人信息", "联系方式", "求职意向",
    "教育背景", "教育经历", "工作经历", "项目经历", "项目经验", "技能特长",
    "自我评价", "个人简介", "简历", "求职信", "应聘", "实习生", "专业技能",
    "个人技能", "在校经历", "荣誉证书", "个人评价", "兴趣爱好",
}


def _ensure_name(llm_name: str, text: str) -> str:
    """校验LLM给的姓名，不对就正则提取"""
    name = (llm_name or "").strip()
    if _is_valid_name(name):
        return name
    return _regex_name(text)


def _is_valid_name(name: str) -> bool:
    """判断是否像合法中文姓名"""
    if not name or len(name) < 2 or len(name) > 4:
        return False
    if name in _NAME_BLACKLIST:
        return False
    if "@" in name or re.search(r"\d", name):
        return False
    # 必须是纯汉字（或·分隔的少数民族名）
    if not re.fullmatch(r"[\u4e00-\u9fff·]{2,6}", name):
        return False
    return True


def _regex_name(text: str) -> str:
    """多策略提取中文姓名"""
    # 策略1：明确标记 "姓名：XX" / "Name: XX"
    m = re.search(r"(?:姓\s*名|Name)[：:\s]+([^\s,，、/]{2,4})", text, re.IGNORECASE)
    if m and _is_valid_name(m.group(1)):
        return m.group(1)

    # 策略2：前5行找纯汉字短词
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    for line in lines[:5]:
        # 去掉分隔符
        clean = re.sub(r"[|｜\-\s\t]", "", line)
        if _is_valid_name(clean):
            return clean
        # 行内可能有 "张三 | 13800001111" 这种
        parts = re.split(r"[|｜\s]{2,}", line)
        for part in parts:
            part = part.strip()
            if _is_valid_name(part):
                return part

    # 策略3：全文找"姓名"附近
    m = re.search(r"[\u4e00-\u9fff]{2,3}(?=\s*[|｜]\s*\d{11})", text)
    if m and _is_valid_name(m.group(0)):
        return m.group(0)

    return ""


def _regex_email(text: str) -> str:
    m = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text)
    return m.group(0) if m else ""


def _regex_phone(text: str) -> str:
    m = re.search(r"1[3-9]\d{9}", text)
    return m.group(0) if m else ""


# ===== 教育经历 =====

def _regex_education(text: str) -> list[dict]:
    """基于段落上下文提取教育经历"""
    results = []
    lines = text.split("\n")
    in_edu = False

    for i, line in enumerate(lines):
        stripped = line.strip()
        # 进入教育段落
        if re.search(r"教育[背经][景历]", stripped) and len(stripped) < 10:
            in_edu = True
            continue
        # 离开教育段落（遇到下一个段落标题）
        if in_edu and re.search(r"(?:工作|实习|项目|技能|自我)[经特]", stripped) and len(stripped) < 10:
            in_edu = False
            continue

        if in_edu or not results:
            # 找大学名
            uni_match = re.search(r"([\u4e00-\u9fff]+(?:大学|学院))", stripped)
            if not uni_match:
                uni_match = re.search(r"([A-Za-z\s]+(?:University|College|Institute))", stripped)
            if uni_match:
                school = uni_match.group(1)
                # 同行提取其他信息
                degree_m = re.search(r"(博士|硕士|研究生|本科|学士|大专|专科)", stripped)
                major_m = re.search(r"(?:专业[：:\s]*)?([\u4e00-\u9fff]{2,10}(?:工程|学|技术|管理|设计|科学))", stripped)
                dates = re.findall(r"(20\d{2})[./\-年](\d{1,2})", stripped)
                start_date = f"{dates[0][0]}.{dates[0][1].zfill(2)}" if len(dates) >= 1 else ""
                end_date = f"{dates[1][0]}.{dates[1][1].zfill(2)}" if len(dates) >= 2 else ""

                # 如果同行没找到专业，看下一行
                major = ""
                if major_m:
                    major = major_m.group(1)
                elif i + 1 < len(lines):
                    next_l = lines[i + 1].strip()
                    major_m2 = re.search(r"([\u4e00-\u9fff]{2,10}(?:工程|学|技术|管理|设计|科学))", next_l)
                    if major_m2:
                        major = major_m2.group(1)

                results.append({
                    "school": school,
                    "major": major,
                    "degree": degree_m.group(1) if degree_m else "",
                    "start_date": start_date,
                    "end_date": end_date,
                })

    # 如果段落式没找到，全文扫描大学名
    if not results:
        for m in re.finditer(r"([\u4e00-\u9fff]+(?:大学|学院))", text):
            school = m.group(1)
            # 取大学名前后50字符作为上下文
            ctx = text[max(0, m.start() - 30):m.end() + 50]
            degree_m = re.search(r"(博士|硕士|研究生|本科|学士|大专|专科)", ctx)
            major_m = re.search(r"([\u4e00-\u9fff]{2,10}(?:工程|学|技术|管理|设计|科学))", ctx)
            dates = re.findall(r"(20\d{2})[./\-年](\d{1,2})", ctx)
            results.append({
                "school": school,
                "major": major_m.group(1) if major_m else "",
                "degree": degree_m.group(1) if degree_m else "",
                "start_date": f"{dates[0][0]}.{dates[0][1].zfill(2)}" if len(dates) >= 1 else "",
                "end_date": f"{dates[1][0]}.{dates[1][1].zfill(2)}" if len(dates) >= 2 else "",
            })
            if len(results) >= 3:
                break

    return results


# ===== 工作/实习经历 =====

_SECTION_HEADERS = re.compile(
    r"^(?:工作经[历验]|实习经[历验]|工作/实习|实践经[历验]|校园经[历验])$",
)


def _regex_experiences(text: str) -> list[dict]:
    """提取工作/实习经历"""
    results = []
    lines = text.split("\n")
    in_section = False
    current = None

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # 进入经历段落
        if _SECTION_HEADERS.match(stripped):
            in_section = True
            continue
        # 离开（遇到下一个段落标题）
        if in_section and re.match(r"^(?:教育|项目|技能|自我|荣誉)", stripped) and len(stripped) < 10:
            in_section = False
            if current:
                results.append(current)
                current = None
            continue

        if not in_section:
            continue

        # 检测公司行（含公司关键词或含日期范围）
        has_date = re.search(r"20\d{2}[./\-]\d{1,2}", stripped)
        has_company = any(kw in stripped for kw in [
            "公司", "集团", "科技", "网络", "传媒", "有限", "工作室",
            "Co.", "Ltd", "Inc", "Corp",
        ])

        if has_company or (has_date and len(stripped) < 40):
            if current:
                results.append(current)
            # 提取日期
            duration = ""
            dur_m = re.search(
                r"(20\d{2}[./\-]\d{1,2}\s*[-–—~至]\s*(?:20\d{2}[./\-]\d{1,2}|至今|今))",
                stripped
            )
            if dur_m:
                duration = dur_m.group(1)
            company = stripped.replace(duration, "").strip(" |｜-—·")
            current = {"company": company[:30], "position": "", "duration": duration, "description": ""}
        elif current:
            # 第二行通常是职位
            if not current["position"] and len(stripped) < 25:
                current["position"] = stripped
            else:
                # 后续是描述
                if current["description"]:
                    current["description"] += "；" + stripped[:60]
                else:
                    current["description"] = stripped[:80]

    if current:
        results.append(current)
    return results[:5]


# ===== 项目经历 =====

def _regex_projects(text: str) -> list[dict]:
    """提取项目经历"""
    results = []
    lines = text.split("\n")
    in_section = False
    current = None

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        if re.match(r"^项目[经]?[历验]?$", stripped):
            in_section = True
            continue
        if in_section and re.match(r"^(?:教育|工作|实习|技能|自我|荣誉)", stripped) and len(stripped) < 10:
            in_section = False
            if current:
                results.append(current)
                current = None
            continue

        if not in_section:
            continue

        # 技术栈行
        tech_m = re.search(r"(?:技术栈|Tech|使用技术|开发工具)[：:\s]*(.+)", stripped, re.IGNORECASE)
        if tech_m and current:
            current["tech_stack"] = tech_m.group(1).strip()[:80]
            continue

        # 角色行
        role_m = re.search(r"(?:角色|担任|职位)[：:\s]*(.+)", stripped)
        if role_m and current:
            current["role"] = role_m.group(1).strip()[:15]
            continue

        # 新项目标题（短行，不以标点开头）
        if len(stripped) < 30 and not stripped.startswith(("-", "·", "•", "–", "·")):
            if current:
                results.append(current)
            current = {"name": stripped, "role": "", "description": "", "tech_stack": ""}
        elif current:
            if not current["description"]:
                current["description"] = stripped[:100]

    if current:
        results.append(current)
    return results[:5]


# ===== 技能 =====

_KNOWN_TECHS = [
    "Python", "Java", "JavaScript", "TypeScript", "Go", "C++", "C#", "Rust", "C",
    "Vue", "Vue3", "React", "Angular", "FastAPI", "Flask", "Django", "Spring",
    "MySQL", "Redis", "MongoDB", "PostgreSQL", "SQL", "SQLite",
    "Docker", "Kubernetes", "K8s", "Linux", "Git", "GitHub",
    "HTML", "CSS", "Node.js", "Webpack", "Vite", "Tailwind",
    "PyTorch", "TensorFlow", "LangChain", "LangGraph", "Ollama", "ChromaDB", "Chroma",
    "Figma", "Axure", "Photoshop", "Excel", "PPT", "Word",
    "pandas", "numpy", "Spark", "Hive", "Tableau", "PowerBI",
    "微信小程序", "uni-app", "Flutter", "Android", "iOS",
    "Playwright", "Selenium", "YOLO", "RAG", "Agent", "Vibe Coding",
    "Server酱", "CAS", "Cookie", "API", "CLI",
    "嵌入式", "机器学习", "计算机视觉", "强化学习", "深度学习",
    "NLP", "CV", "LLM", "GPT", "Copilot", "Codex",
]


def _regex_skills(text: str) -> list[str]:
    """从文本中匹配已知技术词 + 技术栈段落提取"""
    found = []
    text_lower = text.lower()

    # 匹配已知技术词（短名用词边界避免误匹配）
    for tech in _KNOWN_TECHS:
        if len(tech) <= 2:
            # 短名（C, Go, CV等）需要词边界
            if re.search(r"(?<![a-zA-Z])" + re.escape(tech.lower()) + r"(?![a-zA-Z])", text_lower):
                found.append(tech)
        else:
            if tech.lower() in text_lower:
                found.append(tech)

    # 提取"技术栈"段落（后续几行都是技能词）
    lines = text.split("\n")
    in_tech_section = False
    tech_section_lines = 0
    for line in lines:
        stripped = line.strip()
        if re.match(r"^技术栈$", stripped) or re.match(r"^(?:技能|技术|Skills)[：:\s]*$", stripped, re.IGNORECASE):
            in_tech_section = True
            tech_section_lines = 0
            continue
        if in_tech_section:
            # 遇到下一个段落标题就停
            if re.match(r"^(?:教育|工作|实习|项目|自我|语言|培训|开源)", stripped) and len(stripped) < 10:
                in_tech_section = False
                continue
            if not stripped:
                continue
            tech_section_lines += 1
            if tech_section_lines > 6:
                in_tech_section = False
                continue
            # 先从行中提取已知多词技术（如 Vibe Coding）
            remaining = stripped
            for tech in _KNOWN_TECHS:
                if " " in tech and tech.lower() in remaining.lower():
                    if tech not in found:
                        found.append(tech)
                    remaining = re.sub(re.escape(tech), " ", remaining, flags=re.IGNORECASE)
            # 再按空格和分隔符切分剩余（技术栈行是空格分隔的）
            items = re.split(r"[,，、/|·\s]+", remaining)
            for item in items:
                item = item.strip()
                if item and len(item) <= 15 and item not in found:
                    found.append(item)

    # 扫描项目技术栈行（含 · 分隔的多个技术词）
    for line in lines:
        stripped = line.strip()
        if "·" in stripped and stripped.count("·") >= 2:
            items = re.split(r"[·]+", stripped)
            tech_count = sum(1 for it in items if it.strip().lower() in [t.lower() for t in _KNOWN_TECHS])
            if tech_count >= 2:  # 至少2个已知技术词才算技术栈行
                for item in items:
                    item = item.strip()
                    if item and len(item) <= 15 and item not in found:
                        found.append(item)

    # 也尝试提取"技能：XXX, YYY"单行格式
    m = re.search(r"(?:技能|Skills)[：:\s]+(.+)", text, re.IGNORECASE)
    if m:
        items = re.split(r"[,，、/|·]+", m.group(1))
        for item in items:
            item = item.strip()
            if item and len(item) <= 15 and item not in found:
                found.append(item)

    return _filter_skills(found)


# 非技能黑名单模式
_SKILL_BLACKLIST_PATTERNS = [
    r"\d{4}",            # 含年份数字（2027届、2022.07等）
    r"^[‒\-–—~·•]+$",   # 纯分隔符
    r"大学|学院|University",  # 校名
    r"本科|硕士|博士|大专|学士",  # 学历
    r"中国|法国|美国|英国|德国",  # 国家名
    r"GPA|绩点",         # 成绩
    r"年龄|岁",          # 年龄
    r"邮箱|电话|手机",    # 联系方式标签
    r"至今|⾄今",        # 时间词
    r"课程|学[年分期]",   # 学术词
    r"提供|负责|覆盖|沟通|编制|协助|优化|推进|定位|安装|调试",  # 动词（句子碎片）
    r"团队|科研|国际|一线|⼀线",  # 描述词
    r"故障|排查|⼯单|响应|解决时间",  # 工作描述
    r"运营维护|技术支持|技术⽀持",  # 岗位描述
]

# 已知的中文技术词白名单（纯汉字但确实是技能）
_CHINESE_TECH_WHITELIST = {
    "嵌入式", "嵌⼊式", "机器学习", "计算机视觉", "强化学习", "深度学习",
    "自然语言处理", "数据分析", "数据挖掘", "微信小程序", "人工智能",
    "操作系统", "计算机网络", "数据库", "算法", "前端", "后端",
}

# 非技术的常见英文短词（不应作为技能）
_NON_TECH_ENGLISH = {
    "it", "service", "desk", "the", "and", "for", "with", "from",
    "this", "that", "have", "has", "was", "were", "are", "been",
    "can", "will", "would", "could", "should", "may", "might",
    "not", "but", "or", "if", "then", "than", "so", "as", "at",
    "in", "on", "to", "of", "by", "up", "out", "no", "yes",
    "all", "any", "each", "every", "both", "few", "more", "most",
    "other", "some", "such", "only", "own", "same", "too", "very",
    "just", "also", "now", "here", "there", "when", "where", "how",
    "what", "which", "who", "whom", "why", "because", "about",
    "into", "through", "during", "before", "after", "above", "below",
    "between", "under", "over", "again", "further", "once",
}


def _filter_skills(skills: list[str]) -> list[str]:
    """白名单式过滤：只保留看起来像技术/工具名的项"""
    known_lower = {t.lower() for t in _KNOWN_TECHS}
    result = []
    for s in skills:
        s = s.strip().strip("·•-–— ")
        if not s or len(s) < 1 or len(s) > 20:
            continue
        # 黑名单正则
        if any(re.search(p, s) for p in _SKILL_BLACKLIST_PATTERNS):
            continue
        # 已知技术词直接通过
        if s.lower() in known_lower:
            if s not in result:
                result.append(s)
            continue
        # 中文技术词白名单
        if s in _CHINESE_TECH_WHITELIST:
            if s not in result:
                result.append(s)
            continue
        # 纯汉字：只允许2-4字且在白名单中，否则拒绝
        if re.fullmatch(r"[\u4e00-\u9fff\u3400-\u4dbf]+", s):
            continue  # 不在白名单的纯汉字一律拒绝
        # 英文短词黑名单
        if s.lower() in _NON_TECH_ENGLISH:
            continue
        # 纯英文/数字/符号：必须看起来像技术词
        # 技术词特征：含大写字母、含数字、含特殊字符(+/#/.)、或<=10字符的英文
        if re.fullmatch(r"[a-zA-Z0-9+#./\- ]+", s):
            # 单个常见英文单词（非技术）拒绝
            if re.fullmatch(r"[a-zA-Z]+", s) and len(s) <= 6 and s.lower() in _NON_TECH_ENGLISH:
                continue
            # 看起来像技术词（含大写/数字/特殊字符，或短英文）
            if s not in result:
                result.append(s)
            continue
        # 其他情况（混合中英文等）：只保留短的
        if len(s) <= 8 and s not in result:
            result.append(s)
    return result
