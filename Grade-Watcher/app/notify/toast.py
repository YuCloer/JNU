"""Windows 11 Toast 本地通知（可选补充）"""
from app.utils.logger import logger


def show_toast(title: str, message: str):
    try:
        from win11toast import toast
        toast(title, message)
    except ImportError:
        logger.info("win11toast 未安装，跳过本地通知")
    except Exception as e:
        logger.error(f"Toast 通知失败: {e}")
