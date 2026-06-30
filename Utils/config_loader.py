"""
Загрузка и валидация конфигурационных .txt файлов.
"""
from __future__ import annotations

import json
import os
from configparser import ConfigParser
from typing import Any

from Utils.exceptions import ConfigParseError

CONFIG_DIR = "configs"
MAIN_CONFIG = f"{CONFIG_DIR}/_main.txt"
AUTO_RESPONSE_CONFIG = f"{CONFIG_DIR}/auto_response.txt"
AUTO_DELIVERY_CONFIG = f"{CONFIG_DIR}/auto_delivery.txt"
COMMANDS_CONFIG = f"{CONFIG_DIR}/commands.txt"

REQUIRED_MAIN_SECTIONS = ("Starvell", "Telegram", "Notifications", "Global", "Other")


def _parser() -> ConfigParser:
    config = ConfigParser(delimiters=(":",), interpolation=None)
    config.optionxform = str
    return config


def load_config(path: str) -> ConfigParser:
    if not os.path.exists(path):
        raise ConfigParseError(f"Файл конфигурации не найден: {path}")
    config = _parser()
    try:
        with open(path, encoding="utf-8") as f:
            config.read_file(f)
    except Exception as e:
        raise ConfigParseError(f"Ошибка чтения {path}: {e}") from e
    return config


def save_config(path: str, config: ConfigParser) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        config.write(f)


def load_main_config(path: str = MAIN_CONFIG) -> ConfigParser:
    config = load_config(path)
    for section in REQUIRED_MAIN_SECTIONS:
        if section not in config:
            raise ConfigParseError(f"В {path} отсутствует секция [{section}]")
    return config


def load_auto_response_config(path: str = AUTO_RESPONSE_CONFIG) -> ConfigParser:
    if not os.path.exists(path):
        config = _parser()
        config.add_section("Commands")
        save_config(path, config)
    return load_config(path)


def load_auto_delivery_config(path: str = AUTO_DELIVERY_CONFIG) -> ConfigParser:
    if not os.path.exists(path):
        config = _parser()
        config.add_section("Lots")
        save_config(path, config)
    return load_config(path)


def load_commands_config(path: str = COMMANDS_CONFIG) -> dict[str, dict[str, Any]]:
    if not os.path.exists(path):
        save_commands_config({}, path)
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError as e:
        raise ConfigParseError(f"Ошибка JSON в {path}: {e}") from e
    return {}


def save_commands_config(data: dict[str, dict[str, Any]], path: str = COMMANDS_CONFIG) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_default_main_config() -> dict[str, dict[str, str]]:
    return {
        "Starvell": {
            "session_token": "",
            "sid_cookie": "",
            "my_games_cookie": "",
            "user_agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
        },
        "Telegram": {
            "enabled": "1",
            "token": "",
            "secretKeyHash": "",
            "authorized_users": "[]",
        },
        "Notifications": {
            "new_message": "1",
            "payment": "1",
            "order_confirm": "1",
            "review": "1",
            "bot_start": "1",
            "plugin_message": "1",
        },
        "Global": {
            "auto_bump": "0",
            "auto_response": "0",
            "greeting_text": "Здравствуйте! Чем могу помочь?",
            "order_confirm_text": "Спасибо за заказ, $username!",
            "review_text": "Спасибо за отзыв, $username!",
        },
        "Other": {
            "language": "ru",
            "requests_delay": "4",
            "bump_check_interval": "300",
        },
    }
