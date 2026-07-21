"""GPA 计算：绩点由教务系统返回（XFJD），本地只做加权平均"""


def _dedup_best(grades: list[dict]) -> list[dict]:
    """同一门课出现多次（挂科重考/补考）时，只取绩点最高的那条"""
    best = {}
    for g in grades:
        name = g["course"]
        if name not in best or g["gpa_point"] > best[name]["gpa_point"]:
            best[name] = g
    return list(best.values())


def calc_gpa(grades: list[dict]) -> float:
    """GPA = Σ(绩点 × 学分) / Σ(学分)，同一门课只取最高分"""
    deduped = _dedup_best(grades)
    total_points = 0.0
    total_credits = 0.0
    for g in deduped:
        credit = g["credit"]
        point = g["gpa_point"]
        # 挂科(绩点=0)也计入：分子贡献0，分母贡献学分，拉低GPA
        if credit > 0:
            total_points += point * credit
            total_credits += credit
    if total_credits == 0:
        return 0.0
    return round(total_points / total_credits, 2)


def calc_semester_gpa(grades: list[dict], semester: str) -> float:
    """指定学期的 GPA"""
    filtered = [g for g in grades if g["semester"] == semester]
    return calc_gpa(filtered)


def calc_year_gpa(grades: list[dict], semester: str) -> float:
    """
    学年绩点：第一学期时等于学期绩点，第二学期时等于两学期合计。
    学期代码格式 "2025-2026-2"，末位 1=第一学期 2=第二学期。
    """
    if not semester or "-" not in semester:
        return calc_semester_gpa(grades, semester)
    year_prefix = semester.rsplit("-", 1)[0]  # "2025-2026"
    sem_num = semester.rsplit("-", 1)[1]     # "1" or "2"
    if sem_num == "1":
        return calc_semester_gpa(grades, semester)
    # 第二学期：取该学年两个学期的全部成绩
    year_grades = [g for g in grades if g.get("semester", "").startswith(year_prefix)]
    return calc_gpa(year_grades)


def get_current_semester(grades: list[dict]) -> str:
    """从成绩数据中推断当前学期（取最新的学期代码）"""
    semesters = sorted(set(g["semester"] for g in grades if g["semester"]))
    return semesters[-1] if semesters else ""


def format_gpa_report(grades: list[dict], semester: str | None = None) -> str:
    """格式化输出 GPA 报告"""
    if semester:
        target_grades = [g for g in grades if g["semester"] == semester]
        label = semester
    else:
        target_grades = grades
        label = "全部学期"

    if not target_grades:
        return "无成绩数据"

    target_grades = _dedup_best(target_grades)

    lines = [f"{'='*50}", f"  GPA 报告 — {label}", f"{'='*50}"]
    lines.append(f"{'课程名':<16}{'成绩':>6}{'学分':>6}{'绩点':>6}")
    lines.append("-" * 50)

    for g in sorted(target_grades, key=lambda x: x["semester"]):
        lines.append(
            f"{g['course']:<16}{g['grade']:>6}{g['credit']:>6.1f}{g['gpa_point']:>6.1f}"
        )

    lines.append("-" * 50)
    gpa = calc_gpa(target_grades)
    total_credits = sum(g["credit"] for g in target_grades if g["credit"] > 0)
    lines.append(f"  总学分: {total_credits:.1f}    GPA: {gpa:.2f}")
    lines.append(f"{'='*50}")
    return "\n".join(lines)
