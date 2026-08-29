"""AI模拟面试引擎：基于LangGraph状态图的多轮追问面试"""
import json
from typing import TypedDict, Annotated

from langgraph.graph import StateGraph, END

from services.llm_client import llm, llm_json, get_llm_with_temperature

MAX_ROUNDS = 5

# 追问策略模板
FOLLOWUP_STRATEGIES = {
    "depth": "你具体负责了其中的哪个部分？用了什么技术方案？遇到的最大挑战是什么？",
    "pressure": "如果当时方案被否了，你会怎么调整？有没有Plan B？",
    "blind_spot": "我注意到你简历中没有提到{skill}方面的经验，实际有接触过吗？",
    "scenario": "能举一个具体的例子吗？当时你是怎么推动的？结果如何？",
}

QUESTION_GEN_PROMPT = """你是一位资深技术面试官。根据以下信息生成一个面试问题。

候选人简历摘要：
{resume_summary}

岗位描述：
{jd_text}

面试历史（已问过的内容）：
{history}

当前是第 {round_num}/{max_rounds} 轮。

【严格规则】
1. 绝对不要重复已经问过的问题或相同话题，每一轮必须探索不同维度
2. 如果候选人回答敷衍或拒绝回答，换一个全新角度，不要追问同一个点
3. 每轮问题方向必须不同：
   - 第1轮：从简历项目经历切入（开放性）
   - 第2轮：针对岗位核心技术栈深挖（技术深度）
   - 第3轮：压力/假设性问题（"如果...你会怎么做"）
   - 第4轮：简历盲点或JD中未体现的能力（查漏补缺）
   - 第5轮：行为面试/团队协作/职业规划（软性素质）
4. 问题要具体，不要泛泛而谈，结合简历和JD中的具体内容提问

只返回问题本身，不要编号，不要解释。"""

EVALUATE_PROMPT = """你是面试评估专家。请评估候选人的回答质量。

面试问题：{question}
候选人回答：{answer}
岗位要求：{jd_text}

评分等级（只能选一个）：
S=完美（超出预期，有深度有细节有思考）
A=优秀（完整回答，有具体案例）
B=良好（基本回答到位，缺少部分细节）
C=合格（有回答但较浅，缺乏具体性）
D=偏弱（回答过于简略或偏题）
E=较差（几乎没有有效信息）
F=完全不合格（拒绝回答或完全无关）

请返回JSON格式：
{{"grade": "S/A/B/C/D/E/F中的一个字母", "feedback": "一句话点评（50字内）", "keywords_hit": ["命中的关键词"], "keywords_missed": ["缺失的关键词"]}}"""

REPORT_PROMPT = """你是面试评估专家。根据以下完整面试记录生成综合报告。

面试记录：
{rounds_text}

岗位要求：
{jd_text}

综合等级（只能选一个）：
S=完美, A=优秀, B=良好, C=合格, D=偏弱, E=较差, F=完全不合格
C及以上为合格。

请返回JSON格式：
{{
  "total_grade": "S/A/B/C/D/E/F中的一个字母",
  "strengths": ["优势1", "优势2", "优势3"],
  "improvements": ["改进建议1", "改进建议2", "改进建议3"],
  "summary": "100字以内的综合评价"
}}"""


class InterviewState(TypedDict):
    resume_summary: str
    jd_text: str
    round_num: int
    history: list[dict]
    current_question: str
    current_answer: str
    rounds: list[dict]  # 每轮记录 {question, answer, score, feedback}
    report: dict


def build_resume_summary(resume_data: dict) -> str:
    """从结构化简历生成摘要文本"""
    parts = []
    if resume_data.get("name"):
        parts.append(f"姓名：{resume_data['name']}")
    if resume_data.get("education"):
        edu = resume_data["education"][0]
        parts.append(f"学历：{edu.get('school', '')} {edu.get('major', '')}")
    if resume_data.get("skills"):
        parts.append(f"技能：{', '.join(resume_data['skills'][:10])}")
    if resume_data.get("projects"):
        for p in resume_data["projects"][:2]:
            parts.append(f"项目：{p.get('name', '')} - {p.get('description', '')[:80]}")
    return "\n".join(parts) if parts else "简历信息较少"


def _get_temp_for_round(round_num: int) -> float:
    """轮次越多温度越高，增加追问变体"""
    if round_num <= 2:
        return 0.7
    elif round_num == 3:
        return 0.85
    return 1.0


def generate_question(state: InterviewState) -> dict:
    """问题生成节点"""
    history_text = "\n".join(
        f"{'面试官' if m['role'] == 'assistant' else '候选人'}: {m['content']}"
        for m in state["history"]  # 全部历史，避免重复提问
    ) or "（首轮，无历史）"

    prompt = QUESTION_GEN_PROMPT.format(
        resume_summary=state["resume_summary"],
        jd_text=state["jd_text"] or "通用技术岗",
        history=history_text,
        round_num=state["round_num"],
        max_rounds=MAX_ROUNDS,
    )
    temp = _get_temp_for_round(state["round_num"])
    active_llm = llm if temp == 0.7 else get_llm_with_temperature(temp)
    result = active_llm.invoke(prompt)
    return {"current_question": result.content.strip()}


