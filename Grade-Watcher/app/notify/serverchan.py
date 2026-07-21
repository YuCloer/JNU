"""Server酱推送：多条新成绩合并为一条消息"""
import httpx
from app.utils.logger import logger

API_URL = "https://sctapi.ftqq.com/{token}.send"


def _build_message(new_grades: list[dict], semester_gpa: float, year_gpa: float, total_gpa: float) -> str:
    """
    格式：先罗列所有新出的"课程名(性质) 分数分 绩点X.X"，
    最后追加"本学期绩点X.XX 学年绩点X.XX 总绩点X.XX"
    """
    parts = []
    for g in new_grades:
        ctype = f"({g['course_type']})" if g.get("course_type") else ""
        parts.append(f"{g['course']}{ctype} {g['grade']}分 绩点{g['gpa_point']}")
    parts.append(f"本学期绩点{semester_gpa:.2f} 学年绩点{year_gpa:.2f} 总绩点{total_gpa:.2f}")
    return "新成绩: " + " ".join(parts)


def send_grades(token: str, new_grades: list[dict], semester_gpa: float, year_gpa: float, total_gpa: float) -> bool:
    if not new_grades:
        return True

    title = _build_message(new_grades, semester_gpa, year_gpa, total_gpa)
    # desp 放详细表格（付费版可见）
    desp_lines = ["## 新成绩通知\n"]
    for g in new_grades:
        ctype = f"({g['course_type']})" if g.get("course_type") else ""
        desp_lines.append(f"- **{g['course']}**{ctype}: {g['grade']}分 绩点{g['gpa_point']}")
    desp_lines.append(f"\n本学期绩点 **{semester_gpa:.2f}** 学年绩点 **{year_gpa:.2f}** 总绩点 **{total_gpa:.2f}**")

    try:
        resp = httpx.post(
            API_URL.format(token=token),
            data={"title": title, "desp": "\n".join(desp_lines)},
            timeout=10,
        )
        result = resp.json()
        if result.get("code") == 0:
            logger.warning(f"推送成功: {title[:60]}")
            return True
        logger.error(f"推送失败: {result.get('message', '未知错误')}")
        return False
    except Exception as e:
        logger.error(f"推送异常: {e}")
        return False


def send_raw(token: str, title: str, desp: str = "") -> bool:
    """发送自定义消息（测试/告警）"""
    try:
        resp = httpx.post(
            API_URL.format(token=token),
            data={"title": title, "desp": desp},
            timeout=10,
        )
        return resp.json().get("code") == 0
    except Exception:
        return False
