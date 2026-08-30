"""PyCharm-friendly entry point for ScoutXI."""

import os
from pathlib import Path

import uvicorn


def load_local_env() -> None:
    """Load local developer settings without adding a dotenv dependency."""
    env_path = Path(__file__).with_name(".env")
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


if __name__ == "__main__":
    load_local_env()
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
