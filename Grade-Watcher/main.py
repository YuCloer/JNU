"""
成绩监控主程序。
用法：
    python main.py login    — 打开浏览器登录（首次或 Cookie 过期时）
    python main.py check    — 手动查一次成绩
    python main.py test     — 发一条测试通知到微信
    python main.py daemon   — 后台持续监控，每 N 分钟检查一次
"""
import json
import sys
import time
import threading
from datetime import datetime

from login import login, reauth
from checker import check_new_grades
from notifier import send_notification, send_raw


def load_config() -> dict:
    with open("config.json", "r", encoding="utf-8") as f:
        return json.load(f)


def cmd_login(config: dict):
    """登录教务系统，保存 Cookie"""
    login(config)
    print("\n[完成] Cookie 已保存，接下来可以运行 check 或 daemon")


def cmd_check(config: dict):
    """手动检查一次新成绩"""
    try:
        new_grades = check_new_grades(config)
        if new_grades:
            for g in new_grades:
                credit = f"({g['_credit']}学分)" if g["_credit"] else ""
                print(f"  -> {g['_course']}: {g['_grade']} {credit}")
        return new_grades
    except PermissionError as e:
        print(f"[错误] {e}")
        return None
    except Exception as e:
        print(f"[错误] 查询失败: {e}")
        return None


def cmd_test(config: dict):
    """发送测试通知"""
    token = config["serverchan_token"]
    if "在这里" in token or not token:
        print("[错误] 请先在 config.json 中填写 Server酱 SendKey")
        return

    ok = send_raw(token, "成绩监控测试", "如果你收到这条消息，说明 Server酱配置正确！")
    if ok:
        print("[测试] 推送成功，请检查微信是否收到消息")
    else:
        print("[测试] 推送失败，请检查 SendKey 是否正确")


def cmd_daemon(config: dict):
    """后台持续监控"""
    interval = config["check_interval_minutes"]
    token = config["serverchan_token"]

    if "在这里" in token or not token:
        print("[错误] 请先在 config.json 中填写 Server酱 SendKey")
        return

    print(f"[监控] 启动！每 {interval} 分钟检查一次成绩")
    print("[监控] 按 Ctrl+C 停止\n")

    # 启动时通知
    send_raw(token, "成绩监控已启动", f"每 {interval} 分钟检查一次，有新成绩会通知你")

    fail_count = 0

    while True:
        now = datetime.now().strftime("%H:%M:%S")

        print(f"\n[{now}] 检查中...")

        try:
            new_grades = check_new_grades(config)

            if new_grades:
                send_notification(token, new_grades)

            fail_count = 0  # 成功则重置

        except PermissionError:
            # EMAP session 过期（约 90 分钟硬性超时），尝试 CAS 静默重认证
            print(f"[{now}] EMAP session 已过期，尝试自动重认证...")
            if reauth(config):
                # 重认证成功，立即重试查询
                print(f"[{now}] 重认证成功，重新查询成绩...")
                try:
                    new_grades = check_new_grades(config)
                    if new_grades:
                        send_notification(token, new_grades)
                    fail_count = 0
                except Exception as e2:
                    print(f"[{now}] 重认证后查询仍失败: {e2}")
            else:
                # CAS 也过期了，需要手动登录
                print(f"[{now}] CAS 也已过期，需要手动登录")
                send_raw(token, "Cookie 已过期", "CAS 和 EMAP 均已过期，请运行 python main.py login 重新登录")
                break

        except Exception as e:
            fail_count += 1
            print(f"[{now}] 查询出错: {e}")

            # 连续失败 5 次才告警，避免网络波动导致刷屏
            if fail_count == 5:
                send_raw(token, "成绩查询连续失败", f"已失败 {fail_count} 次: {e}")

        time.sleep(interval * 60)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    cmd = sys.argv[1].lower()
    config = load_config()

    if cmd == "login":
        cmd_login(config)
    elif cmd == "check":
        cmd_check(config)
    elif cmd == "test":
        cmd_test(config)
    elif cmd == "daemon":
        cmd_daemon(config)
    else:
        print(f"未知命令: {cmd}")
        print(__doc__)


if __name__ == "__main__":
    main()
