"""简历解析服务：三层兜底策略（LLM JSON → pydantic校验 → 正则兜底）"""
import json
import re

from langchain_ollama import ChatOllama
from pydantic import ValidationError

from schemas import ResumeSchema

llm_json = ChatOllama(model="qwen2.5:3b", format="json", temperature=0.3)

RESUME_PROMPT = """你是一个专业的简历解析助手。请从以下简历文本中提取结构化信息，严格返回JSON格式。

要求提取的字段：
- name: 姓名
- email: 邮箱
- phone: 手机号
- education: 教育经历数组，每项含 school/major/degree/start_date/end_date
- skills: 技能列表（字符串数组）
- experiences: 工作/实习经历数组，每项含 company/position/duration/description
- projects: 项目经历数组，每项含 name/role/description/tech_stack

如果某字段无法提取，填空字符串或空数组。只返回JSON，不要其他文字。

简历文本：
{text}"""

FALLBACK_SKILLS_PROMPT = """从以下文本中提取所有技术技能关键词，返回JSON格式：{{"skills": ["技能1", "技能2", ...]}}

文本：
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
    import PyPDF2
    import io
    reader = PyPDF2.PdfReader(io.BytesIO(content))
    text = ""
    for page in reader.pages:
        text += page.extract_text() or ""
    return text


def _extract_docx(content: bytes) -> str:
    import docx
    import io
    doc = docx.Document(io.BytesIO(content))
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


def extract_resume(raw_text: str) -> dict:
    """三层兜底解析简历"""
    # 第一层：LLM JSON Mode
    try:
        result = llm_json.invoke(RESUME_PROMPT.format(text=raw_text[:3000]))
        data = json.loads(result.content)
        # 第二层：pydantic 校验
        validated = ResumeSchema(**data)
        return validated.model_dump()
    except (json.JSONDecodeError, ValidationError, Exception):
        pass

    # 第三层：正则兜底
    fallback = {
        "name": _regex_name(raw_text),
        "email": _regex_email(raw_text),
        "phone": _regex_phone(raw_text),
        "education": [],
        "skills": _fallback_skills(raw_text),
        "experiences": [],
        "projects": [],
    }
    return fallback


def _regex_name(text: str) -> str:
    # 尝试匹配"姓名：XXX"模式
    m = re.search(r"姓\s*名[：:]\s*(\S{2,4})", text)
    if m:
        return m.group(1)
    # 取第一行非空文本作为候选
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    return lines[0][:10] if lines else ""


def _regex_email(text: str) -> str:
    m = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text)
    return m.group(0) if m else ""


def _regex_phone(text: str) -> str:
    m = re.search(r"1[3-9]\d{9}", text)
    return m.group(0) if m else ""


def _fallback_skills(text: str) -> list[str]:
    try:
        result = llm_json.invoke(FALLBACK_SKILLS_PROMPT.format(text=text[:2000]))
        data = json.loads(result.content)
        return data.get("skills", [])
    except Exception:
        return []
