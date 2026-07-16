"""
成绩查询模块：针对暨大金智 EMAP 教务系统。
用保存的 Cookie 调用成绩 API，解析 JSON 返回，检测新成绩。
"""
import json
import os
import requests
from urllib.parse import quote

# EMAP 成绩 API 路径
GRADE_API = "/jwapp/sys/cjcx/modules/cjcx/xscjcx.do"
# 获取当前学期 API
SEMESTER_API = "/jwapp/sys/cjcx/modules/cjcx/cxdqxnxqhsygxnxq.do"
# EMAP 成绩页面的 Referer
GRADE_PAGE = "/jwapp/sys/cjcx/*default/index.do"


def _build_session(config: dict) -> requests.Session:
    """用保存的 Cookie 构建 requests Session"""
    cookie_file = config["cookie_file"]
    if not os.path.exists(cookie_file):
        raise FileNotFoundError(
            f"Cookie 文件不存在: {cookie_file}\n请先运行 python main.py login"
        )

    with open(cookie_file, "r", encoding="utf-8") as f:
        cookies = json.load(f)

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "X-Requested-With": "XMLHttpRequest",
    })

    base = config["base_url"].rstrip("/")
    session.headers["Referer"] = f"{base}{GRADE_PAGE}"

    for c in cookies:
        session.cookies.set(c["name"], c["value"], domain=c.get("domain", ""))

    return session


def _check_response(resp: requests.Response):
    """统一检查响应：Cookie 过期 / 状态码 / 非 JSON"""
    if resp.status_code in (301, 302):
        location = resp.headers.get("Location", "")
        if "login" in location.lower() or "sso" in location.lower() or "auth" in location.lower():
            raise PermissionError("Cookie 已过期，请重新运行 python main.py login")

    if resp.status_code != 200:
        raise RuntimeError(f"API 返回 HTTP {resp.status_code}")

    text = resp.text.strip()
    if text.startswith("<!") or text.startswith("<html"):
        raise PermissionError("Cookie 已过期（返回了 HTML 登录页），请重新运行 python main.py login")


def _get_semester_codes(session: requests.Session, base: str) -> list[str]:
    """调用学期 API 获取当前学年学期代码列表（如 2025-2026-1, 2025-2026-2）"""
    url = f"{base}{SEMESTER_API}"
    resp = session.post(url, data={}, timeout=60, allow_redirects=False)
    _check_response(resp)

    data = resp.json()
    rows = data.get("datas", {}).get("cxdqxnxqhsygxnxq", {}).get("rows", [])
    codes = [r["XNXQDM"] for r in rows if "XNXQDM" in r]

    if not codes:
        raise RuntimeError("无法获取学期信息，请检查 Cookie 是否有效")

    # 只查最近一个学期（列表末尾 = 当前学期）
    return [codes[-1]]


def _build_query_data(semester_codes: list[str]) -> str:
    """
    构建 EMAP 成绩查询的 POST body。
    querySetting 是 JSON 数组，指定查询条件（学期、有效成绩等）。
    """
    query_setting = [
        {
            "name": "XNXQDM",
            "value": ",".join(semester_codes),
            "linkOpt": "and",
            "builder": "m_value_equal"
        },
        {
            "name": "SFYX",
            "caption": "\u662f\u5426\u6709\u6548",  # 是否有效
            "linkOpt": "AND",
            "builderList": "cbl_m_List",
            "builder": "m_value_equal",
            "value": "1",
            "value_display": "\u662f"  # 是
        },
        {
            "name": "SHOWMAXCJ",
            "caption": "\u663e\u793a\u6700\u9ad8\u6210\u7ee9",  # 显示最高成绩
            "linkOpt": "AND",
            "builderList": "cbl_m_List",
            "builder": "m_value_equal",
            "value": "0",
            "value_display": "\u5426"  # 否
        }
    ]
    return (
        f"querySetting={quote(json.dumps(query_setting))}"
        f"&*order=-XNXQDM%2C-KCH%2C-KXH"
        f"&pageSize=200"
        f"&pageNumber=1"
    )


