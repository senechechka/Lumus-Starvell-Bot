"""
Общие утилиты Lumus Starvell Bot.
"""
from __future__ import annotations

import hashlib
import os
import sys

import bcrypt


def set_console_title(title: str) -> None:
    if sys.platform == "win32":
        os.system(f"title {title}")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def check_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def md5_hash(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()
