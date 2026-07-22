"""CAS 认证：保存 CASTGC 实现静默续期（沿用旧项目 grade-watcher 的成熟方案）

原理：首次登录拿到全部 Cookie（含 CAS 的 CASTGC），加密存盘。
重认证时把 CASTGC 注入新浏览器 context，走 CAS 重定向链自动换取新 EMAP session。
CASTGC 每次使用会自动续期，因此只要 daemon 持续运行就永不过期，实现 7×24h 无人值守。
仅当 CASTGC 真正过期（如长期停机）时才需要重新 login。
"""
import asyncio
from playwright.async_api import async_playwright
from app.utils.config import Settings
from app.utils.crypto import encrypt_json, decrypt_json
from app.utils.logger import logger

GRADE_PAGE = "/jwapp/sys/cjcx/*default/index.do"


async def do_login(settings: Settings):
    """首次登录：打开浏览器，用户手动完成密码+滑块，保存全部 Cookie（含 CASTGC）"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="chrome", headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        target = f"{settings.base_url.rstrip('/')}{GRADE_PAGE}"
        logger.info("正在打开成绩查询页（会跳转 CAS 登录）...")
        await page.goto(target, wait_until="domcontentloaded", timeout=30000)
        await asyncio.sleep(2)

        if "icas.jnu.edu.cn" in page.url:
            logger.info("请在浏览器中输入账号密码并完成滑块验证码（最长等待 5 分钟）")
            try:
                await page.wait_for_url(
                    lambda url: "icas.jnu.edu.cn" not in url, timeout=300000
                )
            except Exception:
                logger.warning("等待超时，尝试继续保存 Cookie...")
        else:
            logger.info("已有有效 session，无需重新登录")

        if "jw.jnu.edu.cn" not in page.url:
            try:
                await page.wait_for_url(
                    lambda url: "jw.jnu.edu.cn" in url, timeout=30000
                )
            except Exception:
                pass

        await asyncio.sleep(3)
        cookies = await context.cookies()
        encrypt_json(cookies, settings.cookies_path)
        logger.info(f"已保存 {len(cookies)} 条 Cookie（含 CASTGC，加密）")
        await browser.close()


async def do_reauth(settings: Settings) -> bool:
    """
    静默重认证：加载已保存的 Cookie（含 CASTGC）注入新 context，
    走 CAS 重定向链自动换取新 EMAP session，全程无需用户干预。
    """
    saved_cookies = decrypt_json(settings.cookies_path)
    if not saved_cookies:
        logger.warning("无已保存的 Cookie，无法静默重认证，请运行 python main.py login")
        return False

    backoff = [30, 60, 90]
    target = f"{settings.base_url.rstrip('/')}{GRADE_PAGE}"

    for attempt, wait in enumerate(backoff):
        browser = None
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(channel="chrome", headless=False)
                context = await browser.new_context()
                # 注入已保存的 Cookie（关键是 CAS 的 CASTGC）
                await context.add_cookies(saved_cookies)
                page = await context.new_page()

                logger.info(f"重认证尝试 {attempt + 1}/3，注入 CASTGC 走 CAS 重定向链...")
                await page.goto(target, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(3)

                # 落到 CAS 登录表单 = CASTGC 过期，静默重认证失败
                if "icas.jnu.edu.cn" in page.url and "login" in page.url:
                    logger.warning("CASTGC 已过期，静默重认证失败，请运行 python main.py login")
                    await browser.close()
                    return False

                # 等重定向链跑完
                if "jw.jnu.edu.cn" not in page.url:
                    try:
                        await page.wait_for_url(
                            lambda url: "jw.jnu.edu.cn" in url, timeout=15000
                        )
                    except Exception:
                        logger.warning(f"重定向未完成: {page.url}")
                        await browser.close()
                        if attempt < 2:
                            logger.info(f"{wait}秒后重试...")
                            await asyncio.sleep(wait)
                        continue

                await asyncio.sleep(2)
                new_cookies = await context.cookies()
                encrypt_json(new_cookies, settings.cookies_path)
                logger.info(f"静默重认证成功，已保存 {len(new_cookies)} 条新 Cookie")
                await browser.close()
                return True

        except Exception as e:
            logger.error(f"重认证异常: {e}")
            if browser is not None:
                try:
                    await browser.close()
                except Exception:
                    pass
            # 网络层错误 ≠ CASTGC 过期，退避后重试
            if attempt < 2:
                logger.info(f"{wait}秒后重试...")
                await asyncio.sleep(wait)

    return False


def login(settings: Settings):
    asyncio.run(do_login(settings))


def reauth(settings: Settings) -> bool:
    return asyncio.run(do_reauth(settings))
