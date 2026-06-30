from __future__ import annotations

import logging
import threading
import time
from configparser import ConfigParser

from colorama import Fore, Style

from StarvellAPI.account import Account
from StarvellAPI.common.exceptions import UnauthorizedError
from StarvellAPI.updater.runner import Runner
from handlers import on_new_message, on_new_order, on_order_confirm, on_payment, on_review
from plugin_manager import PluginManager
from tg_bot.bot import TGBot
from Utils.config_loader import save_config

logger = logging.getLogger("LSB")


def _log_account_info(rows: list[tuple[str, str]]) -> None:
    col1_w = max(len(r[0]) for r in rows)
    col2_w = max(len(str(r[1])) for r in rows)
    width = col1_w + col2_w + 7

    logger.info(f"$BLACK┌{'─' * width}┐{Style.RESET_ALL}")
    for key, val in rows:
        logger.info(
            f"$BLACK│ $CYAN{key:<{col1_w}}{Style.RESET_ALL} $BLACK│{Style.RESET_ALL} "
            f"$WHITE{val:<{col2_w}}{Style.RESET_ALL} $BLACK│{Style.RESET_ALL}"
        )
    logger.info(f"$BLACK└{'─' * width}┘{Style.RESET_ALL}")


class LSB:
    instance: "LSB | None" = None

    def __init__(
        self,
        main_cfg: ConfigParser,
        ar_cfg: ConfigParser,
        ad_cfg: ConfigParser,
        version: str,
    ):
        self.main_cfg = main_cfg
        self.ar_cfg = ar_cfg
        self.ad_cfg = ad_cfg
        self.version = version
        self.account: Account | None = None
        self.runner: Runner | None = None
        self.tg_bot: TGBot | None = None
        self.plugins = PluginManager()
        self._bump_thread: threading.Thread | None = None
        self._stats_thread: threading.Thread | None = None
        self._running = False
        self._bump_cooldowns: dict[tuple[int, int], float] = {}
        LSB.instance = self

    def init(self) -> "LSB":
        self.plugins.load_all()
        self.plugins.run_handlers("BIND_TO_PRE_INIT", self)

        if self.main_cfg.get("Telegram", "enabled", fallback="0") == "1":
            self.tg_bot = TGBot(self)
            self.tg_bot.init()
            threading.Thread(target=self.tg_bot.run, daemon=True, name="TGBot").start()
            logger.info("$SUCCESSTelegram-бот запущен")

        self._init_account()
        self.plugins.run_handlers("BIND_TO_POST_INIT", self)
        return self

    def _init_account(self) -> None:
        while True:
            try:
                self.account = Account(
                    session_token=self.main_cfg.get("Starvell", "session_token"),
                    sid_cookie=self.main_cfg.get("Starvell", "sid_cookie", fallback=""),
                    my_games_cookie=self.main_cfg.get("Starvell", "my_games_cookie", fallback=""),
                    user_agent=self.main_cfg.get("Starvell", "user_agent", fallback=None),
                ).get()
                break
            except UnauthorizedError as e:
                logger.error(f"$ERRORАвторизация Starvell: {e}")
                logger.info("$TIMERПовтор через 30 сек...")
                time.sleep(30)

        self.runner = Runner(
            self.account,
            poll_interval=float(self.main_cfg.get("Other", "requests_delay", fallback="4")),
        )
        self.runner.add_handler("new_message", lambda e: self._dispatch("new_message", e))
        self.runner.add_handler("new_order", lambda e: self._dispatch("new_order", e))
        self.runner.add_handler("payment", lambda e: self._dispatch("payment", e))
        self.runner.add_handler("order_confirm", lambda e: self._dispatch("order_confirm", e))
        self.runner.add_handler("review", lambda e: self._dispatch("review", e))

        lots, categories = self.account.count_lots()

        _log_account_info([
            ("Аккаунт", self.account.username or "—"),
            ("ID", str(self.account.user_id or "—")),
            ("Баланс", f"{self.account.balance} ₽"),
            ("Активных заказов", str(self.account.active_orders)),
            ("Лотов", str(lots)),
            ("Категорий (автоподнятие)", str(categories)),
            ("Версия", self.version),
        ])

    def _dispatch(self, event_type: str, event) -> None:
        handlers = {
            "new_message": on_new_message,
            "new_order": on_new_order,
            "payment": on_payment,
            "order_confirm": on_order_confirm,
            "review": on_review,
        }
        fn = handlers.get(event_type)
        if fn:
            fn(self, event)
        bind = {
            "new_message": "BIND_TO_NEW_MESSAGE",
            "new_order": "BIND_TO_NEW_ORDER",
            "payment": "BIND_TO_PAYMENT",
            "order_confirm": "BIND_TO_ORDER_CONFIRM",
            "review": "BIND_TO_REVIEW",
        }.get(event_type)
        if bind:
            self.plugins.run_handlers(bind, self, event)

    def run(self) -> None:
        self._running = True
        self.plugins.run_handlers("BIND_TO_PRE_START", self)

        if self.runner:
            self.runner.start()

        if self.main_cfg.get("Global", "auto_bump", fallback="0") == "1":
            self._bump_thread = threading.Thread(target=self._bump_loop, daemon=True, name="AutoBump")
            self._bump_thread.start()

        self._stats_thread = threading.Thread(target=self._stats_loop, daemon=True, name="Stats")
        self._stats_thread.start()

        self.plugins.run_handlers("BIND_TO_POST_START", self)

        if self.tg_bot and self.main_cfg.get("Notifications", "bot_start", fallback="1") == "1":
            self.tg_bot.send_notification("🚀 <b>Lumus Starvell Bot запущен</b>")
            self.tg_bot.send_main_menu_to_all()

        logger.info("$SUCCESSLumus Starvell Bot работает")
        try:
            while self._running:
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop()

    def stop(self) -> None:
        self._running = False
        if self.runner:
            self.runner.stop()
        self.plugins.run_handlers("BIND_TO_DELETE", self)
        logger.info("$SYSTEMLSB остановлен")

    def restart(self) -> None:
        import sys
        logger.info("$SYSTEMОстановка по команде /restart...")
        self.stop()
        sys.exit(0)

    def save_main_config(self) -> None:
        save_config("configs/_main.txt", self.main_cfg)

    def _stats_loop(self) -> None:
        while self._running:
            if self.account:
                self.account.refresh_stats()
            time.sleep(60)

    def _bump_loop(self) -> None:
        interval = float(self.main_cfg.get("Other", "bump_check_interval", fallback="300"))
        while self._running:
            try:
                self._try_bump_all()
            except Exception as e:
                logger.error(f"$ERRORАвтоподнятие: {e}")
            time.sleep(interval)

    def _try_bump_all(self) -> None:
        if not self.account:
            return
        categories = self.account.get_categories_for_bump()
        if not categories:
            logger.warning("$TIMERНет категорий для поднятия")
            return

        by_game: dict[int, list[int]] = {}
        for cat in categories:
            by_game.setdefault(cat["gameId"], []).append(cat["categoryId"])

        now = time.time()
        for game_id, cat_ids in by_game.items():
            key = (game_id, cat_ids[0])
            cooldown_until = self._bump_cooldowns.get(key, 0)
            if now < cooldown_until:
                wait = int(cooldown_until - now)
                logger.info(f"$TIMERАвтоподнятие game={game_id}: ждём {wait} сек")
                continue

            result = self.account.bump_categories(game_id, cat_ids)
            if result.get("success"):
                logger.info(f"$SUCCESSКатегории подняты (game={game_id})")
                self._bump_cooldowns[key] = now + 3600
            else:
                resp = result.get("json") or {}
                wait_sec = resp.get("retryAfter") or resp.get("cooldown") or 3600
                try:
                    wait_sec = int(wait_sec)
                except (TypeError, ValueError):
                    wait_sec = 3600
                self._bump_cooldowns[key] = now + wait_sec
                logger.warning(f"$TIMERПоднятие недоступно, ждём {wait_sec} сек")