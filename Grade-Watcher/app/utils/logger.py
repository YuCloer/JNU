from loguru import logger
from app.utils.config import LOGS_DIR

LOGS_DIR.mkdir(exist_ok=True)

logger.remove()
logger.add(
    LOGS_DIR / "grade_guard_{time:YYYY-MM-DD}.log",
    rotation="1 day",
    retention="7 days",
    encoding="utf-8",
    level="INFO",
)
logger.add(lambda msg: print(msg, end=""), level="INFO", format="{message}")
