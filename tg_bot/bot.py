from __future__ import annotations

import logging
import os
import re
import threading
import time
from typing import TYPE_CHECKING

import telebot
from telebot.types import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Message

from tg_bot.CBT import CBT
from tg_bot.auth import AuthManager
from tg_bot.keyboards import (
    configs_kb,
    global_settings_kb,
    main_menu,
    notification_kb,
)
from Utils.config_loader import (
    AUTO_DELIVERY_CONFIG,
    AUTO_RESPONSE_CONFIG,
    COMMANDS_CONFIG,
    MAIN_CONFIG,
    load_commands_config,
    save_commands_config,
)
from Utils.session_log import get_session_log_path
from Utils.variables import variables_help_text

if TYPE_CHECKING:
    from lsb import LSB

logger = logging.getLogger("TGBot")

CONFIG_PATHS = {
    "main": MAIN_CONFIG,
    "delivery": AUTO_DELIVERY_CONFIG,
    "response": AUTO_RESPONSE_CONFIG,
    "commands": COMMANDS_CONFIG,
}


class TGBot:
    def __init__(self, lsb: "LSB"):
        self.lsb = lsb
        self.cfg = lsb.main_cfg
        telebot.apihelper.ENABLE_MIDDLEWARE = True
        token = self.cfg.get("Telegram", "token")
        self.bot = telebot.TeleBot(token, parse_mode="HTML", threaded=False, use_class_middlewares=True)
        self.auth = AuthManager(self.cfg.get("Telegram", "secretKeyHash"))
        self.user_states: dict[int, dict] = {}
        self.pending_upload: dict[int, str] = {}
        self._start_time = int(time.time())

    def init(self) -> None:
        self._setup_commands()
        self._register_handlers()
        self._setup_middleware()
        self.lsb.plugins.run_handlers("BIND_TO_PRE_INIT", self.lsb)

    def run(self) -> None:
        logger.info("$SYSTEMPolling Telegram...")
        self.bot.get_updates(offset=-1)
        self.bot.infinity_polling(timeout=30, long_polling_timeout=30)

    def _setup_middleware(self) -> None:
        @self.bot.middleware_handler(update_types=["message"])
        def filter_old_messages(bot_instance, message):
            if message.date < self._start_time:
                raise telebot.CancelUpdate()

    def _setup_commands(self) -> None:
        commands = [
            BotCommand("start", "Запуск / авторизация"),
            BotCommand("menu", "Главное меню"),
            BotCommand("profile", "Профиль Starvell"),
            BotCommand("session", "Информация о session_token"),
            BotCommand("logs", "Логи текущей сессии"),
            BotCommand("restart", "Перезапуск бота"),
            BotCommand("help", "Справка"),
        ]
        self.bot.set_my_commands(commands)
        for plugin in self.lsb.plugins.list_plugins():
            logger.info(f"$PLUGINРегистрирую команды плагина: {plugin.name}, handlers: {list(plugin.handlers.keys())}")
            for handler in plugin.handlers.get("BIND_TO_TELEGRAM_COMMANDS", []):
                try:
                    handler(self.lsb, self)
                    logger.info(f"$PLUGINКоманды плагина {plugin.name} зарегистрированы")
                except Exception as e:
                    logger.error(f"$ERRORРегистрация команд плагина {plugin.name}: {e}", exc_info=True)

    def _register_handlers(self) -> None:
        @self.bot.message_handler(commands=["start"])
        def start_handler(msg: Message):
            if msg.chat.type != "private":
                return
            if self.auth.is_authorized(msg.from_user.id):
                self.send_main_menu(msg.chat.id, msg.message_id)
            else:
                self.bot.send_message(
                    msg.chat.id,
                    "🔐 <b>Lumus Starvell Bot</b>\n\nВведите пароль для доступа:",
                )
                self.user_states[msg.from_user.id] = {"state": "auth"}

        @self.bot.message_handler(commands=["menu"])
        def menu_handler(msg: Message):
            if not self._check_auth(msg):
                return
            self.send_main_menu(msg.chat.id)

        @self.bot.message_handler(commands=["profile"])
        def profile_handler(msg: Message):
            if not self._check_auth(msg):
                return
            acc = self.lsb.account
            if not acc:
                self.bot.send_message(msg.chat.id, "Аккаунт Starvell не инициализирован.")
                return
            self.bot.send_message(
                msg.chat.id,
                f"👤 <b>{acc.username}</b>\n"
                f"ID: {acc.user_id}\n"
                f"💰 Баланс: {acc.balance} ₽\n"
                f"📦 Активных заказов: {acc.active_orders}",
            )

        @self.bot.message_handler(commands=["session"])
        def session_handler(msg: Message):
            if not self._check_auth(msg):
                return
            self.bot.send_message(
                msg.chat.id,
                "🔑 <b>Session Token</b>\n\n"
                "Получите cookie <code>session</code> на starvell.com:\n"
                "DevTools → Application → Cookies → starvell.com\n\n"
                "Вставьте значение или полную строку cookie в configs/_main.txt → session_token",
            )

        @self.bot.message_handler(commands=["restart"])
        def restart_handler(msg: Message):
            if not self._check_auth(msg):
                return
            self.bot.send_message(msg.chat.id, "🛑 Бот остановлен.")
            threading.Thread(target=self.lsb.restart, daemon=True).start()

        @self.bot.message_handler(commands=["logs"])
        def logs_handler(msg: Message):
            if not self._check_auth(msg):
                return
            path = get_session_log_path()
            if not os.path.exists(path) or os.path.getsize(path) == 0:
                self.bot.send_message(msg.chat.id, "Логи текущей сессии пусты.")
                return
            with open(path, "rb") as f:
                self.bot.send_document(
                    msg.chat.id,
                    f,
                    visible_file_name="session.log",
                    caption="📋 Логи текущей сессии LSB",
                )

        @self.bot.message_handler(commands=["help"])
        def help_handler(msg: Message):
            if not self._check_auth(msg):
                return
            self.bot.send_message(
                msg.chat.id,
                "<b>Команды LSB</b>\n"
                "/menu — главное меню\n"
                "/profile — профиль Starvell\n"
                "/session — как получить session_token\n"
                "/logs — логи текущей сессии\n"
                "/restart — остановить бота\n"
                "/help — эта справка",
            )

        @self.bot.message_handler(content_types=["document"])
        def document_handler(msg: Message):
            if not self._check_auth(msg):
                return

            # Плагин
            state_data = self.user_states.get(msg.from_user.id, {})
            if state_data.get("state") == "plugin_upload":
                self._handle_plugin_upload(msg)
                return

            upload_type = self.pending_upload.pop(msg.from_user.id, None)
            if not upload_type:
                return
            file_info = self.bot.get_file(msg.document.file_id)
            content = self.bot.download_file(file_info.file_path)
            path = CONFIG_PATHS.get(upload_type)
            if not path:
                return
            with open(path, "wb") as f:
                f.write(content)
            logger.info(f"$SUCCESSКонфиг загружен: {path}")
            self.bot.send_message(msg.chat.id, f"✅ Файл сохранён: <code>{path}</code>")

        @self.bot.message_handler(content_types=["text"])
        def text_handler(msg: Message):
            if msg.chat.type != "private":
                return
            uid = msg.from_user.id
            state_data = self.user_states.get(uid)
            if not state_data:
                if not self.auth.is_authorized(uid):
                    ok, err = self.auth.authorize(uid, msg.text.strip())
                    if ok:
                        self.bot.send_message(msg.chat.id, "✅ Доступ разрешён!")
                        self.send_main_menu(msg.chat.id)
                    else:
                        self.bot.send_message(msg.chat.id, f"❌ {err}")
                return

            state = state_data.get("state")
            if state == "auth":
                ok, err = self.auth.authorize(uid, msg.text.strip())
                if ok:
                    self.user_states.pop(uid, None)
                    self.bot.send_message(msg.chat.id, "✅ Доступ разрешён!")
                    self.send_main_menu(msg.chat.id)
                else:
                    self.bot.send_message(msg.chat.id, f"❌ {err}")
            elif state == "cmd_add_name":
                self._finish_cmd_add_name(msg)
            elif state == "cmd_edit":
                self._finish_cmd_edit(msg)
            elif state == "global_edit":
                self._finish_global_edit(msg)
            elif state == "plugin_upload":
                self._handle_plugin_upload(msg)
            elif state == "reply_to_chat":
                self._finish_reply_to_chat(msg)

        @self.bot.callback_query_handler(func=lambda c: True)
        def callback_handler(call):
            if call.message.chat.type != "private":
                return
            if not self.auth.is_authorized(call.from_user.id):
                self.bot.answer_callback_query(call.id, "Требуется авторизация. /start")
                return
            data = call.data or ""
            self._route_callback(call, data)

    def _check_auth(self, msg: Message) -> bool:
        if self.auth.is_authorized(msg.from_user.id):
            return True
        self.bot.send_message(msg.chat.id, "🔐 Введите /start и авторизуйтесь паролем.")
        return False

    def _route_callback(self, call, data: str) -> None:
        chat_id = call.message.chat.id
        msg_id = call.message.message_id

        if data == CBT.BACK_MAIN or data == CBT.MAIN:
            self.send_main_menu(chat_id, msg_id)
        elif data == CBT.NOTIFICATIONS:
            self._edit(chat_id, msg_id, "🔔 <b>Уведомления</b>", notification_kb(self.cfg))
        elif data.startswith(f"{CBT.NOTIF_TOGGLE}:"):
            key = data.split(":", 2)[2]
            section = self.cfg["Notifications"]
            cur = section.get(key, "1")
            section[key] = "0" if cur == "1" else "1"
            self.lsb.save_main_config()
            logger.info(f"$SYSTEMУведомление {key}: {section[key]}")
            self._edit(chat_id, msg_id, "🔔 <b>Уведомления</b>", notification_kb(self.cfg))
        elif data == CBT.COMMANDS:
            self._show_commands_list(chat_id, msg_id)
        elif data.startswith(f"{CBT.CMD_VIEW}:"):
            self._show_command(chat_id, msg_id, data.split(":", 2)[2])
        elif data.startswith(f"{CBT.CMD_TOGGLE_NOTIFY}:"):
            self._toggle_cmd_notify(chat_id, msg_id, data.split(":", 2)[2])
        elif data.startswith(f"{CBT.CMD_EDIT_BUYER}:"):
            name = data.split(":", 2)[2]
            self._prompt_text_edit(
                call.from_user.id,
                chat_id,
                f"✏️ <b>Сообщение покупателю</b> — команда «{name}»",
                "cmd_edit",
                {"name": name, "field": "buyer_message", "return_cmd": name},
            )
        elif data.startswith(f"{CBT.CMD_EDIT_OWNER}:"):
            name = data.split(":", 2)[2]
            self._prompt_text_edit(
                call.from_user.id,
                chat_id,
                f"✏️ <b>Сообщение владельцу</b> — команда «{name}»",
                "cmd_edit",
                {"name": name, "field": "owner_message", "return_cmd": name},
            )
        elif data == CBT.CMD_ADD:
            self.user_states[call.from_user.id] = {"state": "cmd_add_name"}
            self.bot.send_message(chat_id, "Введите триггер новой команды (например: !привет):")
        elif data.startswith(f"{CBT.CMD_DELETE}:"):
            self._delete_command(chat_id, msg_id, data.split(":", 2)[2])
        elif data == CBT.GLOBAL:
            self._edit(chat_id, msg_id, "⚙️ <b>Глобальные настройки</b>", global_settings_kb(self.cfg))
        elif data.startswith(f"{CBT.GLOBAL_TOGGLE}:"):
            key = data.split(":", 2)[2]
            section = self.cfg["Global"]
            cur = section.get(key, "0")
            section[key] = "0" if cur == "1" else "1"
            self.lsb.save_main_config()
            logger.info(f"$SYSTEMГлобальная настройка {key}: {section[key]}")
            self._edit(chat_id, msg_id, "⚙️ <b>Глобальные настройки</b>", global_settings_kb(self.cfg))
        elif data.startswith(f"{CBT.GLOBAL_EDIT}:"):
            key = data.split(":", 2)[2]
            labels = {
                "greeting_text": "Приветствие (первое сообщение)",
                "order_confirm_text": "Подтверждение заказа",
                "review_text": "Ответ на отзыв",
            }
            self._prompt_text_edit(
                call.from_user.id,
                chat_id,
                f"✏️ <b>{labels.get(key, key)}</b>",
                "global_edit",
                {"key": key},
            )
        elif data == CBT.CONFIGS:
            self._edit(chat_id, msg_id, "📁 <b>Конфиги</b>", configs_kb())
        elif data.startswith(f"{CBT.CONFIG_UPLOAD}:"):
            kind = data.split(":", 2)[2]
            self.pending_upload[call.from_user.id] = kind
            self.bot.send_message(chat_id, f"Отправьте файл для замены <code>{CONFIG_PATHS.get(kind)}</code>")
        elif data.startswith(f"{CBT.CONFIG_DOWNLOAD}:"):
            kind = data.split(":", 2)[2]
            self._download_config(chat_id, kind)
        elif data == CBT.PLUGINS:
            self._show_plugins(chat_id, msg_id)
        elif data == CBT.PLUGIN_ADD:
            self.user_states[call.from_user.id] = {"state": "plugin_upload"}
            self.bot.send_message(
                chat_id,
                "Отправьте файл плагина (.py).\n\n⚠️ <b>После добавления выполните /restart</b>",
            )
        elif data.startswith(f"{CBT.PLUGIN_VIEW}:"):
            self._show_plugin_detail(chat_id, msg_id, data.split(":", 2)[2])
        elif data.startswith(f"{CBT.PLUGIN_TOGGLE}:"):
            self._toggle_plugin(chat_id, msg_id, data.split(":", 2)[2])
        elif data.startswith(f"{CBT.PLUGIN_DELETE}:"):
            self._delete_plugin(chat_id, msg_id, data.split(":", 2)[2])
        elif data.startswith(f"{CBT.PLUGIN_MENU}:"):
            self._open_plugin_menu(chat_id, msg_id, call.from_user.id, data.split(":", 2)[2])
        elif data.startswith(f"{CBT.PLUGIN_CMDS}:"):
            self._show_plugin_commands(chat_id, msg_id, data.split(":", 2)[2])
        elif data.startswith(f"{CBT.COPY_VAR}:"):
            var = data.split(":", 2)[2]
            self.bot.answer_callback_query(call.id, f"Скопируйте: {var}", show_alert=True)
        elif data.startswith("reply:"):
            parts = data.split(":", 2)
            starvell_chat_id = parts[1] if len(parts) > 1 else ""
            interlocutor_raw = parts[2] if len(parts) > 2 else ""
            interlocutor_id = int(interlocutor_raw) if interlocutor_raw.isdigit() else None
            self.user_states[call.from_user.id] = {
                "state": "reply_to_chat",
                "chat_id": starvell_chat_id,
                "interlocutor_id": interlocutor_id,
            }
            self.bot.send_message(chat_id, "✏️ Введите сообщение для отправки в чат:")
        self.bot.answer_callback_query(call.id)

    def send_main_menu(self, chat_id: int, message_id: int | None = None) -> None:
        text = "⭐ <b>Lumus Starvell Bot</b>\n\nВыберите раздел:"
        kb = main_menu()
        if message_id:
            try:
                self.bot.edit_message_text(text, chat_id, message_id, reply_markup=kb)
                return
            except telebot.apihelper.ApiTelegramException:
                pass
        self.bot.send_message(chat_id, text, reply_markup=kb)

    def send_main_menu_to_all(self) -> None:
        for user_id in self.auth.authorized:
            try:
                self.send_main_menu(user_id)
            except Exception as e:
                logger.warning(f"Не удалось отправить меню {user_id}: {e}")

    def send_notification(self, text: str) -> None:
        for user_id in self.auth.authorized:
            try:
                self.bot.send_message(user_id, text)
            except Exception as e:
                logger.warning(f"Не удалось отправить уведомление {user_id}: {e}")

    def send_new_message_notification(self, chat_id: str, username: str, text: str, interlocutor_id: int | None) -> None:
        kb = InlineKeyboardMarkup()
        iid = str(interlocutor_id) if interlocutor_id is not None else ""

        btn_reply = InlineKeyboardButton("↩️ Ответить", callback_data=f"reply:{chat_id}:{iid}")
        chat_url = f"https://starvell.com/chat/{chat_id}"
        btn_open = InlineKeyboardButton("🔗 Открыть чат", url=chat_url)

        kb.row(btn_reply, btn_open)

        for user_id in self.auth.authorized:
            try:
                self.bot.send_message(
                    user_id,
                    f"💬 <b>Новое сообщение</b>\nОт: {username}\n\n{text[:500]}",
                    reply_markup=kb,
                )
            except Exception as e:
                logger.warning(f"Не удалось отправить уведомление {user_id}: {e}")

    def _finish_reply_to_chat(self, msg) -> None:
        state = self.user_states.pop(msg.from_user.id, {})
        starvell_chat_id = state.get("chat_id")
        interlocutor_id = state.get("interlocutor_id")
        if not starvell_chat_id:
            self.bot.send_message(msg.chat.id, "❌ Ошибка: чат не найден.")
            return
        ok = self.lsb.account.send_chat_message(starvell_chat_id, msg.text, interlocutor_id)
        if ok:
            self.bot.send_message(msg.chat.id, "✅ Сообщение отправлено.")
        else:
            self.bot.send_message(msg.chat.id, "❌ Не удалось отправить сообщение.")

    def _edit(self, chat_id, msg_id, text, kb):
        self.bot.edit_message_text(text, chat_id, msg_id, reply_markup=kb)

    def _show_commands_list(self, chat_id, msg_id):
        commands = load_commands_config()
        kb = InlineKeyboardMarkup(row_width=1)
        for name, data in commands.items():
            kb.add(InlineKeyboardButton(f"⌨️ {name}", callback_data=f"{CBT.CMD_VIEW}:{name}"))
        kb.add(InlineKeyboardButton("➕ Добавить команду", callback_data=CBT.CMD_ADD))
        kb.add(InlineKeyboardButton("◀️ Назад", callback_data=CBT.BACK_MAIN))
        self._edit(chat_id, msg_id, "⌨️ <b>Команды автоответа</b>", kb)

    def _show_command(self, chat_id, msg_id, name):
        commands = load_commands_config()
        cmd = commands.get(name, {})
        notify = cmd.get("notify_owner", True)
        kb = InlineKeyboardMarkup(row_width=1)
        kb.add(InlineKeyboardButton("✏️ Сообщение покупателю", callback_data=f"{CBT.CMD_EDIT_BUYER}:{name}"))
        kb.add(InlineKeyboardButton("✏️ Сообщение владельцу", callback_data=f"{CBT.CMD_EDIT_OWNER}:{name}"))
        kb.add(
            InlineKeyboardButton(
                f"{'✅' if notify else '❌'} Оповещать бота",
                callback_data=f"{CBT.CMD_TOGGLE_NOTIFY}:{name}",
            )
        )
        kb.add(InlineKeyboardButton("🗑 Удалить", callback_data=f"{CBT.CMD_DELETE}:{name}"))
        kb.add(InlineKeyboardButton("◀️ Назад", callback_data=CBT.COMMANDS))
        text = (
            f"⌨️ <b>{name}</b>\n\n"
            f"<b>Покупателю:</b>\n<code>{cmd.get('buyer_message', '')}</code>\n\n"
            f"<b>Владельцу:</b>\n<code>{cmd.get('owner_message', '')}</code>"
        )
        self._edit(chat_id, msg_id, text, kb)

    def _toggle_cmd_notify(self, chat_id, msg_id, name):
        commands = load_commands_config()
        if name in commands:
            commands[name]["notify_owner"] = not commands[name].get("notify_owner", True)
            save_commands_config(commands)
        self._show_command(chat_id, msg_id, name)

    def _prompt_text_edit(self, user_id: int, chat_id: int, title: str, state: str, extra: dict) -> None:
        self.user_states[user_id] = {"state": state, **extra}
        text = f"{title}\n\n{variables_help_text()}\n\n<i>Отправьте новый текст сообщением:</i>"
        self.bot.send_message(chat_id, text)

    def _finish_cmd_edit(self, msg):
        state = self.user_states.pop(msg.from_user.id, {})
        name = state.get("name")
        field = state.get("field")
        commands = load_commands_config()
        if name in commands and field:
            commands[name][field] = msg.text
            save_commands_config(commands)
            logger.info(f"$SUCCESSКоманда {name}.{field} обновлена")
        self.bot.send_message(msg.chat.id, "✅ Сохранено")
        if name:
            sent = self.bot.send_message(msg.chat.id, "Обновлённое меню команды:")
            self._show_command(msg.chat.id, sent.message_id, name)
        else:
            self.send_main_menu(msg.chat.id)

    def _finish_cmd_add_name(self, msg):
        trigger = msg.text.strip()
        self.user_states.pop(msg.from_user.id, None)
        commands = load_commands_config()
        name = re.sub(r"[^\w\-!]", "_", trigger)[:32]
        commands[name] = {
            "trigger": trigger,
            "buyer_message": "Здравствуйте!",
            "owner_message": f"Сработала команда {trigger}",
            "notify_owner": True,
            "enabled": True,
        }
        save_commands_config(commands)
        logger.info(f"$SUCCESSДобавлена команда: {name}")
        self.bot.send_message(msg.chat.id, f"✅ Команда «{name}» создана")
        self.send_main_menu(msg.chat.id)

    def _delete_command(self, chat_id, msg_id, name):
        commands = load_commands_config()
        commands.pop(name, None)
        save_commands_config(commands)
        self._show_commands_list(chat_id, msg_id)

    def _finish_global_edit(self, msg):
        state = self.user_states.pop(msg.from_user.id, {})
        key = state.get("key")
        if key:
            self.cfg.set("Global", key, msg.text)
            self.lsb.save_main_config()
            logger.info(f"$SUCCESSГлобальный текст {key} обновлён")
        self.bot.send_message(msg.chat.id, "✅ Сохранено")
        sent = self.bot.send_message(msg.chat.id, "⚙️ Глобальные настройки:")
        self._edit(sent.chat.id, sent.message_id, "⚙️ <b>Глобальные настройки</b>", global_settings_kb(self.cfg))

    def _download_config(self, chat_id, kind):
        path = CONFIG_PATHS.get(kind)
        if path and os.path.exists(path):
            with open(path, "rb") as f:
                self.bot.send_document(chat_id, f, visible_file_name=os.path.basename(path))
        else:
            self.bot.send_message(chat_id, "Файл не найден.")

    def _show_plugins(self, chat_id, msg_id):
        plugins = self.lsb.plugins.list_plugins()
        kb = InlineKeyboardMarkup(row_width=1)
        for p in plugins:
            state = "✅" if p.enabled else "❌"
            kb.add(InlineKeyboardButton(f"{state} {p.name} v{p.version}", callback_data=f"{CBT.PLUGIN_VIEW}:{p.uuid}"))
        kb.add(InlineKeyboardButton("➕ Добавить плагин", callback_data=CBT.PLUGIN_ADD))
        kb.add(InlineKeyboardButton("◀️ Назад", callback_data=CBT.BACK_MAIN))
        lines = ["🧩 <b>Плагины</b>\n"]
        for p in plugins:
            lines.append(f"• {p.name} — {p.description[:60]}")
        if not plugins:
            lines.append("Плагинов нет.")
        self._edit(chat_id, msg_id, "\n".join(lines), kb)

    def _show_plugin_detail(self, chat_id, msg_id, plugin_uuid):
        plugin = self.lsb.plugins.get_by_uuid(plugin_uuid)
        if not plugin:
            self._show_plugins(chat_id, msg_id)
            return
        kb = InlineKeyboardMarkup(row_width=1)
        if plugin.commands:
            kb.add(InlineKeyboardButton(f"⌨️ Команды ({len(plugin.commands)})", callback_data=f"{CBT.PLUGIN_CMDS}:{plugin_uuid}"))
        if plugin.menu_handler:
            kb.add(InlineKeyboardButton("📋 Меню плагина", callback_data=f"{CBT.PLUGIN_MENU}:{plugin_uuid}"))
        kb.add(InlineKeyboardButton(f"{'✅ Включён' if plugin.enabled else '❌ Выключен'}", callback_data=f"{CBT.PLUGIN_TOGGLE}:{plugin_uuid}"))
        kb.add(InlineKeyboardButton("🗑 Удалить плагин", callback_data=f"{CBT.PLUGIN_DELETE}:{plugin_uuid}"))
        kb.add(InlineKeyboardButton("◀️ К списку", callback_data=CBT.PLUGINS))
        text = (
            f"🧩 <b>{plugin.name}</b> v{plugin.version}\n\n"
            f"<b>Автор:</b> {plugin.credits}\n"
            f"<b>Описание:</b> {plugin.description}\n"
            f"<b>UUID:</b> <code>{plugin.uuid}</code>"
        )
        self._edit(chat_id, msg_id, text, kb)

    def _show_plugin_commands(self, chat_id, msg_id, plugin_uuid):
        plugin = self.lsb.plugins.get_by_uuid(plugin_uuid)
        if not plugin:
            return
        lines = [f"⌨️ <b>Команды — {plugin.name}</b>\n"]
        if plugin.commands:
            for cmd in plugin.commands:
                lines.append(f"/{cmd['command']} — {cmd.get('description') or '—'}")
        else:
            lines.append("Плагин не регистрирует команды.")
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("◀️ Назад", callback_data=f"{CBT.PLUGIN_VIEW}:{plugin_uuid}"))
        self._edit(chat_id, msg_id, "\n".join(lines), kb)

    def _open_plugin_menu(self, chat_id, msg_id, user_id, plugin_uuid):
        plugin = self.lsb.plugins.get_by_uuid(plugin_uuid)
        if not plugin or not plugin.menu_handler:
            self.bot.send_message(chat_id, "У этого плагина нет меню.")
            return
        if not plugin.enabled:
            self.bot.send_message(chat_id, "Плагин выключен. Включите его в меню плагина.")
            return
        try:
            plugin.menu_handler(self.lsb, self, chat_id, msg_id, plugin_uuid)
        except Exception as e:
            logger.error(f"$ERRORМеню плагина {plugin.name}: {e}")
            self.bot.send_message(chat_id, f"❌ Ошибка меню плагина: {e}")

    def _toggle_plugin(self, chat_id, msg_id, plugin_uuid):
        plugin = self.lsb.plugins.get_by_uuid(plugin_uuid)
        if plugin:
            self.lsb.plugins.set_enabled(plugin_uuid, not plugin.enabled)
            logger.info(f"$PLUGINПлагин {plugin.name}: {'вкл' if plugin.enabled else 'выкл'}")
        self._show_plugin_detail(chat_id, msg_id, plugin_uuid)

    def _delete_plugin(self, chat_id, msg_id, plugin_uuid):
        plugin = self.lsb.plugins.get_by_uuid(plugin_uuid)
        if not plugin:
            self._show_plugins(chat_id, msg_id)
            return
        name = plugin.name
        if self.lsb.plugins.delete_plugin(plugin_uuid):
            self.bot.send_message(chat_id, f"🗑 Плагин «{name}» удалён.\n⚠️ Выполните /restart")
        self._show_plugins(chat_id, msg_id)

    def _handle_plugin_upload(self, msg):
        self.user_states.pop(msg.from_user.id, None)
        if not msg.document or not msg.document.file_name.endswith(".py"):
            self.bot.send_message(msg.chat.id, "Отправьте .py файл.")
            return
        os.makedirs("plugins", exist_ok=True)
        path = os.path.join("plugins", msg.document.file_name)
        file_info = self.bot.get_file(msg.document.file_id)
        content = self.bot.download_file(file_info.file_path)
        with open(path, "wb") as f:
            f.write(content)

        try:
            plugin = self.lsb.plugins._load_file(path)
            self.bot.send_message(
                msg.chat.id,
                f"✅ <b>Плагин успешно загружен!</b>\n\n"
                f"🧩 <b>{plugin.name}</b> v{plugin.version}\n"
                f"👤 Автор: {plugin.credits}\n"
                f"📝 {plugin.description}\n\n"
                f"⚠️ <b>Выполните /restart для активации</b>",
            )
        except Exception as e:
            os.remove(path)
            self.bot.send_message(
                msg.chat.id,
                f"❌ <b>Ошибка плагина:</b> {e}\n\nФайл не сохранён.",
            )
            return

        logger.info(f"$PLUGINЗагружен плагин: {path}")