def _parse_grade_rows(data: dict) -> list[dict]:
    """解析成绩 API 返回的 JSON，提取成绩列表"""
    rows = data.get("datas", {}).get("xscjcx", {}).get("rows", [])
    if not rows:
        return []

    grades = []
    for r in rows:
        entry = dict(r)
        entry["_course"] = r.get("KCM", "")           # 课程名
        entry["_grade"] = str(r.get("ZCJ", ""))        # 总成绩（数值）
        entry["_credit"] = str(r.get("XF", ""))        # 学分
        entry["_semester"] = r.get("XNXQDM", "")       # 学期代码（如 2025-2026-2）
        entry["_semester_display"] = r.get("XNXQDM_DISPLAY", "")  # 学期显示名
        entry["_gpa"] = str(r.get("XFJD", ""))         # 学分绩点
        entry["_exam_date"] = r.get("KSSJ", "")        # 考试时间
        entry["_course_type"] = r.get("KCXZDM_DISPLAY", "")  # 课程性质（必修/选修）

        if entry["_course"]:
            grades.append(entry)

    return grades


def _make_grade_key(grade: dict) -> str:
    """生成成绩唯一标识，用于去重和对比"""
    return f"{grade['_course']}|{grade['_grade']}|{grade['_semester']}"


def fetch_grades(config: dict) -> list[dict]:
    """
    获取当前学期所有成绩。
    流程：先查学期代码 → 再用学期代码查成绩。
    Cookie 过期时抛出 PermissionError。
    网络超时自动重试最多 3 次。
    """
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            return _do_fetch_grades(config)
        except PermissionError:
            raise  # Cookie 过期不重试，直接抛出
        except (requests.Timeout, requests.ConnectionError) as e:
            if attempt < max_retries:
                print(f"[成绩] 网络超时，{10}秒后重试 ({attempt}/{max_retries})...")
                import time
                time.sleep(10)
            else:
                raise RuntimeError(f"成绩查询连续 {max_retries} 次超时: {e}")


def _do_fetch_grades(config: dict) -> list[dict]:
    """实际执行成绩查询（不含重试逻辑）"""
    session = _build_session(config)
    base = config["base_url"].rstrip("/")

    # 第一步：获取当前学期代码
    semester_codes = _get_semester_codes(session, base)
    print(f"[成绩] 当前学期: {', '.join(semester_codes)}")

    # 第二步：查询成绩
    url = f"{base}{GRADE_API}"
    post_data = _build_query_data(semester_codes)

    resp = session.post(
        url,
        data=post_data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=60,
        allow_redirects=False
    )
    _check_response(resp)

    try:
        data = resp.json()
    except Exception:
        raise RuntimeError(f"成绩 API 返回非 JSON:\n{resp.text[:500]}")

    grades = _parse_grade_rows(data)

    if not grades:
        debug_file = "debug_response.json"
        with open(debug_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        raise RuntimeError(
            f"未解析到成绩数据，原始响应已保存到 {debug_file}。\n"
            f"请将此文件内容发给我，我来调整解析逻辑。"
        )

    return grades


def load_history(config: dict) -> list[str]:
    """加载历史成绩 key 列表"""
    path = config["grades_file"]
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_history(config: dict, keys: list[str]):
    """保存成绩 key 列表"""
    with open(config["grades_file"], "w", encoding="utf-8") as f:
        json.dump(keys, f, ensure_ascii=False, indent=2)


def check_new_grades(config: dict) -> list[dict]:
    """
    核心方法：检查是否有新成绩。
    返回新成绩列表（每项包含 _course, _grade, _credit, _semester 等）。
    首次运行会把当前所有成绩写入历史，不触发通知。
    """
    grades = fetch_grades(config)
    history_keys = set(load_history(config))

    if not history_keys:
        all_keys = [_make_grade_key(g) for g in grades]
        save_history(config, all_keys)
        print(f"[成绩] 首次运行，已记录当前 {len(grades)} 条成绩作为基线")
        return []

    new_grades = []
    for g in grades:
        key = _make_grade_key(g)
        if key not in history_keys:
            new_grades.append(g)

    if new_grades:
        all_keys = list(history_keys) + [_make_grade_key(g) for g in new_grades]
        save_history(config, all_keys)
        print(f"[成绩] 发现 {len(new_grades)} 条新成绩！")
    else:
        print(f"[成绩] 无新成绩（当前共 {len(grades)} 条）")

    return new_grades
