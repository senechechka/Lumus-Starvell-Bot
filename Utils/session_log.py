"""
Буфер логов текущей сессии (сбрасывается при каждом запуске main.py).
"""
from __future__ import annotations

import logging
import os
from datetime import datetime

SESSION_LOG_PATH = "logs/session.log"
_handler: logging.Handler | None = None


class SessionLogHandler(logging.Handler):
    def __init__(self, path: str = SESSION_LOG_PATH):
        super().__init__(level=logging.DEBUG)
        self.path = path
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"=== LSB session started {datetime.now():%d.%m.%Y %H:%M:%S} ===\n")
        self._formatter = logging.Formatter(
            "[%(asctime)s][%(name)s]> %(levelname)s: %(message)s",
            "%d.%m.%Y %H:%M:%S",
        )

    def emit(self, record: logging.LogRecord) -> None:
        try:
            import re

            msg = self._formatter.format(record)
            msg = re.sub(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])", "", msg)
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(msg + "\n")
        except Exception:
            pass


def init_session_log() -> SessionLogHandler:
    global _handler
    if _handler is not None:
        return _handler
    _handler = SessionLogHandler()
    for name in ("main", "StarvellAPI", "LSB", "TGBot"):
        logging.getLogger(name).addHandler(_handler)
    return _handler


def get_session_log_path() -> str:
    return SESSION_LOG_PATH
