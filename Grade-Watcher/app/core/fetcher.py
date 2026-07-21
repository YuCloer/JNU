"""成绩抓取：单次 POST 拉取全部学期，不逐学期循环"""
import json
from urllib.parse import quote
import httpx
from app.utils.config import Settings
from app.utils.crypto import decrypt_json
from app.utils.logger import logger

GRADE_API = "/jwapp/sys/cjcx/modules/cjcx/xscjcx.do"
GRADE_PAGE = "/jwapp/sys/cjcx/*default/index.do"


def _build_session(settings: Settings) -> httpx.Client:
    """用加密存储的 Cookie 构建 httpx 客户端"""
    cookies_data = decrypt_json(settings.cookies_path)
    if not cookies_data:
        raise FileNotFoundError("Cookie 不存在，请先运行 python main.py login")

    client = httpx.Client(
        timeout=15,
        follow_redirects=False,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"{settings.base_url.rstrip('/')}{GRADE_PAGE}",
        },
    )
    for c in cookies_data:
        client.cookies.set(c["name"], c["value"], domain=c.get("domain", ""))
    return client


def _build_post_body(semester: str | None = None) -> str:
    """
    构建查询 POST body。
    semester=None 时不传 XNXQDM，返回全部学期成绩。
    """
    query_setting = [
        {
            "name": "SFYX",
            "caption": "\u662f\u5426\u6709\u6548",
            "linkOpt": "AND",
            "builderList": "cbl_m_List",
            "builder": "m_value_equal",
            "value": "1",
            "value_display": "\u662f",
        },
        {
            "name": "SHOWMAXCJ",
            "caption": "\u663e\u793a\u6700\u9ad8\u6210\u7ee9",
            "linkOpt": "AND",
            "builderList": "cbl_m_List",
            "builder": "m_value_equal",
            "value": "0",
            "value_display": "\u5426",
        },
    ]
    if semester:
        query_setting.insert(0, {
            "name": "XNXQDM",
            "value": semester,
            "linkOpt": "and",
            "builder": "m_value_equal",
        })

    return (
        f"querySetting={quote(json.dumps(query_setting))}"
        f"&*order=-XNXQDM%2C-KCH%2C-KXH"
        f"&pageSize=500"
        f"&pageNumber=1"
    )


def _check_response(resp: httpx.Response):
    """检测 session 过期"""
    if resp.status_code in (301, 302):
        location = resp.headers.get("location", "")
        if any(k in location.lower() for k in ("login", "sso", "cas")):
            raise PermissionError("Session 已过期")
    if resp.status_code != 200:
        raise RuntimeError(f"API 返回 HTTP {resp.status_code}")
    text = resp.text.strip()
    if text.startswith("<!") or text.startswith("<html"):
        raise PermissionError("Session 已过期（返回 HTML）")


def _parse_rows(data: dict) -> list[dict]:
    rows = data.get("datas", {}).get("xscjcx", {}).get("rows", [])
    grades = []
    for r in rows:
        course = r.get("KCM", "")
        if not course:
            continue
        grades.append({
            "course": course,
            "grade": str(r.get("ZCJ", "")),
            "credit": float(r.get("XF", 0) or 0),
            "gpa_point": float(r.get("XFJD", 0) or 0),
            "semester": r.get("XNXQDM", ""),
            "semester_display": r.get("XNXQDM_DISPLAY", ""),
            "course_type": r.get("KCXZDM_DISPLAY", ""),
        })
    return grades


def fetch_grades(settings: Settings, semester: str | None = None) -> list[dict]:
    """
    拉取成绩。semester=None 返回全部学期，
    传 "2025-2026-2" 返回单学期，传 "2025-2026-1,2025-2026-2" 返回多学期。
    """
    client = _build_session(settings)
    url = f"{settings.base_url.rstrip('/')}{GRADE_API}"
    body = _build_post_body(semester)

    try:
        resp = client.post(
            url,
            content=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        _check_response(resp)
        data = resp.json()
    finally:
        client.close()

    grades = _parse_rows(data)
    if not grades:
        logger.warning("未解析到成绩数据，可能 API 结构变更")
    return grades
