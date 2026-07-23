"""AI模拟面试引擎：基于LangGraph状态图的多轮追问面试"""
import json
from typing import TypedDict, Annotated

from langchain_ollama import ChatOllama
from langgraph.graph import StateGraph, END

llm = ChatOllama(model="qwen2.5:3b", temperature=0.7)
llm_json = ChatOllama(model="qwen2.5:3b", format="json", temperature=0.3)

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

面试历史：
{history}

当前是第 {round_num}/{max_rounds} 轮。

要求：
- 第1轮：从简历中的项目经历切入，问一个开放性问题
- 第2-4轮：基于上一轮回答做追问（深度/压力/盲点/场景 轮换）
- 第5轮：问一个综合性/行为面试题

只返回问题本身，不要编号，不要解释。"""

EVALUATE_PROMPT = """你是面试评估专家。请评估候选人的回答质量。

面试问题：{question}
候选人回答：{answer}
岗位要求：{jd_text}

请返回JSON格式：
{{"score": 1-5的评分, "feedback": "一句话点评（50字内）", "keywords_hit": ["命中的关键词"], "keywords_missed": ["缺失的关键词"]}}"""

REPORT_PROMPT = """你是面试评估专家。根据以下完整面试记录生成综合报告。

面试记录：
{rounds_text}

岗位要求：
{jd_text}

请返回JSON格式：
{{
  "total_score": 1-5综合评分,
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


def generate_question(state: InterviewState) -> dict:
    """问题生成节点"""
    history_text = "\n".join(
        f"{'面试官' if m['role'] == 'assistant' else '候选人'}: {m['content']}"
        for m in state["history"][-6:]  # 最近3轮对话
    ) or "（首轮，无历史）"

    prompt = QUESTION_GEN_PROMPT.format(
        resume_summary=state["resume_summary"],
        jd_text=state["jd_text"] or "通用技术岗",
        history=history_text,
        round_num=state["round_num"],
        max_rounds=MAX_ROUNDS,
    )
    result = llm.invoke(prompt)
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
        eval_data = {"score": 3.0, "feedback": "回答基本完整", "keywords_hit": [], "keywords_missed": []}

    round_record = {
        "round_num": state["round_num"],
        "question": state["current_question"],
        "answer": state["current_answer"],
        "score": eval_data.get("score", 3.0),
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
        f"第{r['round_num']}轮 - 问：{r['question']}\n答：{r['answer']}\n评分：{r['score']}"
        for r in state["rounds"]
    )
    prompt = REPORT_PROMPT.format(rounds_text=rounds_text, jd_text=state["jd_text"] or "通用技术岗")
    try:
        result = llm_json.invoke(prompt)
        report = json.loads(result.content)
    except Exception:
        scores = [r["score"] for r in state["rounds"]]
        avg = sum(scores) / len(scores) if scores else 3.0
        report = {
            "total_score": round(avg, 1),
            "strengths": ["完成全部面试轮次"],
            "improvements": ["建议补充更多项目细节", "注意量化成果"],
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
