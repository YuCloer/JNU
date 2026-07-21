"""CAS 认证：Playwright persistent context 复用 Chrome 密码管理器"""
import asyncio
import os
from pathlib import Path
from playwright.async_api import async_playwright
from app.utils.config import Settings
from app.utils.crypto import encrypt_json, decrypt_json
from app.utils.logger import logger

CAS_LOGIN = "https://icas.jnu.edu.cn/cas/login"
GRADE_PAGE = "/jwapp/sys/cjcx/*default/index.do"


def _get_user_data_dir(settings: Settings) -> str:
    if settings.chrome_user_data_dir:
        return settings.chrome_user_data_dir
    # 项目本地独立 profile，不和日常 Chrome 冲突
    from app.utils.config import DATA_DIR
    profile_dir = DATA_DIR / "chrome-profile"
    profile_dir.mkdir(parents=True, exist_ok=True)
    return str(profile_dir)


async def do_login(settings: Settings):
    """首次登录：打开浏览器，用户手动完成滑块，保存 Cookie"""
    user_data_dir = _get_user_data_dir(settings)
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            channel="chrome",
            headless=False,
        )
        page = context.pages[0] if context.pages else await context.new_page()

        target = f"{settings.base_url.rstrip('/')}{GRADE_PAGE}"
        logger.info("正在打开成绩查询页（会跳转 CAS 登录）...")
        await page.goto(target, wait_until="domcontentloaded", timeout=30000)

        # 等 JS 重定向把页面带到 CAS 登录页（或已有 session 直接到成绩页）
        try:
            await page.wait_for_url(
                lambda url: "icas.jnu.edu.cn" in url or "jw.jnu.edu.cn" in url,
                timeout=15000,
            )
        except Exception:
            pass
        await asyncio.sleep(2)

        if "icas.jnu.edu.cn" in page.url:
            # 到了 CAS 登录页，等用户完成滑块+登录
            logger.info("请在浏览器中完成滑块验证码并登录（最长等待 5 分钟）")
            try:
                await page.wait_for_url(
                    lambda url: "icas.jnu.edu.cn" not in url, timeout=300000
                )
            except Exception:
                logger.warning("等待超时，尝试继续保存 Cookie...")
        else:
            logger.info("已有有效 session，无需重新登录")

        # 等跳转到教务系统
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
        logger.info(f"已保存 {len(cookies)} 条 Cookie（加密）")
        await context.close()


async def do_reauth(settings: Settings) -> bool:
    """
    重认证：丢弃旧 context，新建 context 直接导航 CAS 登录页。
    不走教务 URL 的 302 重定向链，规避 2 小时边界 RST 问题。
    """
    user_data_dir = _get_user_data_dir(settings)
    backoff = [30, 60, 90]

    for attempt, wait in enumerate(backoff):
        try:
            async with async_playwright() as p:
                context = await p.chromium.launch_persistent_context(
                    user_data_dir=user_data_dir,
                    channel="chrome",
                    headless=False,
                )
                page = context.pages[0] if context.pages else await context.new_page()

                logger.info(f"重认证尝试 {attempt + 1}/3，导航到 CAS 登录页")
                await page.goto(CAS_LOGIN, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(3)

                # Chrome 密码管理器自动填充，用户只需确认/滑块
                logger.info("请在浏览器中确认登录（滑块验证码）")
                try:
                    await page.wait_for_url(
                        lambda url: "icas.jnu.edu.cn" not in url, timeout=120000
                    )
                except Exception:
                    logger.warning("重认证等待超时")
                    await context.close()
                    if attempt < 2:
                        logger.info(f"{wait}秒后重试...")
                        await asyncio.sleep(wait)
                    continue

                # 导航到成绩页获取 EMAP session
                target = f"{settings.base_url.rstrip('/')}{GRADE_PAGE}"
                await page.goto(target, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(3)

                cookies = await context.cookies()
                encrypt_json(cookies, settings.cookies_path)
                logger.info(f"重认证成功，已保存 {len(cookies)} 条 Cookie")
                await context.close()
                return True

        except Exception as e:
            logger.error(f"重认证异常: {e}")
            if attempt < 2:
                logger.info(f"{wait}秒后重试...")
                await asyncio.sleep(wait)

    return False


def login(settings: Settings):
    asyncio.run(do_login(settings))


def reauth(settings: Settings) -> bool:
    return asyncio.run(do_reauth(settings))
