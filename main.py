"""
Точка входа Lumus Starvell Bot.
"""
from __future__ import annotations

import logging.config
import os
import sys
import time

import colorama
from colorama import Fore, Style

import Utils.config_loader as cfg_loader
import Utils.lsb_tools as lsb_tools
from Utils.exceptions import ConfigParseError
from Utils.logger import LOGGER_CONFIG
from Utils.logo import ensure_logo_assets, print_startup_banner
from Utils.session_log import init_session_log
from first_setup import create_empty_configs, first_setup
from lsb import LSB
from version import VERSION

lsb_tools.set_console_title(f"Lumus Starvell Bot v{VERSION}")

if getattr(sys, "frozen", False):
    os.chdir(os.path.dirname(sys.executable))
else:
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

folders = [
    "configs",
    "logs",
    "storage",
    "storage/cache",
    "storage/plugins",
    "plugins",
    "assets",
]
for folder in folders:
    os.makedirs(folder, exist_ok=True)

create_empty_configs()
ensure_logo_assets()

colorama.init()
logging.config.dictConfig(LOGGER_CONFIG)
init_session_log()
logging.raiseExceptions = False
logger = logging.getLogger("main")
logger.debug("-" * 66)

print_startup_banner(VERSION)
print(f"{Fore.MAGENTA}{Style.BRIGHT}Lumus Starvell Bot (LSB){Style.RESET_ALL}")
print(f"{Fore.CYAN}Автоматизация продаж на Starvell{Style.RESET_ALL}\n")

if not os.path.exists("configs/_main.txt"):
    first_setup()
    sys.exit()

try:
    logger.info("$MAGENTAЗагружаю configs/_main.txt...")
    MAIN_CFG = cfg_loader.load_main_config()
    logger.info("$MAGENTAЗагружаю configs/auto_response.txt...")
    AR_CFG = cfg_loader.load_auto_response_config()
    logger.info("$MAGENTAЗагружаю configs/auto_delivery.txt...")
    AD_CFG = cfg_loader.load_auto_delivery_config()
except ConfigParseError as e:
    logger.error(f"$ERROR{e}")
    time.sleep(5)
    sys.exit(1)
except UnicodeDecodeError:
    logger.error("$ERRORОшибка UTF-8. Кодировка файлов должна быть UTF-8, окончания строк — LF.")
    time.sleep(5)
    sys.exit(1)

if MAIN_CFG.get("Telegram", "enabled", fallback="0") == "1" and MAIN_CFG.get("Starvell", "session_token"):
    balance = "—"
    orders = "—"

try:
    LSB(MAIN_CFG, AR_CFG, AD_CFG, VERSION).init().run()
except KeyboardInterrupt:
    logger.info("$SYSTEMЗавершение...")
    sys.exit()
except Exception:
    logger.critical("$ERRORКритическая ошибка LSB", exc_info=True)
    time.sleep(5)
    sys.exit(1)
