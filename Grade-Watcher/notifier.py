"""
通知模块：通过 Server酱 将新成绩推送到微信。
免费版每天最多 5 条，所以多条新成绩会合并为一条消息。
"""
import requests


API_URL = "https://sctapi.ftqq.com/{token}.send"


def _build_title(new_grades: list[dict]) -> str:
    """构建推送标题（免费版只显示标题，把关键信息塞进去）"""
    if len(new_grades) == 1:
        g = new_grades[0]
        gpa = f" 绩点{g['_gpa']}" if g.get("_gpa") and g["_gpa"] != "None" else ""
        return f"新成绩: {g['_course']} {g['_grade']}分{gpa}"
    else:
        names = "\u3001".join(g["_course"] for g in new_grades)
        return f"{len(new_grades)}\u6761\u65b0\u6210\u7ee9: {names}"


def _build_desp(new_grades: list[dict]) -> str:
    """构建推送正文（付费版才会显示，但也写好以备升级）"""
    lines = ["## \u65b0\u6210\u7ee9\u901a\u77e5\n"]
    for g in new_grades:
        credit = f" ({g['_credit']}\u5b66\u5206)" if g["_credit"] and g["_credit"] != "None" else ""
        gpa = f" \u7ee9\u70b9{g['_gpa']}" if g.get("_gpa") and g["_gpa"] != "None" else ""
        semester = f" [{g.get('_semester_display', '') or g['_semester']}]" if g.get("_semester_display") or g["_semester"] else ""
        lines.append(f"- **{g['_course']}**: {g['_grade']}\u5206{credit}{gpa}{semester}")
    return "\n".join(lines)


def send_notification(token: str, new_grades: list[dict]) -> bool:
    """
    推送新成绩到微信。
    返回 True 表示成功，False 表示失败。
    """
    if not new_grades:
        return True

    url = API_URL.format(token=token)
    data = {
        "title": _build_title(new_grades),
        "desp": _build_desp(new_grades),
    }

    try:
        resp = requests.post(url, data=data, timeout=10)
        result = resp.json()

        if result.get("code") == 0:
            print(f"[通知] 推送成功: {data['title']}")
            return True
        else:
            msg = result.get("message", "未知错误")
            print(f"[通知] 推送失败: {msg}")
            return False

    except Exception as e:
        print(f"[通知] 推送异常: {e}")
        return False


def send_raw(token: str, title: str, desp: str = "") -> bool:
    """发送自定义消息（用于测试或错误告警）"""
    url = API_URL.format(token=token)
    data = {"title": title, "desp": desp}
    try:
        resp = requests.post(url, data=data, timeout=10)
        result = resp.json()
        return result.get("code") == 0
    except Exception:
        return False