def evaluate_answer(state: InterviewState) -> dict:
    """回答评估节点"""
    prompt = EVALUATE_PROMPT.format(
        question=state["current_question"],
        answer=state["current_answer"],
        jd_text=state["jd_text"] or "通用技术岗",
    )
    try:
        result = llm_json.invoke(prompt)
        eval_data = json.loads(result.content)
    except Exception:
        eval_data = {"grade": "C", "feedback": "回答基本完整", "keywords_hit": [], "keywords_missed": []}

    # 兼容：如果LLM返回了score而非grade，做转换
    grade = eval_data.get("grade", "")
    if not grade and "score" in eval_data:
        score_map = {5: "S", 4: "A", 3: "B", 2: "D", 1: "E"}
        grade = score_map.get(int(eval_data["score"]), "C")
    if grade not in "SABCDEF":
        grade = "C"

    round_record = {
        "round_num": state["round_num"],
        "question": state["current_question"],
        "answer": state["current_answer"],
        "grade": grade,
        "feedback": eval_data.get("feedback", ""),
    }
    new_rounds = state["rounds"] + [round_record]
    new_history = state["history"] + [
        {"role": "assistant", "content": state["current_question"]},
        {"role": "user", "content": state["current_answer"]},
    ]
    return {"rounds": new_rounds, "history": new_history, "round_num": state["round_num"] + 1}


def generate_report(state: InterviewState) -> dict:
    """报告生成节点"""
    rounds_text = "\n".join(
        f"第{r['round_num']}轮 - 问：{r['question']}\n答：{r['answer']}\n等级：{r.get('grade', 'C')}"
        for r in state["rounds"]
    )
    prompt = REPORT_PROMPT.format(rounds_text=rounds_text, jd_text=state["jd_text"] or "通用技术岗")
    try:
        result = llm_json.invoke(prompt)
        report = json.loads(result.content)
        if report.get("total_grade") not in "SABCDEF":
            raise ValueError("无效等级")
    except Exception:
        # 兜底：根据各轮等级取众数
        grades = [r.get("grade", "C") for r in state["rounds"]]
        grade_order = "SABCDEF"
        avg_idx = sum(grade_order.index(g) for g in grades) // len(grades) if grades else 2
        report = {
            "total_grade": grade_order[avg_idx],
            "strengths": ["完成全部面试轮次"],
            "improvements": ["建议补充更多项目细节", "注意量化成果", "建议提前准备岗位相关技术问题的回答思路"],
            "summary": "面试完成，整体表现中等，建议加强项目经验的深度表达。",
        }
    return {"report": report}


def should_continue(state: InterviewState) -> str:
    """条件路由：判断是否继续面试"""
    if state["round_num"] > MAX_ROUNDS:
        return "report"
    return "continue"


def build_interview_graph():
    """构建面试状态图"""
    graph = StateGraph(InterviewState)

    graph.add_node("generate_question", generate_question)
    graph.add_node("evaluate_answer", evaluate_answer)
    graph.add_node("generate_report", generate_report)

    graph.set_entry_point("generate_question")
    graph.add_edge("generate_question", END)  # 生成问题后等待用户输入
    graph.add_edge("evaluate_answer", "generate_question")  # 评估后生成下一题

    # 条件路由在外部控制（因为需要等待用户输入）
    return graph.compile()


# 简化版：逐步调用（因为需要等待用户输入，不适合一次跑完整个图）
def get_next_question(resume_data: dict, jd_text: str, history: list[dict], round_num: int) -> str:
    """获取下一个面试问题（流式用）"""
    state = {
        "resume_summary": build_resume_summary(resume_data),
        "jd_text": jd_text,
        "round_num": round_num,
        "history": history,
        "current_question": "",
        "current_answer": "",
        "rounds": [],
        "report": {},
    }
    result = generate_question(state)
    return result["current_question"]


def evaluate_round(question: str, answer: str, jd_text: str) -> dict:
    """评估单轮回答"""
    state = {
        "resume_summary": "",
        "jd_text": jd_text,
        "round_num": 1,
        "history": [],
        "current_question": question,
        "current_answer": answer,
        "rounds": [],
        "report": {},
    }
    result = evaluate_answer(state)
    return result["rounds"][0] if result["rounds"] else {}


def generate_final_report(rounds: list[dict], jd_text: str) -> dict:
    """生成最终报告"""
    state = {
        "resume_summary": "",
        "jd_text": jd_text,
        "round_num": MAX_ROUNDS + 1,
        "history": [],
        "current_question": "",
        "current_answer": "",
        "rounds": rounds,
        "report": {},
    }
    result = generate_report(state)
    return result["report"]


async def astream_next_question(resume_data: dict, jd_text: str, history: list[dict], round_num: int):
    """异步流式生成面试问题，逐token yield"""
    resume_summary = build_resume_summary(resume_data)
    history_text = "\n".join(
        f"{'面试官' if m['role'] == 'assistant' else '候选人'}: {m['content']}"
        for m in history
    ) or "（首轮，无历史）"

    prompt = QUESTION_GEN_PROMPT.format(
        resume_summary=resume_summary,
        jd_text=jd_text or "通用技术岗",
        history=history_text,
        round_num=round_num,
        max_rounds=MAX_ROUNDS,
    )
    temp = _get_temp_for_round(round_num)
    active_llm = llm if temp == 0.7 else get_llm_with_temperature(temp)
    async for chunk in active_llm.astream(prompt):
        if chunk.content:
            yield chunk.content
