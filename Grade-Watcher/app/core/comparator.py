"""成绩对比去重：基于 课程名|成绩|学期 三元组"""
from app.utils.config import Settings
from app.utils.crypto import encrypt_json, decrypt_json
from app.utils.logger import logger


def _make_key(g: dict) -> str:
    return f"{g['course']}|{g['grade']}|{g['semester']}"


def load_history(settings: Settings) -> set[str]:
    data = decrypt_json(settings.grades_path)
    if data is None:
        return set()
    return set(data)


def check_new_grades(settings: Settings, grades: list[dict]) -> list[dict]:
    """
    对比当前成绩与历史基线，返回新增成绩列表。
    首次运行时写入基线，不触发通知。
    """
    history = load_history(settings)

    if not history:
        all_keys = [_make_key(g) for g in grades]
        encrypt_json(all_keys, settings.grades_path)
        logger.info(f"首次运行，已记录 {len(grades)} 条成绩作为基线")
        return []

    new_grades = [g for g in grades if _make_key(g) not in history]

    if new_grades:
        updated = list(history) + [_make_key(g) for g in new_grades]
        encrypt_json(updated, settings.grades_path)
        logger.warning(f"发现 {len(new_grades)} 条新成绩")
    else:
        logger.info(f"无新成绩（当前共 {len(grades)} 条）")

    return new_grades
