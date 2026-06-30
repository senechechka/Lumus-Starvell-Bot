"""Advanced Profile Stat — плагин расширенной статистики для Lumus Starvell Bot."""
from __future__ import annotations

import json
import os
import time
import html
from logging import getLogger
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from lsb import LSB

NAME = "Advanced Profile Stat"
VERSION = "1.0.0"
DESCRIPTION = "Расширенная статистика аккаунта: продажи, лоты, заказы, баланс. Команда /advprofile."
CREDITS = "LSB Team"
UUID = "7e8d1fc4-cda0-4e7b-b9d1-3cff16a80bfd"

COMMANDS = [
    {"command": "advprofile", "description": "Расширенная статистика аккаунта"},
    {"command": "advlots",    "description": "Статистика лотов и категорий"},
    {"command": "advorders",  "description": "Статистика заказов по периодам"},
]

STORAGE_PATH = "storage/plugins/advProfileStat.json"
LOGGER_PREFIX = "[ADV_PROFILE_STAT]"
logger = getLogger("LSB.adv_profile_stat")

# ── Хранилище подтверждённых заказов ────────────────────────────────────────

_confirmed: dict[str, dict] = {}


def _load_storage() -> None:
    global _confirmed
    if not os.path.exists(STORAGE_PATH):
        return
    try:
        with open(STORAGE_PATH, encoding="utf-8") as f:
            _confirmed = json.load(f)
    except Exception:
        _confirmed = {}


def _save_storage() -> None:
    os.makedirs(os.path.dirname(STORAGE_PATH), exist_ok=True)
    with open(STORAGE_PATH, "w", encoding="utf-8") as f:
        json.dump(_confirmed, f, ensure_ascii=False, indent=2)


def _clean_old_entries() -> None:
    """Удаляем записи старше 48 часов."""
    now = time.time()
    stale = [oid for oid, e in _confirmed.items() if now - e.get("time", 0) > 172800]
    for oid in stale:
        del _confirmed[oid]


# ── Форматирование ───────────────────────────────────────────────────────────

def _fmt(n: float) -> str:
    if n == int(n):
        return f"{int(n):,}".replace(",", " ")
    return f"{n:,.2f}".replace(",", " ")


def _pending_withdraw() -> dict[str, float]:
    """Считаем сумму заказов которую ещё нельзя вывести, с разбивкой по ожиданию."""
    now = time.time()
    buckets: dict[str, float] = {"soon": 0.0, "day": 0.0, "later": 0.0}
    for entry in _confirmed.values():
        elapsed = now - entry.get("time", 0)
        price = float(entry.get("price", 0))
        if elapsed > 172800:
            continue
        if elapsed > 169200:       # менее часа до разблокировки
            buckets["soon"] += price
        elif elapsed > 86400:      # 1–2 суток
            buckets["day"] += price
        else:                      # менее суток
            buckets["later"] += price
    return buckets


# ── Получение данных через реальный API ─────────────────────────────────────

