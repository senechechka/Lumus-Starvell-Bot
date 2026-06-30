"""Клавиатуры Telegram-бота."""
from __future__ import annotations

from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup

from tg_bot.CBT import CBT


def main_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("🔔 Уведомления", callback_data=CBT.NOTIFICATIONS),
        InlineKeyboardButton("⌨️ Команды", callback_data=CBT.COMMANDS),
    )
    kb.add(
        InlineKeyboardButton("⚙️ Глобальные настройки", callback_data=CBT.GLOBAL),
        InlineKeyboardButton("📁 Конфиги", callback_data=CBT.CONFIGS),
    )
    kb.add(InlineKeyboardButton("🧩 Плагины", callback_data=CBT.PLUGINS))
    return kb


def back_main() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("◀️ Главное меню", callback_data=CBT.BACK_MAIN))
    return kb


def toggle_button(label: str, callback: str, enabled: bool) -> InlineKeyboardButton:
    state = "✅" if enabled else "❌"
    return InlineKeyboardButton(f"{state} {label}", callback_data=callback)


def notification_kb(cfg) -> InlineKeyboardMarkup:
    n = cfg["Notifications"]
    kb = InlineKeyboardMarkup(row_width=1)
    items = [
        ("new_message", "Новое сообщение"),
        ("payment", "Оплата"),
        ("order_confirm", "Подтверждение заказа"),
        ("review", "Отзыв"),
        ("bot_start", "Запуск бота"),
        ("plugin_message", "Сообщения плагинов"),
    ]
    for key, label in items:
        enabled = n.get(key, "1") == "1"
        kb.add(toggle_button(label, f"{CBT.NOTIF_TOGGLE}:{key}", enabled))
    kb.add(InlineKeyboardButton("◀️ Назад", callback_data=CBT.BACK_MAIN))
    return kb


def global_settings_kb(cfg) -> InlineKeyboardMarkup:
    g = cfg["Global"]
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(toggle_button("Автоподнятие", f"{CBT.GLOBAL_TOGGLE}:auto_bump", g.get("auto_bump", "0") == "1"))
    kb.add(toggle_button("Автоответчик", f"{CBT.GLOBAL_TOGGLE}:auto_response", g.get("auto_response", "0") == "1"))
    if g.get("auto_response", "0") == "1":
        kb.add(InlineKeyboardButton("✏️ Приветствие", callback_data=f"{CBT.GLOBAL_EDIT}:greeting_text"))
        kb.add(InlineKeyboardButton("✏️ Подтверждение заказа", callback_data=f"{CBT.GLOBAL_EDIT}:order_confirm_text"))
        kb.add(InlineKeyboardButton("✏️ Ответ на отзыв", callback_data=f"{CBT.GLOBAL_EDIT}:review_text"))
    kb.add(InlineKeyboardButton("◀️ Назад", callback_data=CBT.BACK_MAIN))
    return kb


def configs_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("⬆️ Загрузить _main.txt", callback_data=f"{CBT.CONFIG_UPLOAD}:main"))
    kb.add(InlineKeyboardButton("⬆️ Загрузить auto_delivery.txt", callback_data=f"{CBT.CONFIG_UPLOAD}:delivery"))
    kb.add(InlineKeyboardButton("⬆️ Загрузить auto_response.txt", callback_data=f"{CBT.CONFIG_UPLOAD}:response"))
    kb.add(InlineKeyboardButton("⬇️ Выгрузить _main.txt", callback_data=f"{CBT.CONFIG_DOWNLOAD}:main"))
    kb.add(InlineKeyboardButton("⬇️ Выгрузить auto_delivery.txt", callback_data=f"{CBT.CONFIG_DOWNLOAD}:delivery"))
    kb.add(InlineKeyboardButton("⬇️ Выгрузить commands.txt", callback_data=f"{CBT.CONFIG_DOWNLOAD}:commands"))
    kb.add(InlineKeyboardButton("◀️ Назад", callback_data=CBT.BACK_MAIN))
    return kb
