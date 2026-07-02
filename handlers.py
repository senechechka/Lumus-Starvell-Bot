"""
Встроенные обработчики событий LSB.
"""
from __future__ import annotations

import logging

from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup

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


def _notify_with_kb(lsb, key: str, text: str, kb: InlineKeyboardMarkup) -> None:
    if not lsb.tg_bot:
        return
    if lsb.main_cfg.get("Notifications", key, fallback="1") != "1":
        return
    for user_id in lsb.tg_bot.auth.authorized:
        try:
            lsb.tg_bot.bot.send_message(user_id, text, reply_markup=kb, parse_mode="HTML")
        except Exception as e:
            logger.warning(f"Не удалось отправить уведомление {user_id}: {e}")


def _order_kb(order_id: str, chat_id: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup()
    btn_refund = InlineKeyboardButton("↩️ Возврат", callback_data=f"refund:{order_id}")
    btn_chat   = InlineKeyboardButton("🔗 Открыть чат", url=f"https://starvell.com/chat/{chat_id}")
    kb.row(btn_refund, btn_chat)
    return kb


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
                    kb = InlineKeyboardMarkup()
                    kb.row(
                        InlineKeyboardButton("🔗 Открыть чат", url=f"https://starvell.com/chat/{event.chat_id}"),
                        InlineKeyboardButton("↩️ Ответить", callback_data=f"reply:{event.chat_id}:{event.interlocutor_id or ''}"),
                    )
                    for user_id in lsb.tg_bot.auth.authorized:
                        try:
                            lsb.tg_bot.bot.send_message(
                                user_id,
                                f"🤖 Команда «{cmd_name}»\n{owner_msg}",
                                reply_markup=kb,
                                parse_mode="HTML",
                            )
                        except Exception as e:
                            logger.warning(f"Не удалось отправить уведомление {user_id}: {e}")
            return

    greeting = lsb.main_cfg.get("Global", "greeting_text", fallback="")
    if greeting and lsb.account and event.is_new_chat:
        msg = format_variables(greeting, _ctx(lsb, username=event.username, chat_id=event.chat_id))
        lsb.account.send_chat_message(event.chat_id, msg, event.interlocutor_id)
        logger.info(f"$SUCCESSАвтоответ отправлен в чат {event.chat_id}")


def on_payment(lsb, event: PaymentEvent) -> None:
    amount = float(event.amount) / 100
    raw = getattr(event, "raw", {}) or {}
    chat_id = str(raw.get("chatId") or raw.get("chat_id") or "")
    order_id = event.order_id

    kb = InlineKeyboardMarkup()
    btn_refund = InlineKeyboardButton("↩️ Возврат", callback_data=f"refund:{order_id}")
    if chat_id:
        btn_chat = InlineKeyboardButton("🔗 Открыть чат", url=f"https://starvell.com/chat/{chat_id}")
        kb.row(btn_refund, btn_chat)
    else:
        kb.add(btn_refund)

    _notify_with_kb(
        lsb, "payment",
        f"💰 <b>Оплата</b>\nЗаказ: #{order_id}\nПокупатель: {event.username}\nСумма: {amount:.2f} ₽",
        kb,
    )


def on_new_order(lsb, event: NewOrderEvent) -> None:
    price = float(event.price) / 100
    raw = getattr(event, "raw", {}) or {}
    chat_id = str(raw.get("chatId") or raw.get("chat_id") or "")
    order_id = event.order_id

    kb = InlineKeyboardMarkup()
    btn_refund = InlineKeyboardButton("↩️ Возврат", callback_data=f"refund:{order_id}")
    if chat_id:
        btn_chat = InlineKeyboardButton("🔗 Открыть чат", url=f"https://starvell.com/chat/{chat_id}")
        kb.row(btn_refund, btn_chat)
    else:
        kb.add(btn_refund)

    _notify_with_kb(
        lsb, "payment",
        f"🛒 <b>Новый заказ</b>\n#{order_id}\n{event.lot_title}\n{price:.2f} ₽ — {event.username}",
        kb,
    )


def on_order_confirm(lsb, event: OrderConfirmEvent) -> None:
    chat_id = str(event.raw.get("chatId") or event.raw.get("chat_id") or "")
    order_id = event.order_id

    kb = InlineKeyboardMarkup()
    btn_refund = InlineKeyboardButton("↩️ Возврат", callback_data=f"refund:{order_id}")
    if chat_id:
        btn_chat = InlineKeyboardButton("🔗 Открыть чат", url=f"https://starvell.com/chat/{chat_id}")
        kb.row(btn_refund, btn_chat)
    else:
        kb.add(btn_refund)

    _notify_with_kb(
        lsb, "order_confirm",
        f"✅ <b>Подтверждение заказа</b>\n#{order_id} — {event.username}",
        kb,
    )

    if lsb.main_cfg.get("Global", "auto_response", fallback="0") == "1" and lsb.account:
        text = lsb.main_cfg.get("Global", "order_confirm_text", fallback="")
        if text and chat_id:
            msg = format_variables(text, _ctx(lsb, username=event.username, order_id=order_id))
            lsb.account.send_chat_message(chat_id, msg)


def on_review(lsb, event: ReviewEvent) -> None:
    stars = "⭐" * event.rating
    review_text = event.text[:300] if event.text else "Без комментария"
    _notify(
        lsb,
        "review",
        f"{stars} <b>Отзыв</b>\n{event.username}: {review_text}",
    )
    if lsb.main_cfg.get("Global", "auto_response", fallback="0") == "1" and lsb.account:
        text = lsb.main_cfg.get("Global", "review_text", fallback="")
        if text:
            msg = format_variables(text, _ctx(lsb, username=event.username, order_id=event.order_id))
            chat_id = event.raw.get("chatId") or event.raw.get("chat_id")
            if chat_id:
                lsb.account.send_chat_message(str(chat_id), msg)