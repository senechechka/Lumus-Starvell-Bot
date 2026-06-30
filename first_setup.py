"""
Первичная настройка Lumus Starvell Bot.
"""
from __future__ import annotations

import os
import time
from configparser import ConfigParser

import telebot
from colorama import Fore, Style

from Utils.config_loader import (
    AUTO_DELIVERY_CONFIG,
    AUTO_RESPONSE_CONFIG,
    COMMANDS_CONFIG,
    get_default_main_config,
    save_config,
)
from Utils.lsb_tools import hash_password
from Utils.logo import ensure_logo_assets


def create_config_obj(settings: dict) -> ConfigParser:
    config = ConfigParser(delimiters=(":",), interpolation=None)
    config.optionxform = str
    config.read_dict(settings)
    return config


def create_empty_configs() -> None:
    os.makedirs("configs", exist_ok=True)
    for path in (AUTO_RESPONSE_CONFIG, AUTO_DELIVERY_CONFIG):
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as f:
                f.write("[Commands]\n" if "response" in path else "[Lots]\n")
    if not os.path.exists(COMMANDS_CONFIG):
        with open(COMMANDS_CONFIG, "w", encoding="utf-8") as f:
            f.write("{}\n")


def validate_password(password: str) -> bool:
    return (
        len(password) >= 8
        and password.lower() != password
        and password.upper() != password
        and any(c.isdigit() for c in password)
    )


def validate_session_token(token: str) -> bool:
    token = token.strip()
    if len(token) < 16:
        return False
    if "=" in token:
        return "session" in token.lower() or len(token) > 20
    return True


def first_setup() -> None:
    ensure_logo_assets()
    create_empty_configs()
    config = create_config_obj(get_default_main_config())
    sleep_time = 1

    print(f"{Fore.CYAN}{Style.BRIGHT}Привет! Добро пожаловать в Lumus Starvell Bot (LSB)!{Style.RESET_ALL}")
    time.sleep(sleep_time)

    print(
        f"\n{Fore.CYAN}{Style.BRIGHT}Не найден основной конфиг. Проведём первичную настройку.{Style.RESET_ALL}"
    )
    time.sleep(sleep_time)

    print(
        f"\n{Fore.MAGENTA}{Style.BRIGHT}┌── {Fore.CYAN}"
        f"Введите session_token Starvell (cookie «session» из браузера: DevTools → Application → Cookies → starvell.com). "
        f"Можно вставить всю строку cookie или только значение session.{Style.RESET_ALL}"
    )
    while True:
        session_token = input(f"{Fore.MAGENTA}{Style.BRIGHT}└───> {Style.RESET_ALL}").strip()
        if not validate_session_token(session_token):
            print(f"\n{Fore.CYAN}{Style.BRIGHT}Неверный формат session_token. Попробуйте ещё раз.{Style.RESET_ALL}")
            continue
        config.set("Starvell", "session_token", session_token)
        break

    print(
        f"\n{Fore.MAGENTA}{Style.BRIGHT}┌── {Fore.CYAN}"
        f"Опционально: sid cookie (Enter — пропустить).{Style.RESET_ALL}"
    )
    sid = input(f"{Fore.MAGENTA}{Style.BRIGHT}└───> {Style.RESET_ALL}").strip()
    if sid:
        config.set("Starvell", "sid_cookie", sid)

    while True:
        print(
            f"\n{Fore.MAGENTA}{Style.BRIGHT}┌── {Fore.CYAN}"
            f"Введите API-токен Telegram-бота от @BotFather.{Style.RESET_ALL}"
        )
        token = input(f"{Fore.MAGENTA}{Style.BRIGHT}└───> {Style.RESET_ALL}").strip()
        try:
            if not token or not token.split(":")[0].isdigit():
                raise ValueError("Неправильный формат токена")
            bot = telebot.TeleBot(token)
            username = bot.get_me().username
            print(f"\n{Fore.CYAN}Подключение к Telegram успешно: @{username}{Style.RESET_ALL}")
            break
        except Exception as ex:
            print(f"\n{Fore.CYAN}{Style.BRIGHT}Попробуйте ещё раз! ({ex}){Style.RESET_ALL}")
            continue

    while True:
        print(
            f"\n{Fore.MAGENTA}{Style.BRIGHT}┌── {Fore.CYAN}"
            f"Придумайте пароль для доступа к боту (8+ символов, заглавные, строчные, цифра).{Style.RESET_ALL}"
        )
        password = input(f"{Fore.MAGENTA}{Style.BRIGHT}└───> {Style.RESET_ALL}").strip()
        if not validate_password(password):
            print(f"\n{Fore.CYAN}{Style.BRIGHT}Слабый пароль. Попробуйте ещё раз.{Style.RESET_ALL}")
            continue
        break

    config.set("Telegram", "enabled", "1")
    config.set("Telegram", "token", token)
    config.set("Telegram", "secretKeyHash", hash_password(password))

    print(
        f"\n{Fore.CYAN}{Style.BRIGHT}Готово! Сохраняю конфиг и завершаю программу.{Style.RESET_ALL}"
    )
    print(
        f"{Fore.CYAN}{Style.BRIGHT}Запустите Start.bat и напишите боту /start — введите пароль для доступа.{Style.RESET_ALL}"
    )
    save_config("configs/_main.txt", config)
    time.sleep(5)
