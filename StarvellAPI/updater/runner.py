from __future__ import annotations

import concurrent.futures
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
        self._chat_baselines: set[str] = set()
        self._last_notified: dict[str, str] = {}
        self._seen_orders: set[str] = set()
        self._last_order_status: dict[str, str] = {}
        self._seen_reviews: set[str] = set()
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="StarvellPoll")
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

    def _dispatch(self, event_type: str, event) -> None:
        for handler in self._handlers.get(event_type, []):
            threading.Thread(
                target=self._safe_call,
                args=(handler, event, event_type),
                daemon=True,
            ).start()

    def _safe_call(self, handler: Callable, event, event_type: str) -> None:
        try:
            handler(event)
        except Exception as e:
            logger.error(f"$ERRORОшибка обработчика {event_type}: {e}")

    def start(self) -> None:
        if self.running:
            return
        self.running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="StarvellRunner")
        self._thread.start()
        logger.info("$SYSTEMМониторинг чатов Starvell запущен")

    def stop(self) -> None:
        self.running = False
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _run_with_deadline(self, fn, *args, name: str = "", deadline: float = 25.0, **kwargs):
        """Выполняет fn в пуле потоков с жёстким общим дедлайном.
        Защищает от зависаний requests, которые не ловятся обычным timeout=
        (timeout у requests относится к отдельной операции чтения, а не к запросу целиком)."""
        future = self._executor.submit(fn, *args, **kwargs)
        try:
            return future.result(timeout=deadline)
        except concurrent.futures.TimeoutError:
            logger.error(f"$ERROR{name} завис дольше {deadline} сек — пропускаем итерацию")
            return None

    def _loop(self) -> None:
        first = True
        error_count = 0
        iteration = 0
        while self.running:
            iteration += 1
            if iteration % 30 == 0:
                logger.info(f"$DEBUG Runner alive, iteration={iteration}, threads={threading.active_count()}")
            try:
                self._run_with_deadline(self._poll_messages, baseline=first, name="poll_messages")
                self._run_with_deadline(self._poll_orders, baseline=first, name="poll_orders")
                first = False
                error_count = 0
            except Exception as e:
                error_count += 1
                if error_count <= 3 or error_count % 10 == 0:
                    logger.error(f"$ERRORОшибка мониторинга: {e}", exc_info=True)
                time.sleep(min(self.poll_interval * error_count, 60))
                continue
            time.sleep(self.poll_interval)

    def _poll_messages(self, baseline: bool = False) -> None:
        try:
            chats = fetch_chats(self.account)
        except Exception as e:
            logger.error(f"$ERRORОшибка получения чатов: {type(e).__name__}: {e}")
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

            self._dispatch("new_message", event)

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
                self._dispatch("payment", payment_event)

                new_order_event = NewOrderEvent(
                    order_id=order_id, username=username, lot_title=lot, price=price, raw=order
                )
                logger.info(f"$CLIENTНовый заказ #{order_id}: {lot}")
                self._dispatch("new_order", new_order_event)

            if status in confirmed_statuses and prev_status not in confirmed_statuses:
                chat_id = ""
                try:
                    details = self.account.fetch_order_details(order_id)
                    chat_id = (details.get("chat") or {}).get("id", "")
                except Exception as e:
                    logger.debug(f"$ERRORНе удалось получить chat_id заказа #{order_id}: {e}")

                confirm_event = OrderConfirmEvent(order_id=order_id, username=username, raw={**order, "chatId": chat_id})
                logger.info(f"$CLIENTПодтверждение заказа #{order_id}")
                self._dispatch("order_confirm", confirm_event)

            if order.get("sellerCompletedAt") and order_id not in self._seen_reviews:
                try:
                    details = self.account.fetch_order_details(order_id)
                    review = details.get("review")
                except Exception as e:
                    review = None
                    details = {}
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
                    self._dispatch("review", review_event)