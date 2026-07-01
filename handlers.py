"""
Встроенные обработчики событий LSB.
"""
from __future__ import annotations

import logging

from StarvellAPI.updater.events import (
    NewMessageEvent,
    NewOrderEvent,
    OrderConfirmEvent,
    PaymentEvent,
    ReviewEvent,
)
from Utils.config_loader import load_commands_config
from Utils.variables import format_variables

logger = logging.getLogger("LSB")


def _notify(lsb, key: str, text: str) -> None:
    if lsb.tg_bot and lsb.main_cfg.get("Notifications", key, fallback="1") == "1":
        lsb.tg_bot.send_notification(text)


def _ctx(lsb, **kwargs) -> dict:
    account = lsb.account
    base = {
        "seller": account.username if account else "",
        "balance": account.balance if account else 0,
    }
    base.update(kwargs)
    return base


def on_new_message(lsb, event: NewMessageEvent) -> None:
    if lsb.tg_bot and lsb.main_cfg.get("Notifications", "new_message", fallback="1") == "1":
        lsb.tg_bot.send_new_message_notification(
            chat_id=event.chat_id,
            username=event.username,
            text=event.text,
            interlocutor_id=event.interlocutor_id,
        )

    if lsb.main_cfg.get("Global", "auto_response", fallback="0") != "1":
        return

    commands = load_commands_config()
    text_lower = event.text.strip().lower()
    for cmd_name, cmd_data in commands.items():
        if not cmd_data.get("enabled", True):
            continue
        trigger = cmd_data.get("trigger", cmd_name).lower()
        if text_lower == trigger or text_lower.startswith(trigger + " "):
            buyer_msg = format_variables(
                cmd_data.get("buyer_message", ""),
                _ctx(lsb, username=event.username, chat_id=event.chat_id),
            )
            if buyer_msg and lsb.account:
                ok = lsb.account.send_chat_message(event.chat_id, buyer_msg, event.interlocutor_id)
                if not ok:
                    logger.error(f"$ERRORНе удалось отправить buyer_message в чат {event.chat_id}")
            if cmd_data.get("notify_owner", True):
                owner_msg = format_variables(
                    cmd_data.get("owner_message", ""),
                    _ctx(lsb, username=event.username, chat_id=event.chat_id),
                )
                if owner_msg and lsb.tg_bot:
                    lsb.tg_bot.send_notification(f"{owner_msg}")

    greeting = lsb.main_cfg.get("Global", "greeting_text", fallback="")
    if greeting and lsb.account and event.is_new_chat:
        msg = format_variables(greeting, _ctx(lsb, username=event.username, chat_id=event.chat_id))
        lsb.account.send_chat_message(event.chat_id, msg, event.interlocutor_id)
        logger.info(f"$SUCCESSАвтоответ отправлен в чат {event.chat_id}")

def on_payment(lsb, event: PaymentEvent) -> None:
    amount = float(event.amount) / 100
    _notify(
        lsb,
        "payment",
        f"💰 <b>Оплата</b>\nЗаказ: #{event.order_id}\nПокупатель: {event.username}\nСумма: {amount:.2f} ₽",
    )

def on_new_order(lsb, event: NewOrderEvent) -> None:
    price = float(event.price) / 100
    _notify(
        lsb,
        "payment",
        f"🛒 <b>Новый заказ</b>\n#{event.order_id}\n{event.lot_title}\n{price:.2f} ₽ — {event.username}",
    )


def on_order_confirm(lsb, event: OrderConfirmEvent) -> None:
    _notify(lsb, "order_confirm", f"✅ <b>Подтверждение заказа</b>\n#{event.order_id} — {event.username}")
    if lsb.main_cfg.get("Global", "auto_response", fallback="0") == "1" and lsb.account:
        text = lsb.main_cfg.get("Global", "order_confirm_text", fallback="")
        if text:
            msg = format_variables(text, _ctx(lsb, username=event.username, order_id=event.order_id))
            chat_id = event.raw.get("chatId") or event.raw.get("chat_id")
            if chat_id:
                lsb.account.send_chat_message(str(chat_id), msg)


def on_review(lsb, event: ReviewEvent) -> None:
    _notify(
        lsb,
        "review",
        f"⭐ <b>Отзыв</b> ({event.rating}★)\n{event.username}: {event.text[:300]}",
    )
    if lsb.main_cfg.get("Global", "auto_response", fallback="0") == "1" and lsb.account:
        text = lsb.main_cfg.get("Global", "review_text", fallback="")
        if text:
            msg = format_variables(text, _ctx(lsb, username=event.username, order_id=event.order_id))
            chat_id = event.raw.get("chatId") or event.raw.get("chat_id")
            if chat_id:
                lsb.account.send_chat_message(str(chat_id), msg)
