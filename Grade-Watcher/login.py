"""
登录模块：用 Playwright 打开浏览器，手动完成滑动验证码，保存 Cookie。
针对暨大 CAS 统一身份认证（icas.jnu.edu.cn）优化。
登录后自动抓取页面加载时的 API 请求，保存到 api_capture.json 用于调试。
Cookie 过期后重新跑一次 python main.py login 即可。
"""
import json
import asyncio
from playwright.async_api import async_playwright

# 成绩查询页路径（登录成功后会跳转到这里）
GRADE_PAGE = "/jwapp/sys/cjcx/*default/index.do"


async def do_login(base_url: str, username: str, password: str, cookie_file: str):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        # ---- 网络请求监听：抓取所有 API 调用 ----
        captured = []

        async def on_response(response):
            """监听每个 HTTP 响应，记录 jw.jnu.edu.cn 上的 XHR/API 请求"""
            req = response.request
            url = req.url
            # 只关注教务系统域名的 API 请求（排除静态资源）
            if "jw.jnu.edu.cn" in url and not url.endswith(('.js', '.css', '.png', '.jpg', '.gif', '.ico', '.woff', '.woff2')):
                entry = {
                    "url": url,
                    "method": req.method,
                    "status": response.status,
                    "post_data": req.post_data,
                }
                # 尝试读取响应体（API 返回通常是 JSON）
                try:
                    body = await response.text()
                    if len(body) > 15000:
                        body = body[:15000] + "...(截断)"
                    entry["response"] = body
                except Exception:
                    entry["response"] = "(无法读取响应体)"
                captured.append(entry)

        page.on("response", on_response)

        # 直接打开成绩查询页，未登录会自动跳转到 CAS
        target = f"{base_url.rstrip('/')}{GRADE_PAGE}"
        print(f"[登录] 正在打开成绩查询页面（会跳转到 CAS 登录）...")
        await page.goto(target, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(3)
        print(f"[登录] 当前页面: {page.url}")

        # 尝试自动填写账号密码（暨大 CAS 选择器：input#un / input#pd）
        try:
            # 等输入框出现，最多等 10 秒
            user_input = page.locator('#un')
            await user_input.wait_for(state="visible", timeout=10000)
            pass_input = page.locator('#pd')
            await pass_input.wait_for(state="visible", timeout=5000)

            await user_input.fill(username)
            await pass_input.fill(password)
            print("[登录] 已自动填写账号密码，请完成滑块验证码后点击登录")
        except Exception as e:
            print(f"[登录] 未能自动填写（{e}），请手动输入账号密码和验证码")

        # 等待登录成功：URL 离开 CAS 域名 = 认证通过
        print("[登录] 请在浏览器中完成滑块验证码，然后点击登录按钮")
        print("[登录] 等待登录成功（最长 5 分钟）...")
        try:
            await page.wait_for_url(
                lambda url: "icas.jnu.edu.cn" not in url,
                timeout=300000  # 5 分钟，给足时间
            )
            print(f"[登录] 已通过 CAS 认证，当前: {page.url}")
        except Exception:
            print(f"[登录] 超时，当前页面: {page.url}")
            print("[登录] 如果已登录成功只是没跳转，仍会尝试保存 Cookie...")

        # CAS 通过后可能还在重定向链中，等一下跳到教务系统
        if "jw.jnu.edu.cn" not in page.url:
            print("[登录] 等待跳转到教务系统...")
            try:
                await page.wait_for_url(
                    lambda url: "jw.jnu.edu.cn" in url,
                    timeout=30000
                )
            except Exception:
                print(f"[登录] 跳转未完成，当前: {page.url}")

        # 等用户在浏览器里操作到成绩页面（成绩 API 需要用户交互才会触发）
        print("\n[登录] ========================================")
        print("[登录] 浏览器里应该已经打开了成绩查询页面")
        print("[登录] 请在浏览器中确认成绩数据已加载出来")
        print("[登录] 如果页面还没显示成绩，请在页面上操作（选学期、点查询等）")
        print("[登录] 确认成绩数据已显示后，回到这里按 Enter 继续")
        print("[登录] ========================================\n")

        # 在后台线程中等用户按 Enter，不阻塞 asyncio 事件循环
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, input, ">>> 按 Enter 保存并退出：")

        # 保存所有 Cookie
        cookies = await context.cookies()
        with open(cookie_file, "w", encoding="utf-8") as f:
            json.dump(cookies, f, ensure_ascii=False, indent=2)
        print(f"[登录] 已保存 {len(cookies)} 条 Cookie 到 {cookie_file}")

        cookie_names = [c["name"] for c in cookies]
        print(f"[登录] Cookie 名称: {cookie_names}")
        print(f"[登录] 最终页面: {page.url}")

        # 保存抓取到的 API 请求
        with open("api_capture.json", "w", encoding="utf-8") as f:
            json.dump(captured, f, ensure_ascii=False, indent=2)
        print(f"[登录] 已抓取 {len(captured)} 个 API 请求，保存到 api_capture.json")
        # 打印摘要
        for i, c in enumerate(captured):
            print(f"  [{i}] {c['method']} {c['status']} {c['url'][:120]}")

        try:
            await browser.close()
        except Exception:
            pass


def login(config: dict):
    """同步入口，供 main.py 调用"""
    asyncio.run(do_login(
        base_url=config["base_url"],
        username=config["username"],
        password=config["password"],
        cookie_file=config["cookie_file"],
    ))


async def _do_reauth(base_url: str, cookie_file: str) -> bool:
    """
    静默重新认证：用已保存的 CAS Cookie（CASTGC）走一遍 CAS 重定向链，
    拿到新的 EMAP session。如果 CAS 也过期了则返回 False。
    """
    import os
    if not os.path.exists(cookie_file):
        return False

    with open(cookie_file, "r", encoding="utf-8") as f:
        old_cookies = json.load(f)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()

        # 加载已保存的所有 Cookie（包括 CAS 的 CASTGC）
        await context.add_cookies(old_cookies)

        page = await context.new_page()
        target = f"{base_url.rstrip('/')}{GRADE_PAGE}"

        try:
            await page.goto(target, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(5)

            # 检查是否被踢到 CAS 登录页（需要滑块）
            if "icas.jnu.edu.cn" in page.url and "login" in page.url:
                print("[重认证] CAS session 也已过期，需要手动登录")
                await browser.close()
                return False

            # 如果 URL 已经在教务系统上，等重定向链跑完
            if "jw.jnu.edu.cn" not in page.url:
                try:
                    await page.wait_for_url(
                        lambda url: "jw.jnu.edu.cn" in url,
                        timeout=15000
                    )
                except Exception:
                    print(f"[重认证] 重定向未完成: {page.url}")
                    await browser.close()
                    return False

            await asyncio.sleep(3)

            # 保存新的 Cookie
            new_cookies = await context.cookies()
            with open(cookie_file, "w", encoding="utf-8") as f:
                json.dump(new_cookies, f, ensure_ascii=False, indent=2)
            print(f"[重认证] 成功！已保存 {len(new_cookies)} 条新 Cookie")
            await browser.close()
            return True

        except Exception as e:
            print(f"[重认证] 异常: {e}")
            try:
                await browser.close()
            except Exception:
                pass
            return False


def reauth(config: dict) -> bool:
    """同步入口：尝试用 CAS 静默重新认证。成功返回 True，失败返回 False。"""
    print("[重认证] 尝试用 CAS 静默刷新 session...")
    return asyncio.run(_do_reauth(
        base_url=config["base_url"],
        cookie_file=config["cookie_file"],
    ))
