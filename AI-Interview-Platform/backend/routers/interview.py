"""AI模拟面试路由：SSE流式对话"""
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from langchain_ollama import ChatOllama

from schemas import InterviewRequest
from services.interview_agent import (
    get_next_question, evaluate_round, generate_final_report,
    build_resume_summary, MAX_ROUNDS,
)

router = APIRouter()
llm = ChatOllama(model="qwen2.5:3b", temperature=0.7)


@router.post("/start")
async def start_interview(request: InterviewRequest):
    """开始面试，返回第一个问题（流式）"""
    if not request.resume_data:
        raise HTTPException(status_code=400, detail="缺少简历数据")

    async def stream():
        question = get_next_question(
            resume_data=request.resume_data,
            jd_text=request.jd_text,
            history=[],
            round_num=1,
        )
        # 逐字流式输出
        for char in question:
            yield f"data: {json.dumps({'token': char}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'done': True, 'round': 1}, ensure_ascii=False)}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.post("/chat")
async def interview_chat(request: InterviewRequest):
    """面试对话：接收用户回答，返回评估+下一个问题（流式）"""
    if not request.user_answer.strip():
        raise HTTPException(status_code=400, detail="回答不能为空")

    async def stream():
        # 评估当前回答
        eval_result = evaluate_round(
            question=request.history[-1]["content"] if request.history else "",
            answer=request.user_answer,
            jd_text=request.jd_text,
        )
        # 先发送评估结果
        yield f"data: {json.dumps({'type': 'eval', 'data': eval_result}, ensure_ascii=False)}\n\n"

        # 判断是否结束
        if request.round_num >= MAX_ROUNDS:
            yield f"data: {json.dumps({'type': 'end', 'round': request.round_num}, ensure_ascii=False)}\n\n"
            return

        # 生成下一个问题
        new_history = request.history + [
            {"role": "user", "content": request.user_answer}
        ]
        question = get_next_question(
            resume_data=request.resume_data,
            jd_text=request.jd_text,
            history=new_history,
            round_num=request.round_num + 1,
        )
        # 流式输出问题
        yield f"data: {json.dumps({'type': 'question_start'}, ensure_ascii=False)}\n\n"
        for char in question:
            yield f"data: {json.dumps({'type': 'token', 'token': char}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'question_end', 'round': request.round_num + 1}, ensure_ascii=False)}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.post("/report")
async def get_report(request: InterviewRequest):
    """生成面试综合报告"""
    # 从history中重建rounds
    rounds = []
    history = request.history
    round_num = 1
    for i in range(0, len(history) - 1, 2):
        if history[i]["role"] == "assistant" and history[i + 1]["role"] == "user":
            eval_result = evaluate_round(
                question=history[i]["content"],
                answer=history[i + 1]["content"],
                jd_text=request.jd_text,
            )
            rounds.append(eval_result)
            round_num += 1

    if not rounds:
        raise HTTPException(status_code=400, detail="没有有效的面试记录")

    report = generate_final_report(rounds, request.jd_text)
    return {"status": "ok", "report": report, "rounds": rounds}
