"""
Форматтеры логов Lumus Starvell Bot.
"""
from __future__ import annotations

import logging
import logging.handlers
import re

from colorama import Fore, Style

# Приглушённые цвета уровней
LOG_COLORS = {
    logging.DEBUG: Fore.LIGHTBLACK_EX,
    logging.INFO: Fore.LIGHTGREEN_EX,
    logging.WARNING: Fore.LIGHTYELLOW_EX,
    logging.ERROR: Fore.LIGHTRED_EX,
    logging.CRITICAL: Fore.LIGHTRED_EX + Style.BRIGHT,
}

EVENT_COLORS = {
    "client": Fore.LIGHTCYAN_EX,
    "seller": Fore.LIGHTBLUE_EX,
    "success": Fore.LIGHTGREEN_EX,
    "timer": Fore.LIGHTYELLOW_EX,
    "plugin": Fore.LIGHTMAGENTA_EX,
    "error": Fore.LIGHTRED_EX,
    "system": Fore.WHITE,
}

CLI_LOG_FORMAT = (
    f"{Fore.LIGHTBLACK_EX}[%(asctime)s]{Style.RESET_ALL}"
    f" {Fore.LIGHTBLACK_EX}>{Style.RESET_ALL}"
    f" $RESET%(levelname).1s:{Style.RESET_ALL} %(message)s"
)
CLI_TIME_FORMAT = "%d-%m-%Y %H:%M:%S"

FILE_LOG_FORMAT = "[%(asctime)s][%(filename)s][%(lineno)d]> %(levelname).1s: %(message)s"
FILE_TIME_FORMAT = "%d.%m.%y %H:%M:%S"
CLEAR_RE = re.compile(r"(\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~]))|(\n)|(\r)")


def add_colors(text: str) -> str:
    colors = {
        "$YELLOW": Fore.LIGHTYELLOW_EX,
        "$CYAN": Fore.LIGHTCYAN_EX,
        "$MAGENTA": Fore.LIGHTMAGENTA_EX,
        "$BLUE": Fore.LIGHTBLUE_EX,
        "$GREEN": Fore.LIGHTGREEN_EX,
        "$RED": Fore.LIGHTRED_EX,
        "$BLACK": Fore.LIGHTBLACK_EX,
        "$WHITE": Fore.WHITE,
        "$CLIENT": EVENT_COLORS["client"],
        "$SELLER": EVENT_COLORS["seller"],
        "$SUCCESS": EVENT_COLORS["success"],
        "$TIMER": EVENT_COLORS["timer"],
        "$PLUGIN": EVENT_COLORS["plugin"],
        "$ERROR": EVENT_COLORS["error"],
        "$SYSTEM": EVENT_COLORS["system"],
    }
    for token, color in colors.items():
        if token in text:
            text = text.replace(token, color)
    return text


class CLILoggerFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        msg = add_colors(record.getMessage())
        level_color = LOG_COLORS.get(record.levelno, "")
        msg = msg.replace("$RESET", level_color)
        record.msg = msg
        log_format = CLI_LOG_FORMAT.replace("$RESET", Style.RESET_ALL + level_color)
        return logging.Formatter(log_format, CLI_TIME_FORMAT).format(record)


class FileLoggerFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        msg = CLEAR_RE.sub("", record.getMessage())
        record.msg = msg
        return logging.Formatter(FILE_LOG_FORMAT, FILE_TIME_FORMAT).format(record)


LOGGER_CONFIG = {
    "version": 1,
    "handlers": {
        "file_handler": {
            "class": "logging.handlers.RotatingFileHandler",
            "level": "DEBUG",
            "formatter": "file_formatter",
            "filename": "logs/log.log",
            "maxBytes": 20 * 1024 * 1024,
            "backupCount": 25,
            "encoding": "utf-8",
        },
        "cli_handler": {
            "class": "logging.StreamHandler",
            "level": "INFO",
            "formatter": "cli_formatter",
        },
    },
    "formatters": {
        "file_formatter": {"()": "Utils.logger.FileLoggerFormatter"},
        "cli_formatter": {"()": "Utils.logger.CLILoggerFormatter"},
    },
    "loggers": {
        "main": {"handlers": ["cli_handler", "file_handler"], "level": "DEBUG"},
        "StarvellAPI": {"handlers": ["cli_handler", "file_handler"], "level": "DEBUG"},
        "LSB": {"handlers": ["cli_handler", "file_handler"], "level": "DEBUG"},
        "TGBot": {"handlers": ["cli_handler", "file_handler"], "level": "DEBUG"},
        "TeleBot": {"handlers": ["file_handler"], "level": "ERROR", "propagate": False},
    },
}
