from pydantic import BaseModel, Field


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
    education: list[EducationItem] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    experiences: list[ExperienceItem] = Field(default_factory=list)
    projects: list[ProjectItem] = Field(default_factory=list)


# ========== 面试相关 ==========
class InterviewRequest(BaseModel):
    resume_data: dict
    jd_text: str = Field(default="", max_length=10000)
    round_num: int = Field(default=1, ge=1, le=5)
    history: list[dict] = Field(default_factory=list)  # [{"role": "user"/"assistant", "content": "..."}]
    user_answer: str = Field(default="", max_length=5000)
    rounds: list[dict] = Field(default_factory=list)  # 已评估的轮次（chat时产生），report接口直接复用避免重复LLM调用


class InterviewRound(BaseModel):
    round_num: int
    question: str
    answer: str = ""
    grade: str = "C"  # S/A/B/C/D/E/F
    feedback: str = ""


class InterviewReport(BaseModel):
    total_grade: str = "C"  # S/A/B/C/D/E/F，C及以上合格
    rounds: list[InterviewRound] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    improvements: list[str] = Field(default_factory=list)
    summary: str = ""


# ========== JD 匹配 ==========
class JDAnalyzeRequest(BaseModel):
    jd_text: str = Field(min_length=1, max_length=10000)
    resume_data: dict


class SkillMatch(BaseModel):
    matched: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    match_rate: float = 0.0
