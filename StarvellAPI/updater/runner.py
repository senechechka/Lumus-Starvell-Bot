"""Polling-мониторинг событий Starvell."""
from __future__ import annotations

import logging
import threading
import time
from typing import Callable

from StarvellAPI.account import Account
from StarvellAPI.chats import (
    extract_interlocutor,
    fetch_chats,
    is_auto_message,
    message_author_id,
    message_text,
)
from StarvellAPI.updater.events import (
    NewMessageEvent,
    NewOrderEvent,
    OrderConfirmEvent,
    PaymentEvent,
    ReviewEvent,
)

logger = logging.getLogger("StarvellAPI")


class Runner:
    def __init__(self, account: Account, poll_interval: float = 4.0):
        self.account = account
        self.poll_interval = poll_interval
        self.running = False
        self._greeted_chats: set[str] = set()
        self._thread: threading.Thread | None = None
        self._seen_new_order: set[str] = set()
        self._seen_payment: set[str] = set()
        self._seen_confirm: set[str] = set()
        self._seen_messages: dict[str, set[str]]
        self._chat_baselines: set[str] = set()
        self._last_notified: dict[str, str] = {}
        self._seen_orders: set[str] = set()
        self._last_order_status: dict[str, str] = {}
        self._seen_reviews: set[str] = set()
        self._handlers: dict[str, list[Callable]] = {
            "new_message": [],
            "new_order": [],
            "payment": [],
            "order_confirm": [],
            "review": [],
        }

    def add_handler(self, event_type: str, handler: Callable) -> None:
        if event_type in self._handlers:
            self._handlers[event_type].append(handler)

    def start(self) -> None:
        if self.running:
            return
        self.running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="StarvellRunner")
        self._thread.start()
        logger.info("$SYSTEMМониторинг чатов Starvell запущен")

    def stop(self) -> None:
        self.running = False

    def _loop(self) -> None:
        first = True
        while self.running:
            try:
                self._poll_messages(baseline=first)
                self._poll_orders(baseline=first)
                first = False
            except Exception as e:
                logger.error(f"$ERRORОшибка мониторинга: {e}")
            time.sleep(self.poll_interval)

    def _poll_messages(self, baseline: bool = False) -> None:
        try:
            chats = fetch_chats(self.account)
        except Exception as e:
            logger.error(f"$ERRORОшибка получения чатов: {type(e).__name__}: {e}", exc_info=True)
            return

        if not chats:
            return

        my_id = self.account.user_id

        for chat in chats:
            chat_id = str(chat.get("id") or "")
            if not chat_id:
                continue

            last_msg = chat.get("lastMessage")
            if not isinstance(last_msg, dict):
                continue

            msg_id = str(last_msg.get("id") or "")
            if not msg_id:
                continue

            if baseline:
                self._chat_baselines.add(chat_id)
                self._greeted_chats.add(chat_id)
                self._last_notified[chat_id] = msg_id
                continue

            if self._last_notified.get(chat_id) == msg_id:
                continue

            if is_auto_message(last_msg):
                self._last_notified[chat_id] = msg_id
                continue

            author_id = message_author_id(last_msg)
            if my_id is not None and author_id is not None and author_id == my_id:
                self._last_notified[chat_id] = msg_id
                text = message_text(last_msg)
                username, _ = extract_interlocutor(chat, my_id)
                preview = text[:120] + ("…" if len(text) > 120 else "")
                logger.info(f"$SELLERМоё сообщение → {username} (чат {chat_id}): {preview}")
                continue

            self._last_notified[chat_id] = msg_id

            text = message_text(last_msg)
            username, interlocutor_id = extract_interlocutor(chat, my_id or 0)

            preview = text[:120] + ("…" if len(text) > 120 else "")
            logger.info(f"$CLIENTВходящее от {username} (чат {chat_id}): {preview}")

            is_new_chat = chat_id not in self._chat_baselines and chat_id not in self._greeted_chats
            if is_new_chat:
                self._greeted_chats.add(chat_id)

            event = NewMessageEvent(
                chat_id=chat_id,
                username=username,
                text=text,
                interlocutor_id=interlocutor_id,
                raw=chat,
                is_new_chat=is_new_chat,
            )

            for handler in self._handlers["new_message"]:
                try:
                    handler(event)
                except Exception as e:
                    logger.error(f"$ERRORОшибка обработчика new_message: {e}")

    def _poll_orders(self, baseline: bool = False) -> None:
        try:
            orders = self.account.fetch_sells()
        except Exception as e:
            logger.debug(f"$ERRORОшибка получения заказов: {e}")
            return

        if not orders:
            return

        confirmed_statuses = {"completed", "confirmed", "done", "finished"}

        for order in orders:
            if not isinstance(order, dict):
                continue
            order_id = str(order.get("id") or "")
            if not order_id:
                continue

            status = str(order.get("status") or "").lower()

            if baseline:
                self._seen_orders.add(order_id)
                self._last_order_status[order_id] = status
                continue

            user = order.get("user") or {}
            username = str(user.get("username") or "Покупатель")
            offer = order.get("offerDetails") or {}
            descriptions = (offer.get("descriptions") or {}).get("rus") or {}
            lot = str(descriptions.get("briefDescription") or descriptions.get("description") or "")
            price = float(order.get("basePrice") or 0)

            prev_status = self._last_order_status.get(order_id)
            is_new = order_id not in self._seen_orders
            self._seen_orders.add(order_id)
            self._last_order_status[order_id] = status

            if is_new:
                payment_event = PaymentEvent(order_id=order_id, username=username, amount=price, raw=order)
                for handler in self._handlers["payment"]:
                    try:
                        handler(payment_event)
                    except Exception as e:
                        logger.error(f"$ERRORОшибка обработчика payment: {e}")

                new_order_event = NewOrderEvent(
                    order_id=order_id, username=username, lot_title=lot, price=price, raw=order
                )
                for handler in self._handlers["new_order"]:
                    try:
                        handler(new_order_event)
                    except Exception as e:
                        logger.error(f"$ERRORОшибка обработчика new_order: {e}")

            if status in confirmed_statuses and prev_status not in confirmed_statuses:
                event = OrderConfirmEvent(order_id=order_id, username=username, raw=order)
                for handler in self._handlers["order_confirm"]:
                    try:
                        handler(event)
                    except Exception as e:
                        logger.error(f"$ERRORОшибка обработчика order_confirm: {e}")

            if order.get("sellerCompletedAt") and order_id not in self._seen_reviews:
                try:
                    details = self.account.fetch_order_details(order_id)
                    review = details.get("review")
                except Exception as e:
                    review = None
                    logger.debug(f"$ERRORОшибка проверки отзыва #{order_id}: {e}")

                if review:
                    self._seen_reviews.add(order_id)
                    chat_id = (details.get("chat") or {}).get("id", "")
                    review_event = ReviewEvent(
                        order_id=order_id,
                        username=username,
                        rating=int(review.get("rating") or 5),
                        text=str(review.get("content") or ""),
                        raw={**order, "chatId": chat_id},
                    )
                    logger.info(f"$CLIENTОтзыв от {username} ({review_event.rating}★): {review_event.text}")
                    for handler in self._handlers["review"]:
                        try:
                            handler(review_event)
                        except Exception as e:
                            logger.error(f"$ERRORОшибка обработчика review: {e}")