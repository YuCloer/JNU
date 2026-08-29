"""AI模拟面试路由：SSE流式对话"""
import asyncio
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from schemas import InterviewRequest
from services.interview_agent import get_next_question, evaluate_round, generate_final_report, astream_next_question, MAX_ROUNDS

router = APIRouter()


def _last_assistant_question(history: list[dict]) -> str:
    """从对话记录中找到最近一次由面试官提出的问题。"""
    for message in reversed(history):
        if message.get("role") == "assistant" and isinstance(message.get("content"), str):
            return message["content"]
    return ""


def _history_with_answer(history: list[dict], answer: str) -> list[dict]:
    """兼容新旧前端：仅在历史中没有本次回答时追加一次。"""
    if history and history[-1].get("role") == "user" and history[-1].get("content") == answer:
        return history
    return [*history, {"role": "user", "content": answer}]


SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


@router.post("/start")
async def start_interview(request: InterviewRequest):
    """开始面试，流式返回第一个问题（真流式：逐token推送）"""
    if not request.resume_data:
        raise HTTPException(status_code=400, detail="缺少简历数据")

    async def stream():
        try:
            async for token in astream_next_question(
                resume_data=request.resume_data,
                jd_text=request.jd_text,
                history=[],
                round_num=1,
            ):
                yield f"data: {json.dumps({'token': token}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'done': True, 'round': 1}, ensure_ascii=False)}\n\n"
        except Exception:
            yield f"data: {json.dumps({'error': '模型服务不可达，请确认 Ollama 已启动'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream", headers=SSE_HEADERS)


@router.post("/chat")
async def interview_chat(request: InterviewRequest):
    """面试对话：接收用户回答，返回评估+下一个问题（流式）"""
    if not request.user_answer.strip():
        raise HTTPException(status_code=400, detail="回答不能为空")
    question = _last_assistant_question(request.history)
    if not question:
        raise HTTPException(status_code=400, detail="缺少待回答的面试问题，请重新开始面试")

    async def stream():
        # 评估当前回答
        eval_result = await asyncio.to_thread(
            evaluate_round,
            question=question,
            answer=request.user_answer,
            jd_text=request.jd_text,
        )
        yield f"data: {json.dumps({'type': 'eval', 'data': eval_result}, ensure_ascii=False)}\n\n"

        # 判断是否结束
        if request.round_num >= MAX_ROUNDS:
            yield f"data: {json.dumps({'type': 'end', 'round': request.round_num}, ensure_ascii=False)}\n\n"
            return

        # 流式生成下一个问题
        new_history = _history_with_answer(request.history, request.user_answer)
        yield f"data: {json.dumps({'type': 'question_start'}, ensure_ascii=False)}\n\n"
        try:
            async for token in astream_next_question(
                resume_data=request.resume_data,
                jd_text=request.jd_text,
                history=new_history,
                round_num=request.round_num + 1,
            ):
                yield f"data: {json.dumps({'type': 'token', 'token': token}, ensure_ascii=False)}\n\n"
        except Exception:
            # 流式失败时降级为同步生成
            question = await asyncio.to_thread(
                get_next_question,
                resume_data=request.resume_data,
                jd_text=request.jd_text,
                history=new_history,
                round_num=request.round_num + 1,
            )
            yield f"data: {json.dumps({'type': 'token', 'token': question}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'question_end', 'round': request.round_num + 1}, ensure_ascii=False)}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream", headers=SSE_HEADERS)


@router.post("/report")
async def get_report(request: InterviewRequest):
    """生成面试综合报告"""
    # 优先复用chat时已评估的轮次，省掉N次LLM调用
    rounds = request.rounds
    if not rounds:
        # 兼容旧前端：从history重新评估
        history = request.history
        for i in range(0, len(history) - 1, 2):
            if history[i]["role"] == "assistant" and history[i + 1]["role"] == "user":
                eval_result = await asyncio.to_thread(
                    evaluate_round,
                    question=history[i]["content"],
                    answer=history[i + 1]["content"],
                    jd_text=request.jd_text,
                )
                rounds.append(eval_result)

    if not rounds:
        raise HTTPException(status_code=400, detail="没有有效的面试记录")

    report = await asyncio.to_thread(generate_final_report, rounds, request.jd_text)
    return {"status": "ok", "report": report, "rounds": rounds}
