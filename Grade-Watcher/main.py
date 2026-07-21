"""
JNU-Grade Checker Guard — 暨南大学成绩监控与GPA计算
用法：
    python main.py login        首次登录，保存 Cookie
    python main.py check        单次查询新成绩
    python main.py daemon       守护进程，定时轮询
    python main.py gpa          当前学期 GPA
    python main.py gpa --all    全部学期 GPA
"""
import time
import click
from app.utils.config import load_settings
from app.utils.logger import logger
from app.core.auth import login, reauth
from app.core.fetcher import fetch_grades
from app.core.comparator import check_new_grades
from app.core.gpa import calc_gpa, calc_semester_gpa, calc_year_gpa, get_current_semester, format_gpa_report
from app.notify.serverchan import send_grades, send_raw
from app.notify.toast import show_toast


@click.group()
def cli():
    """暨南大学成绩监控与GPA计算工具"""
    pass


@cli.command(name="login")
def login_cmd():
    """首次登录，保存 Cookie"""
    settings = load_settings()
    login(settings)
    logger.info("登录完成，正在拉取成绩...")
    try:
        grades = fetch_grades(settings)
        check_new_grades(settings, grades)
        semester = get_current_semester(grades)
        sem_gpa = calc_semester_gpa(grades, semester)
        year_gpa = calc_year_gpa(grades, semester)
        total_gpa = calc_gpa(grades)
        click.echo(f"\n  当前学期({semester}) GPA: {sem_gpa:.2f}")
        click.echo(f"  学年 GPA: {year_gpa:.2f}")
        click.echo(f"  总 GPA: {total_gpa:.2f}")
        click.echo(f"  共 {len(grades)} 条成绩已写入基线\n")
    except Exception as e:
        logger.error(f"登录后拉取成绩失败: {e}")


@cli.command()
def check():
    """单次查询新成绩"""
    settings = load_settings()
    try:
        grades = fetch_grades(settings)
        new_grades = check_new_grades(settings, grades)
        if new_grades:
            semester = get_current_semester(grades)
            sem_gpa = calc_semester_gpa(grades, semester)
            year_gpa = calc_year_gpa(grades, semester)
            total_gpa = calc_gpa(grades)
            for g in new_grades:
                click.echo(f"  新: {g['course']} {g['grade']}分 绩点{g['gpa_point']}")
            click.echo(f"  本学期GPA: {sem_gpa:.2f}  学年GPA: {year_gpa:.2f}  总GPA: {total_gpa:.2f}")
            if settings.serverchan_token:
                send_grades(settings.serverchan_token, new_grades, sem_gpa, year_gpa, total_gpa)
                show_toast("新成绩通知", f"{len(new_grades)} 条新成绩已推送")
    except PermissionError:
        logger.error("Session 已过期，请运行 python main.py login")
    except Exception as e:
        logger.error(f"查询失败: {e}")


@cli.command()
def daemon():
    """守护进程，定时轮询"""
    settings = load_settings()
    interval = settings.check_interval_minutes
    token = settings.serverchan_token

    if not token:
        logger.error("请先在 config.json 中填写 serverchan_token")
        return

    logger.info(f"监控启动，每 {interval} 分钟检查一次（Ctrl+C 停止）")
    send_raw(token, "成绩监控已启动", f"每 {interval} 分钟检查一次")

    while True:
        try:
            grades = fetch_grades(settings)
            new_grades = check_new_grades(settings, grades)
            if new_grades:
                semester = get_current_semester(grades)
                sem_gpa = calc_semester_gpa(grades, semester)
                year_gpa = calc_year_gpa(grades, semester)
                total_gpa = calc_gpa(grades)
                send_grades(token, new_grades, sem_gpa, year_gpa, total_gpa)
                show_toast("新成绩通知", f"{len(new_grades)} 条新成绩")

        except PermissionError:
            logger.warning("Session 过期，尝试重认证...")
            if reauth(settings):
                logger.info("重认证成功，下轮继续")
            else:
                logger.error("重认证失败（3次），推送告警并退出")
                send_raw(token, "成绩监控异常", "重认证失败，请运行 python main.py login")
                break

        except Exception as e:
            logger.error(f"本轮查询异常: {e}")

        time.sleep(interval * 60)


@cli.command()
@click.option("--all", "show_all", is_flag=True, help="显示全部学期")
@click.option("--semester", default=None, help="指定学期，如 2025-2026-2")
def gpa(show_all, semester):
    """GPA 计算"""
    settings = load_settings()
    try:
        if semester:
            grades = fetch_grades(settings, semester=semester)
            click.echo(format_gpa_report(grades, semester))
        elif show_all:
            grades = fetch_grades(settings)
            click.echo(format_gpa_report(grades))
        else:
            grades = fetch_grades(settings)
            current = get_current_semester(grades)
            click.echo(format_gpa_report(grades, current))
    except PermissionError:
        logger.error("Session 已过期，请运行 python main.py login")
    except Exception as e:
        logger.error(f"查询失败: {e}")


if __name__ == "__main__":
    cli()
