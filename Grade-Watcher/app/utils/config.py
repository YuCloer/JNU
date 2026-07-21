import json
from pathlib import Path
from pydantic_settings import BaseSettings

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
LOGS_DIR = PROJECT_ROOT / "logs"


class Settings(BaseSettings):
    serverchan_token: str = ""
    base_url: str = "https://jw.jnu.edu.cn"
    check_interval_minutes: int = 10
    chrome_user_data_dir: str = ""

    @property
    def cookies_path(self) -> Path:
        return DATA_DIR / "cookies.enc"

    @property
    def grades_path(self) -> Path:
        return DATA_DIR / "grades.enc"


def load_settings() -> Settings:
    config_file = PROJECT_ROOT / "config.json"
    if config_file.exists():
        with open(config_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return Settings(**data)
    return Settings()