def _fetch_orders(account) -> list[dict[str, Any]]:
    """Получаем последние заказы продавца через API Starvell."""
    try:
        from StarvellAPI.cookies import cookies_to_header
        from StarvellAPI.http_headers import api_headers
        headers = api_headers("https://starvell.com/orders", json=False)
        headers["cookie"] = cookies_to_header(account.cookies)
        if account.user_agent:
            headers["user-agent"] = account.user_agent
        resp = account._session.get(
            "https://starvell.com/api/orders/seller/recent",
            headers=headers,
            timeout=20,
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
        if isinstance(data, list):
            return data
        return data.get("items") or data.get("orders") or []
    except Exception as e:
        logger.warning(f"{LOGGER_PREFIX} Ошибка получения заказов: {e}")
        return []


def _parse_orders_stats(orders: list[dict]) -> dict:
    """Считаем продажи/возвраты/суммы по периодам из списка заказов."""
    now = time.time()
    result = {
        "sales":   {"day": 0, "week": 0, "month": 0, "all": 0},
        "revenue": {"day": 0.0, "week": 0.0, "month": 0.0, "all": 0.0},
        "refunds": {"day": 0, "week": 0, "month": 0, "all": 0},
        "refunds_sum": {"day": 0.0, "week": 0.0, "month": 0.0, "all": 0.0},
    }

    for order in orders:
        if not isinstance(order, dict):
            continue

        # Дата заказа — пробуем несколько полей
        ts = None
        for key in ("createdAt", "created_at", "date", "updatedAt"):
            val = order.get(key)
            if val:
                try:
                    if isinstance(val, (int, float)):
                        ts = float(val)
                    else:
                        import datetime
                        ts = datetime.datetime.fromisoformat(
                            str(val).replace("Z", "+00:00")
                        ).timestamp()
                    break
                except Exception:
                    pass

        if ts is None:
            continue

        age = now - ts
        price = float(order.get("price") or order.get("amount") or 0)
        status = str(order.get("status") or "").lower()
        is_refund = status in ("refunded", "cancelled", "canceled", "returned")

        periods = ["all"]
        if age < 86400:
            periods = ["day", "week", "month", "all"]
        elif age < 604800:
            periods = ["week", "month", "all"]
        elif age < 2592000:
            periods = ["month", "all"]

        if is_refund:
            for p in periods:
                result["refunds"][p] += 1
                result["refunds_sum"][p] += price
        else:
            for p in periods:
                result["sales"][p] += 1
                result["revenue"][p] += price

    return result

def generate_advprofile(lsb: "LSB") -> str:
    account = lsb.account
    _clean_old_entries()

    try:
        account.refresh_stats()
    except Exception:
        pass

    lots, categories = account.count_lots()
    orders = _fetch_orders(account)
    stats = _parse_orders_stats(orders)
    pending = _pending_withdraw()
    updated = time.strftime("%d.%m.%Y %H:%M:%S")

    s = stats["sales"]
    r = stats["revenue"]
    rf = stats["refunds"]
    rs = stats["refunds_sum"]

    username = html.escape(str(account.username or "—"))
    user_id = html.escape(str(account.user_id or "—"))

    return (
        f"👤 <b>Профиль: {username}</b>\n"
        f"🆔 ID: <code>{user_id}</code>\n\n"
        f"💰 <b>Баланс:</b> <code>{_fmt(account.balance)} ₽</code>\n"
        f"📦 <b>Активных заказов:</b> <code>{account.active_orders}</code>\n"
        f"🏷 <b>Лотов / категорий:</b> <code>{lots} / {categories}</code>\n\n"
        f"⏳ <b>Ожидают разблокировки:</b>\n"
        f"  · Скоро (&lt; 1 ч): <code>{_fmt(pending['soon'])} ₽</code>\n"
        f"  · Через ~1 день: <code>{_fmt(pending['day'])} ₽</code>\n"
        f"  · Через ~2 дня: <code>{_fmt(pending['later'])} ₽</code>\n\n"
        f"📈 <b>Продажи:</b>\n"
        f"  · День: <code>{s['day']} шт. / {_fmt(r['day'])} ₽</code>\n"
        f"  · Неделя: <code>{s['week']} шт. / {_fmt(r['week'])} ₽</code>\n"
        f"  · Месяц: <code>{s['month']} шт. / {_fmt(r['month'])} ₽</code>\n"
        f"  · Всё время: <code>{s['all']} шт. / {_fmt(r['all'])} ₽</code>\n\n"
        f"↩️ <b>Возвраты:</b>\n"
        f"  · День: <code>{rf['day']} шт. / {_fmt(rs['day'])} ₽</code>\n"
        f"  · Неделя: <code>{rf['week']} шт. / {_fmt(rs['week'])} ₽</code>\n"
        f"  · Месяц: <code>{rf['month']} шт. / {_fmt(rs['month'])} ₽</code>\n"
        f"  · Всё время: <code>{rf['all']} шт. / {_fmt(rs['all'])} ₽</code>\n\n"
        f"<i>🕒 Обновлено: {updated}</i>"
    )

def generate_advlots(lsb: "LSB") -> str:
    account = lsb.account
    try:
        cats = account._fetch_profile_offers()
    except Exception as e:
        return f"❌ Не удалось получить лоты: {e}"

    if not cats:
        return "📭 Лоты не найдены."

    lines = ["🏷 <b>Лоты по категориям</b>\n"]
    total_lots = 0
    for cat in cats:
        if not isinstance(cat, dict):
            continue
        cat_name = cat.get("name") or cat.get("title") or f"Категория {cat.get('id','?')}"
        offers = cat.get("offers") or []
        count = len([o for o in offers if isinstance(o, dict)])
        total_lots += count
        game = (cat.get("game") or {}).get("name") or ""
        game_str = f" ({game})" if game else ""
        lines.append(f"  · {cat_name}{game_str}: <code>{count} лот(ов)</code>")

    lines.append(f"\n<b>Итого лотов:</b> <code>{total_lots}</code>")
    lines.append(f"<b>Категорий:</b> <code>{len(cats)}</code>")
    return "\n".join(lines)


def generate_advorders(lsb: "LSB") -> str:
    orders = _fetch_orders(lsb.account)
    if not orders:
        return "📭 Заказов не найдено."

    stats = _parse_orders_stats(orders)
    s = stats["sales"]
    r = stats["revenue"]
    rf = stats["refunds"]
    rs = stats["refunds_sum"]

    # Конверсия (продажи / (продажи + возвраты))
    total = s["all"] + rf["all"]
    conv = f"{s['all'] / total * 100:.1f}%" if total > 0 else "—"

    return (
        f"📊 <b>Статистика заказов</b>\n\n"

        f"✅ <b>Продажи:</b>\n"
        f"  · День: <code>{s['day']} / {_fmt(r['day'])} ₽</code>\n"
        f"  · Неделя: <code>{s['week']} / {_fmt(r['week'])} ₽</code>\n"
        f"  · Месяц: <code>{s['month']} / {_fmt(r['month'])} ₽</code>\n"
        f"  · Всё время: <code>{s['all']} / {_fmt(r['all'])} ₽</code>\n\n"

        f"↩️ <b>Возвраты:</b>\n"
        f"  · День: <code>{rf['day']} / {_fmt(rs['day'])} ₽</code>\n"
        f"  · Неделя: <code>{rf['week']} / {_fmt(rs['week'])} ₽</code>\n"
        f"  · Месяц: <code>{rf['month']} / {_fmt(rs['month'])} ₽</code>\n"
        f"  · Всё время: <code>{rf['all']} / {_fmt(rs['all'])} ₽</code>\n\n"

        f"📉 <b>Конверсия (успешные):</b> <code>{conv}</code>\n"
        f"<i>🕒 {time.strftime('%d.%m.%Y %H:%M:%S')}</i>"
    )


# ── Регистрация Telegram-команд ──────────────────────────────────────────────

def register_commands(lsb: "LSB", tg_bot) -> None:
    _load_storage()

    def _send_stat(msg, generator_fn):
        wait = tg_bot.bot.send_message(msg.chat.id, "⏳ Собираю данные...")
        try:
            text = generator_fn(lsb)
            tg_bot.bot.edit_message_text(text, wait.chat.id, wait.message_id, parse_mode="HTML")
        except Exception as ex:
            logger.warning(f"{LOGGER_PREFIX} Ошибка генерации: {ex}", exc_info=True)
            tg_bot.bot.edit_message_text(
                f"❌ Ошибка: {ex}", wait.chat.id, wait.message_id
            )

    @tg_bot.bot.message_handler(commands=["advprofile"])
    def cmd_advprofile(msg):
        if not tg_bot.auth.is_authorized(msg.from_user.id):
            return
        _send_stat(msg, generate_advprofile)

    @tg_bot.bot.message_handler(commands=["advlots"])
    def cmd_advlots(msg):
        if not tg_bot.auth.is_authorized(msg.from_user.id):
            return
        _send_stat(msg, generate_advlots)

    @tg_bot.bot.message_handler(commands=["advorders"])
    def cmd_advorders(msg):
        if not tg_bot.auth.is_authorized(msg.from_user.id):
            return
        _send_stat(msg, generate_advorders)


# ── Обработчики событий ──────────────────────────────────────────────────────

def on_order_confirm(lsb: "LSB", event) -> None:
    """Сохраняем подтверждённый заказ для расчёта ожидания вывода."""
    order_id = str(getattr(event, "order_id", ""))
    if not order_id or order_id in _confirmed:
        return

    # Цену берём из raw если есть, иначе из event
    raw = getattr(event, "raw", {}) or {}
    price = float(
        raw.get("price") or raw.get("amount")
        or getattr(event, "amount", 0)
        or 0
    )

    _confirmed[order_id] = {
        "time": int(time.time()),
        "price": price,
    }
    _save_storage()
    logger.debug(f"{LOGGER_PREFIX} Подтверждён заказ {order_id}: {price} ₽")


# ── Привязки ─────────────────────────────────────────────────────────────────

BIND_TO_TELEGRAM_COMMANDS = [register_commands]
BIND_TO_ORDER_CONFIRM = [on_order_confirm]
