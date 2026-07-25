from pydantic import BaseModel, Field
from typing import Optional


# ========== 简历相关 ==========
class EducationItem(BaseModel):
    school: str = ""
    major: str = ""
    degree: str = ""
    start_date: str = ""
    end_date: str = ""


class ExperienceItem(BaseModel):
    company: str = ""
    position: str = ""
    duration: str = ""
    description: str = ""


class ProjectItem(BaseModel):
    name: str = ""
    role: str = ""
    description: str = ""
    tech_stack: str = ""


class ResumeSchema(BaseModel):
    name: str = ""
    email: str = ""
    phone: str = ""
    education: list[EducationItem] = []
    skills: list[str] = []
    languages: list[str] = []
    experiences: list[ExperienceItem] = []
    projects: list[ProjectItem] = []


# ========== 面试相关 ==========
class InterviewRequest(BaseModel):
    resume_data: dict
    jd_text: str = ""
    round_num: int = 1
    history: list[dict] = []  # [{"role": "user"/"assistant", "content": "..."}]
    user_answer: str = ""


class InterviewRound(BaseModel):
    round_num: int
    question: str
    answer: str = ""
    grade: str = "C"  # S/A/B/C/D/E/F
    feedback: str = ""


class InterviewReport(BaseModel):
    total_grade: str = "C"  # S/A/B/C/D/E/F，C及以上合格
    rounds: list[InterviewRound] = []
    strengths: list[str] = []
    improvements: list[str] = []
    summary: str = ""


# ========== JD 匹配 ==========
class JDAnalyzeRequest(BaseModel):
    jd_text: str
    resume_data: dict


class SkillMatch(BaseModel):
    matched: list[str] = []
    missing: list[str] = []
    match_rate: float = 0.0
