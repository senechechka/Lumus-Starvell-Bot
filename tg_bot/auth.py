"""Авторизация в Telegram-боте."""
from __future__ import annotations

import json
import os

from Utils.lsb_tools import check_password

AUTH_FILE = "storage/cache/authorized_users.json"
MAX_ATTEMPTS = 5


class AuthManager:
    def __init__(self, password_hash: str):
        self.password_hash = password_hash
        self.authorized: set[int] = set()
        self.attempts: dict[int, int] = {}
        self._load()

    def _load(self) -> None:
        if os.path.exists(AUTH_FILE):
            try:
                with open(AUTH_FILE, encoding="utf-8") as f:
                    data = json.load(f)
                self.authorized = set(int(x) for x in data)
            except (json.JSONDecodeError, ValueError, TypeError):
                self.authorized = set()

    def save(self) -> None:
        os.makedirs(os.path.dirname(AUTH_FILE), exist_ok=True)
        with open(AUTH_FILE, "w", encoding="utf-8") as f:
            json.dump(list(self.authorized), f)

    def is_authorized(self, user_id: int) -> bool:
        return user_id in self.authorized

    def authorize(self, user_id: int, password: str) -> tuple[bool, str]:
        if self.is_authorized(user_id):
            return True, "ok"
        attempts = self.attempts.get(user_id, 0)
        if attempts >= MAX_ATTEMPTS:
            return False, "Превышено число попыток. Попробуйте позже."
        if check_password(password, self.password_hash):
            self.authorized.add(user_id)
            self.attempts.pop(user_id, None)
            self.save()
            return True, "ok"
        self.attempts[user_id] = attempts + 1
        left = MAX_ATTEMPTS - self.attempts[user_id]
        return False, f"Неверный пароль. Осталось попыток: {left}"
