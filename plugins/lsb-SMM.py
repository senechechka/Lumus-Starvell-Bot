from __future__ import annotations

import html
import json
import logging
import os
import re
import shutil
import threading
import time
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

import requests
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup

if TYPE_CHECKING:
    from lsb import LSB

NAME = "AutoSMM"
VERSION = "1.0.0"
DESCRIPTION = "Автоматическая накрутка через SMM-сервисы. Принимает заказы, запрашивает ссылку у покупателя и создаёт заказ в сервисе."
CREDITS = "LSB Team (адаптация с FunPay Cardinal @exfador)"
UUID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"

COMMANDS = [
    {"command": "smm",            "description": "Панель управления AutoSMM"},
    {"command": "smm_start",      "description": "Запустить AutoSMM"},
    {"command": "smm_stop",       "description": "Остановить AutoSMM"},
    {"command": "smm_status",     "description": "Статус AutoSMM"},
    {"command": "smm_delete",     "description": "Удалить файлы заказов"},
    {"command": "smm_help",       "description": "Справка по настройке лотов"},
]

CONFIG_PATH      = os.path.join("storage", "cache", "auto_smm_config.json")
ORDERS_PATH      = os.path.join("storage", "cache", "auto_smm_orders.json")
ORDERS_DATA_PATH = os.path.join("storage", "cache", "auto_smm_orders_data.json")
VALID_LINKS_PATH = os.path.join("storage", "cache", "auto_smm_valid_links.json")
LOG_DIR          = os.path.join("storage", "logs")
LOG_PATH         = os.path.join(LOG_DIR, "auto_smm.log")

for _p in (CONFIG_PATH, ORDERS_PATH, ORDERS_DATA_PATH, VALID_LINKS_PATH):
    os.makedirs(os.path.dirname(_p), exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

LOGGER_PREFIX = "[AutoSMM]"
logger = logging.getLogger("LSB.auto_smm")

_file_handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
_file_handler.setLevel(logging.ERROR)
_file_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
logger.addHandler(_file_handler)

RUNNING = False
_lsb_ref: "LSB | None" = None
_bot_ref = None
_tg_bot_ref = None

waiting_for_link: dict[str, dict] = {}
waiting_for_json_upload: set[int] = set()
lot_mapping: dict = {}

DEFAULT_CONFIG: dict[str, Any] = {
    "services": {
        "1": {
            "api_url": "https://twiboost.com/api/v2",
            "api_key": "YOUR_API_KEY_HERE"
        }
    },
    "lot_mapping": {},
    "auto_refunds": True,
    "confirm_link": True,
    "auto_start": True,
    "notification_chat_id": None,
    "messages": {
        "after_payment": (
            "⚫️ Благодарим за оплату! ⚫️\n\n"
            "Чтобы начать накрутку, отправьте корректную ссылку на вашу страницу или пост в социальных сетях.\n"
            "Ссылка должна начинаться с \"https://\"\n\n"
            "Пример: https://vk.com/your_page\n\n"
            "Без правильной ссылки накрутка не будет запущена."
        ),
        "after_confirmation": (
            "⚪️ Ваш заказ успешно оформлен! ⚪️\n\n"
            "⚪️ ID заказа в сервисе: {smm_order_id}\n"
            "🔗 Ссылка: {link} ⚪️\n\n"
            "📋 Доступные команды:\n"
            "🔍 !чек {smm_order_id} — Проверить статус заказа\n"
            "🔄 !рефилл {smm_order_id} — Запросить рефилл\n\n"
            "Если у вас возникнут вопросы, не стесняйтесь обращаться!"
        ),
    },
}

DEFAULT_VALID_LINKS = [
    "vk.com", "t.me", "instagram.com", "tiktok.com", "youtube.com",
    "youtu.be", "twitch.tv", "vt.tiktok.com", "vm.tiktok.com",
    "twitter.com", "x.com", "ok.ru",
]


def _load_config() -> dict:
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                content = f.read()
            if not content.strip():
                raise ValueError
            cfg = json.loads(content)
            for k, v in DEFAULT_CONFIG.items():
                if k not in cfg:
                    cfg[k] = v
            return cfg
        except Exception:
            pass
    cfg = dict(DEFAULT_CONFIG)
    _save_config(cfg)
    return cfg


def _save_config(cfg: dict) -> None:
    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    if os.path.exists(CONFIG_PATH):
        os.remove(CONFIG_PATH)
    os.rename(tmp, CONFIG_PATH)


def _load_orders_data() -> list[dict]:
    if not os.path.exists(ORDERS_DATA_PATH):
        return []
    try:
        with open(ORDERS_DATA_PATH, encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        backup = f"{ORDERS_DATA_PATH}.bak.{int(time.time())}"
        try:
            shutil.copy2(ORDERS_DATA_PATH, backup)
        except Exception:
            pass
        try:
            with open(ORDERS_DATA_PATH, encoding="utf-8") as f:
                content = f.read()
            last = content.rstrip().rfind("]")
            if last > 0:
                valid = content[:last + 1]
                parsed = json.loads(valid)
                with open(ORDERS_DATA_PATH, "w", encoding="utf-8") as f:
                    f.write(valid)
                return parsed
        except Exception:
            pass
        return []


def _save_orders_data(orders: list[dict]) -> None:
    tmp = ORDERS_DATA_PATH + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(orders, f, ensure_ascii=False, indent=2)
        if os.path.exists(ORDERS_DATA_PATH):
            os.remove(ORDERS_DATA_PATH)
        os.rename(tmp, ORDERS_DATA_PATH)
    except Exception as e:
        logger.error(f"Ошибка сохранения orders_data: {e}")
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except Exception:
                pass


def _load_orders_cache() -> list[dict]:
    if not os.path.exists(ORDERS_PATH):
        return []
    try:
        with open(ORDERS_PATH, encoding="utf-8") as f:
            content = f.read()
        if not content.strip():
            return []
        return json.loads(content)
    except Exception:
        return []


def _save_orders_cache(orders: list[dict]) -> None:
    tmp = ORDERS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(orders, f, ensure_ascii=False, indent=2)
    if os.path.exists(ORDERS_PATH):
        os.remove(ORDERS_PATH)
    os.rename(tmp, ORDERS_PATH)


def _save_order_entry(
    chat_id: str,
    order_id: str,
    smm_order_id: int,
    status: str,
    price: float,
    link: str,
    quantity: int,
    service_number: int,
) -> None:
    data = _load_orders_data()
    data = [o for o in data if str(o.get("order_id")) != str(order_id)]
    data.append({
        "chat_id": chat_id,
        "order_id": order_id,
        "id_zakaz": smm_order_id,
        "status": status,
        "summa": price,
        "chistota": price,
        "spent": 0.0,
        "customer_url": link,
        "quantity": quantity,
        "service_number": service_number,
        "is_refunded": False,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })
    _save_orders_data(data)

    cache = _load_orders_cache()
    cache = [o for o in cache if str(o.get("order_id")) != str(order_id)]
    cache.append({
        "order_id": order_id,
        "id_zakaz": smm_order_id,
        "completed_notification_sent": False,
    })
    _save_orders_cache(cache)


def _load_valid_links() -> list[str]:
    if os.path.exists(VALID_LINKS_PATH):
        try:
            with open(VALID_LINKS_PATH, encoding="utf-8") as f:
                links = json.load(f)
            if links:
                return links
        except Exception:
            pass
    _save_valid_links(list(DEFAULT_VALID_LINKS))
    return list(DEFAULT_VALID_LINKS)


def _save_valid_links(links: list[str]) -> None:
    with open(VALID_LINKS_PATH, "w", encoding="utf-8") as f:
        json.dump(links, f, ensure_ascii=False, indent=2)


def _is_valid_link(link: str) -> tuple[bool, str]:
    valid = _load_valid_links()
    if not link.startswith(("http://", "https://")):
        return False, "❌ Ссылка должна начинаться с http:// или https://"
    for domain in valid:
        if domain in link:
            return True, f"✅ Ссылка корректна ({domain})"
    return False, "❌ Недопустимая ссылка. Используйте поддерживаемую платформу."


def _reindex_lots(cfg: dict) -> None:
    lot_map = cfg.get("lot_mapping", {})
    sorted_lots = sorted(
        lot_map.items(),
        key=lambda x: int(x[0].split("_")[1]) if x[0].startswith("lot_") and x[0].split("_")[1].isdigit() else 0
    )
    new_map = {f"lot_{i}": v for i, (_, v) in enumerate(sorted_lots, start=1)}
    cfg["lot_mapping"] = new_map
    _save_config(cfg)
    lot_mapping.clear()
    lot_mapping.update(new_map)


def _find_lot(description: str, order_amount: int) -> tuple[int, int, int] | None:
    clean_desc = re.sub(r"[^\w\s-]", " ", description.lower()).strip()
    desc_words = [w for w in clean_desc.split() if len(w) > 2]

    for lot_key, lot_data in lot_mapping.items():
        lot_name = lot_data.get("name", "")
        clean_lot = re.sub(r"[^\w\s-]", " ", lot_name.lower()).strip()
        lot_words = [w for w in clean_lot.split() if len(w) > 2]

        matches = sum(
            1 for lw in lot_words
            if any(lw in dw or dw in lw for dw in desc_words)
        )
        if lot_words and matches >= max(1, len(lot_words) // 2):
            service_id = lot_data["service_id"]
            base_qty = lot_data.get("quantity", 1)
            real_qty = base_qty * order_amount
            srv_num = lot_data.get("service_number", 1)
            logger.info(f"{LOGGER_PREFIX} Лот найден: {lot_key} service_id={service_id} qty={real_qty}")
            return service_id, real_qty, srv_num

    logger.warning(f"{LOGGER_PREFIX} Лот не найден для '{description}'")
    return None


def _send_to_buyer(lsb: "LSB", chat_id: str, text: str, interlocutor_id: int | None = None) -> None:
    if lsb.account:
        lsb.account.send_chat_message(chat_id, text, interlocutor_id)

def _find_chat_for_buyer(lsb: "LSB", buyer_id) -> tuple[str, int | None]:
    """Ищет существующий чат с покупателем по его user id через список чатов Starvell."""
    if not buyer_id or not lsb.account:
        return "", None
    try:
        buyer_id_int = int(buyer_id)
    except (TypeError, ValueError):
        return "", None

    try:
        from StarvellAPI.chats import fetch_chats
        chats = fetch_chats(lsb.account)
    except Exception as e:
        logger.error(f"{LOGGER_PREFIX} Ошибка получения чатов для поиска покупателя: {e}")
        return "", None

    for chat in chats:
        if not isinstance(chat, dict):
            continue
        participants = chat.get("participants") or []
        for p in participants:
            if isinstance(p, dict) and p.get("id") is not None:
                try:
                    if int(p["id"]) == buyer_id_int:
                        chat_id = str(chat.get("id") or "")
                        if chat_id:
                            return chat_id, buyer_id_int
                except (TypeError, ValueError):
                    continue
    return "", None


def _notify_owner(text: str) -> None:
    if _tg_bot_ref:
        _tg_bot_ref.send_notification(text)


def _get_statistics() -> dict | None:
    if not os.path.exists(ORDERS_DATA_PATH):
        return None
    data = _load_orders_data()
    if not data:
        return None

    now = datetime.now()
    day_ago   = now - timedelta(days=1)
    week_ago  = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)

    def parse_dt(o):
        try:
            return datetime.strptime(o.get("date", ""), "%Y-%m-%d %H:%M:%S")
        except Exception:
            return datetime.min

    day_orders   = [o for o in data if parse_dt(o) >= day_ago]
    week_orders  = [o for o in data if parse_dt(o) >= week_ago]
    month_orders = [o for o in data if parse_dt(o) >= month_ago]

    def totals(lst):
        total   = sum(o.get("summa", 0) for o in lst)
        chistota = sum(o.get("chistota", o.get("summa", 0) - o.get("spent", 0)) for o in lst)
        return len(lst), round(total, 2), round(chistota, 2)

    dc, dt, dch = totals(day_orders)
    wc, wt, wch = totals(week_orders)
    mc, mt, mch = totals(month_orders)
    ac, at, ach = totals(data)

    return {
        "day_orders": dc, "day_total": dt, "day_chistota": dch,
        "week_orders": wc, "week_total": wt, "week_chistota": wch,
        "month_orders": mc, "month_total": mt, "month_chistota": mch,
        "all_time_orders": ac, "all_time_total": at, "all_time_chistota": ach,
    }


def _generate_lots_keyboard(page: int = 0) -> InlineKeyboardMarkup:
    cfg = _load_config()
    items = list(cfg.get("lot_mapping", {}).items())
    per_page = 10
    start = page * per_page
    end = start + per_page
    chunk = items[start:end]

    kb = InlineKeyboardMarkup(row_width=1)
    for lot_key, lot_data in chunk:
        name = lot_data.get("name", "?")
        sid  = lot_data.get("service_id", "?")
        qty  = lot_data.get("quantity", "?")
        snum = lot_data.get("service_number", 1)
        kb.add(InlineKeyboardButton(f"{name} [ID={sid}, Q={qty}, S={snum}]", callback_data=f"smm_edit_lot_{lot_key}"))

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️", callback_data=f"smm_prev_page_{page - 1}"))
    if end < len(items):
        nav.append(InlineKeyboardButton("➡️", callback_data=f"smm_next_page_{page + 1}"))
    if nav:
        kb.row(*nav)

    kb.add(InlineKeyboardButton("🔙 Назад", callback_data="smm_return_to_settings"))
    return kb


def _create_smm_order(
    lsb: "LSB",
    order_id: str,
    chat_id: str,
    interlocutor_id: int | None,
    service_id: int,
    quantity: int,
    link: str,
    price: float,
    service_number: int,
) -> None:
    cfg = _load_config()
    svc = cfg["services"].get(str(service_number))
    if not svc:
        _send_to_buyer(lsb, chat_id, "❌ Ошибка конфигурации сервиса. Обратитесь к продавцу.", interlocutor_id)
        return

    api_url = svc["api_url"]
    api_key = svc["api_key"]
    encoded_link = quote(link, safe="")
    url = f"{api_url}?action=add&service={service_id}&link={encoded_link}&quantity={quantity}&key={api_key}"

    logger.info(f"{LOGGER_PREFIX} Создаём заказ: service_id={service_id} qty={quantity} link={link}")

    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        logger.info(f"{LOGGER_PREFIX} Ответ API: {data}")

        if "order" in data:
            smm_order_id = data["order"]
            _save_order_entry(chat_id, order_id, smm_order_id, "pending", price, link, quantity, service_number)

            tpl = cfg["messages"].get("after_confirmation", "")
            msg = tpl.format(smm_order_id=smm_order_id, link=link)
            _send_to_buyer(lsb, chat_id, msg, interlocutor_id)

            notification_chat_id = cfg.get("notification_chat_id")
            if notification_chat_id and _bot_ref:
                kb = InlineKeyboardMarkup()
                kb.add(InlineKeyboardButton("Перейти к заказу", url=f"https://starvell.com/orders/{order_id}"))
                try:
                    _bot_ref.send_message(
                        notification_chat_id,
                        f"🚀 [AutoSMM] Заказ #{order_id} начат!\n\n"
                        f"📦 SMM ID: {smm_order_id}\n"
                        f"💰 Сумма: {price} ₽\n"
                        f"🔢 Кол-во: {quantity}\n"
                        f"🔗 Ссылка: {html.escape(link)}",
                        reply_markup=kb,
                    )
                except Exception as e:
                    logger.error(f"{LOGGER_PREFIX} Ошибка отправки уведомления: {e}")

            waiting_for_link.pop(str(order_id), None)

            threading.Thread(
                target=_check_order_status,
                args=(lsb, smm_order_id, chat_id, interlocutor_id, link, order_id, service_number),
                daemon=True,
            ).start()

        else:
            error = data.get("error", "Неизвестная ошибка")
            logger.error(f"{LOGGER_PREFIX} Ошибка API: {error}")

            if "not_enough_funds" in str(error):
                logger.error(f"{LOGGER_PREFIX} Недостаточно средств на балансе SMM панели!")
            elif "invalid_service" in str(error):
                logger.error(f"{LOGGER_PREFIX} Неверный ID услуги или услуга недоступна!")
            elif "invalid_key" in str(error):
                logger.error(f"{LOGGER_PREFIX} Неверный API ключ!")

            cfg2 = _load_config()
            notification_chat_id = cfg2.get("notification_chat_id")
            auto_refunds = cfg2.get("auto_refunds", True)

            if auto_refunds:
                _send_to_buyer(lsb, chat_id, f"❌ Ваши средства возвращены. Причина: ошибка при создании заказа.", interlocutor_id)
                if notification_chat_id and _bot_ref:
                    try:
                        _bot_ref.send_message(
                            notification_chat_id,
                            f"⚠️ Автоматический возврат для заказа #{order_id}.\nОшибка: {error}"
                        )
                    except Exception:
                        pass
            else:
                if notification_chat_id and _bot_ref:
                    try:
                        _bot_ref.send_message(
                            notification_chat_id,
                            f"⚠️ Требуется ручной возврат для заказа #{order_id}.\n"
                            f"Ссылка: https://starvell.com/orders/{order_id}\n"
                            f"Причина: {error}"
                        )
                    except Exception:
                        pass

    except requests.RequestException as e:
        logger.error(f"{LOGGER_PREFIX} Сетевая ошибка: {e}")
        _send_to_buyer(lsb, chat_id, "❌ Сетевая ошибка при создании заказа. Обратитесь к продавцу.", interlocutor_id)
    except Exception as e:
        logger.error(f"{LOGGER_PREFIX} Неизвестная ошибка: {e}")
        _send_to_buyer(lsb, chat_id, "❌ Внутренняя ошибка. Обратитесь к продавцу.", interlocutor_id)


def _check_order_status(
    lsb: "LSB",
    smm_order_id: int,
    chat_id: str,
    interlocutor_id: int | None,
    link: str,
    order_id: str,
    service_number: int,
    attempt: int = 1,
) -> None:
    cache = _load_orders_cache()
    entry = next((o for o in cache if str(o.get("order_id")) == str(order_id)), None)
    if entry and entry.get("completed_notification_sent"):
        return

    cfg = _load_config()
    svc = cfg["services"].get(str(service_number))
    if not svc:
        return

    api_url = svc["api_url"]
    api_key = svc["api_key"]
    url = f"{api_url}?action=status&order={smm_order_id}&key={api_key}"

    completed_statuses = {"completed", "done", "success", "partial"}
    failed_statuses    = {"failed", "error", "canceled", "cancelled"}
    delay = 300

    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            status   = str(data.get("status", "")).lower()
            remains  = data.get("remains", None)
            charge   = float(data.get("charge", "0") or 0)
            currency = data.get("currency", "USD")

            logger.info(f"{LOGGER_PREFIX} Статус #{smm_order_id}: {status} (осталось: {remains})")

            try:
                remains_int = int(remains)
            except (TypeError, ValueError):
                remains_int = None

            if status in completed_statuses or (remains_int is not None and remains_int == 0):
                if entry:
                    for o in cache:
                        if str(o.get("order_id")) == str(order_id):
                            o["completed_notification_sent"] = True
                    _save_orders_cache(cache)

                orders_data = _load_orders_data()
                for o in orders_data:
                    if str(o.get("order_id")) == str(order_id):
                        o["status"] = "completed"
                        net = o.get("summa", 0) - charge
                        o["chistota"] = round(net, 2)
                        o["spent"] = charge
                        o["currency"] = currency
                _save_orders_data(orders_data)

                if lsb.account:
                    try:
                        lsb.account.mark_seller_completed(order_id)
                    except Exception as e:
                        logger.error(f"{LOGGER_PREFIX} Ошибка подтверждения заказа #{order_id}: {e}")

                _send_to_buyer(
                    lsb, chat_id,
                    f"🎉 Ваш заказ успешно завершён!\n"
                    f"🔢 Номер заказа: {smm_order_id}\n"
                    f"🔗 Подтвердите заказ: https://starvell.com/orders/{order_id}/",
                    interlocutor_id,
                )
                return

            elif status in failed_statuses:
                cfg2 = _load_config()
                auto_refunds = cfg2.get("auto_refunds", True)
                notification_chat_id = cfg2.get("notification_chat_id")

                if auto_refunds:
                    _send_to_buyer(lsb, chat_id, f"❌ Ваши средства возвращены. Заказ не выполнен.", interlocutor_id)
                    if notification_chat_id and _bot_ref:
                        try:
                            _bot_ref.send_message(
                                notification_chat_id,
                                f"⚠️ Автоматический возврат для заказа #{order_id}.\n"
                                f"Статус в сервисе: {status}"
                            )
                        except Exception:
                            pass
                else:
                    if notification_chat_id and _bot_ref:
                        try:
                            _bot_ref.send_message(
                                notification_chat_id,
                                f"⚠️ Требуется ручной возврат для заказа #{order_id}.\n"
                                f"https://starvell.com/orders/{order_id}/\n"
                                f"Статус: {status}"
                            )
                        except Exception:
                            pass
                return

            else:
                delay = 300

        elif resp.status_code == 429:
            delay = 3600
        else:
            delay = 300

    except Exception as e:
        logger.error(f"{LOGGER_PREFIX} Ошибка проверки #{smm_order_id}: {e}")
        delay = min(300 * (2 ** (attempt - 1)), 3600)

    logger.info(f"{LOGGER_PREFIX} Повтор #{smm_order_id} через {delay} сек")
    threading.Timer(
        delay,
        _check_order_status,
        args=(lsb, smm_order_id, chat_id, interlocutor_id, link, order_id, service_number, attempt + 1),
    ).start()


def _start_order_checking(lsb: "LSB") -> None:
    if not RUNNING:
        return
    data = _load_orders_data()
    cache = _load_orders_cache()
    for od in data:
        try:
            if od.get("status", "").lower() == "completed" or od.get("is_refunded"):
                continue
            entry = next((o for o in cache if str(o.get("order_id")) == str(od.get("order_id"))), None)
            if entry and entry.get("completed_notification_sent"):
                continue
            threading.Thread(
                target=_check_order_status,
                args=(lsb, od["id_zakaz"], od["chat_id"], None, od["customer_url"], od["order_id"], od.get("service_number", 1)),
                daemon=True,
            ).start()
            time.sleep(0.5)
        except Exception as e:
            logger.error(f"{LOGGER_PREFIX} Ошибка в start_order_checking: {e}")

def _check_active_orders_on_startup(lsb: "LSB") -> None:
    logger.info(f"{LOGGER_PREFIX} Запуск проверки активных заказов...")

    waited = 0
    while not lsb.account and waited < 60:
        time.sleep(1)
        waited += 1

    if not RUNNING:
        logger.info(f"{LOGGER_PREFIX} RUNNING=False, пропуск проверки")
        return
    if not lsb.account:
        logger.info(f"{LOGGER_PREFIX} lsb.account отсутствует даже после ожидания, пропуск")
        return

    try:
        orders = lsb.account.fetch_sells()
        logger.info(f"{LOGGER_PREFIX} Получено заказов: {len(orders)}")
    except Exception as e:
        logger.error(f"{LOGGER_PREFIX} Ошибка получения активных заказов при старте: {e}", exc_info=True)
        return

    existing_data = _load_orders_data()
    existing_ids = {str(o.get("order_id")) for o in existing_data}

    for order in orders:
        if not isinstance(order, dict):
            continue
        status = str(order.get("status") or "").upper()
        if status != "CREATED":
            continue

        order_id = str(order.get("id") or "")
        if not order_id:
            continue
        if order_id in existing_ids or order_id in waiting_for_link:
            continue

        logger.info(f"{LOGGER_PREFIX} Обнаружен необработанный активный заказ #{order_id}, запускаю обработку")

        user = order.get("user") or {}
        username = str(user.get("username") or "Покупатель")
        offer = order.get("offerDetails") or {}
        descriptions = (offer.get("descriptions") or {}).get("rus") or {}
        lot_title = str(descriptions.get("briefDescription") or descriptions.get("description") or "")
        price = float(order.get("basePrice") or 0)

        fake_event = type("FakeOrderEvent", (), {
            "order_id": order_id,
            "lot_title": lot_title,
            "price": price,
            "username": username,
            "raw": order,
        })()

        on_new_order(lsb, fake_event)

def on_new_order(lsb: "LSB", event) -> None:
    if not RUNNING:
        return

    order_id = str(getattr(event, "order_id", ""))

    existing = _load_orders_data()
    if any(str(o.get("order_id")) == order_id for o in existing):
        logger.info(f"{LOGGER_PREFIX} Заказ #{order_id} уже обработан, пропуск")
        return
    if order_id in waiting_for_link:
        logger.info(f"{LOGGER_PREFIX} Заказ #{order_id} уже ожидает ссылку, пропуск")
        return

    lot_title  = str(getattr(event, "lot_title", ""))
    price      = float(getattr(event, "price", 0))
    username   = str(getattr(event, "username", ""))
    raw        = getattr(event, "raw", {}) or {}

    buyer_id = raw.get("buyerId") or (raw.get("user") or {}).get("id")
    chat_id, interlocutor_id = _find_chat_for_buyer(lsb, buyer_id)
    if interlocutor_id:
        try:
            interlocutor_id = int(interlocutor_id)
        except Exception:
            interlocutor_id = None
    order_amount = int(raw.get("quantity") or raw.get("amount") or 1)

    logger.info(f"{LOGGER_PREFIX} Новый заказ #{order_id}: '{lot_title}' x{order_amount} от {username}")

    result = _find_lot(lot_title, order_amount)
    if not result:
        logger.warning(f"{LOGGER_PREFIX} Лот не найден для заказа #{order_id}")
        cfg = _load_config()
        if cfg.get("new_order_notifications") and _bot_ref:
            notification_chat_id = cfg.get("notification_chat_id")
            if notification_chat_id:
                try:
                    _bot_ref.send_message(notification_chat_id, f"⚠️ Лот не найден для заказа #{order_id}: {lot_title}")
                except Exception:
                    pass
        return

    service_id, real_qty, service_number = result

    cfg = _load_config()
    tpl = cfg["messages"].get("after_payment", "")
    try:
        msg = tpl.format(
            buyer_username=username,
            orderDesc=lot_title,
            orderPrice=price,
            orderAmount=order_amount,
        )
    except KeyError:
        msg = "❤️ Спасибо за оплату! Укажите ссылку для запуска заказа."

    if chat_id:
        _send_to_buyer(lsb, chat_id, msg, interlocutor_id)

    waiting_for_link[str(order_id)] = {
        "buyer_id": interlocutor_id,
        "chat_id": chat_id,
        "interlocutor_id": interlocutor_id,
        "service_id": service_id,
        "real_amount": real_qty,
        "order_id": order_id,
        "price": price,
        "service_number": service_number,
        "step": "await_link",
    }

    logger.info(f"{LOGGER_PREFIX} Заказ #{order_id} ожидает ссылку от покупателя")


def on_new_message(lsb: "LSB", event) -> None:
    if not RUNNING:
        return

    text           = str(getattr(event, "text", "")).strip()
    chat_id        = str(getattr(event, "chat_id", ""))
    interlocutor_id = getattr(event, "interlocutor_id", None)

    m_check = re.match(r"^!чек\s+(\d+)$", text.lower())
    if m_check:
        order_num = m_check.group(1)
        data = _load_orders_data()
        found = next((o for o in data if str(o.get("id_zakaz")) == order_num), None)
        if not found:
            _send_to_buyer(lsb, chat_id, "❌ Заказ не найден в базе.", interlocutor_id)
            return
        cfg = _load_config()
        svc = cfg["services"].get(str(found.get("service_number", 1)))
        if not svc:
            _send_to_buyer(lsb, chat_id, "❌ Ошибка конфигурации сервиса.", interlocutor_id)
            return
        try:
            url = f"{svc['api_url']}?action=status&order={order_num}&key={svc['api_key']}"
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            rdata = resp.json()
            st  = rdata.get("status", "неизв.")
            rm  = rdata.get("remains", "неизв.")
            ch  = rdata.get("charge", "неизв.")
            cur = rdata.get("currency", "неизв.")
            _send_to_buyer(lsb, chat_id, f"📊 Статус заказа #{order_num}:\n🔄 {st}\n⏳ Осталось: {rm}\n💸 Списано: {ch} {cur}", interlocutor_id)
        except Exception:
            _send_to_buyer(lsb, chat_id, "❌ Ошибка при проверке статуса.", interlocutor_id)
        return

    m_refill = re.match(r"^!рефилл\s+(\d+)$", text.lower())
    if m_refill:
        order_num = m_refill.group(1)
        _send_to_buyer(lsb, chat_id, "🔄 Запрашиваю рефилл...", interlocutor_id)
        data = _load_orders_data()
        found = next((o for o in data if str(o.get("id_zakaz")) == order_num), None)
        if not found:
            _send_to_buyer(lsb, chat_id, "❌ Заказ не найден в базе.", interlocutor_id)
            return
        cfg = _load_config()
        svc = cfg["services"].get(str(found.get("service_number", 1)))
        if not svc:
            _send_to_buyer(lsb, chat_id, "❌ Ошибка конфигурации сервиса.", interlocutor_id)
            return
        try:
            url = f"{svc['api_url']}?action=refill&order={order_num}&key={svc['api_key']}"
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            rdata = resp.json()
            st = rdata.get("status", 0)
            if str(st) in ("1", "true"):
                _send_to_buyer(lsb, chat_id, "✅ Рефилл успешно запущен.", interlocutor_id)
            else:
                _send_to_buyer(lsb, chat_id, f"❌ Рефилл отклонён (status={st}).", interlocutor_id)
        except Exception:
            _send_to_buyer(lsb, chat_id, "❌ Ошибка при запросе рефилла.", interlocutor_id)
        return

    for order_id, entry in waiting_for_link.items():
        if str(entry.get("chat_id")) != str(chat_id):
            continue

        if entry["step"] == "await_link":
            m_link = re.search(r"(https?://\S+)", text)
            if not m_link:
                _send_to_buyer(lsb, chat_id, "❌ Неверная ссылка, повторите...", interlocutor_id)
                return
            link = m_link.group(0)
            ok, reason = _is_valid_link(link)
            if not ok:
                _send_to_buyer(lsb, chat_id, reason, interlocutor_id)
                return
            entry["link"] = link
            cfg = _load_config()
            if cfg.get("confirm_link", True):
                entry["step"] = "await_confirm"
                _send_to_buyer(lsb, chat_id, f"✅ Ссылка принята: {link}\nПодтвердите: + / -", interlocutor_id)
            else:
                threading.Thread(
                    target=_create_smm_order,
                    args=(lsb, order_id, entry["chat_id"], entry.get("interlocutor_id"),
                          entry["service_id"], entry["real_amount"], link, entry["price"], entry["service_number"]),
                    daemon=True,
                ).start()
            return

        elif entry["step"] == "await_confirm":
            if text.lower() == "+":
                link = entry.get("link", "")
                threading.Thread(
                    target=_create_smm_order,
                    args=(lsb, order_id, entry["chat_id"], entry.get("interlocutor_id"),
                          entry["service_id"], entry["real_amount"], link, entry["price"], entry["service_number"]),
                    daemon=True,
                ).start()
            elif text.lower() == "-":
                entry["step"] = "await_link"
                _send_to_buyer(lsb, chat_id, "❌ Подтверждение отклонено. Введите другую ссылку.", interlocutor_id)
            else:
                _send_to_buyer(lsb, chat_id, "❌ Используйте + или -. Повторите.", interlocutor_id)
            return


def register_commands(lsb: "LSB", tg_bot) -> None:
    global _lsb_ref, _tg_bot_ref, _bot_ref, RUNNING, lot_mapping

    _lsb_ref    = lsb
    _tg_bot_ref = tg_bot
    _bot_ref    = tg_bot.bot

    cfg = _load_config()
    lot_mapping.clear()
    lot_mapping.update(cfg.get("lot_mapping", {}))

    if cfg.get("auto_start", True):
        RUNNING = True
        logger.info(f"{LOGGER_PREFIX} Автозапуск включён, запускаем проверку незавершённых заказов")
        threading.Thread(target=_start_order_checking, args=(lsb,), daemon=True).start()
        threading.Thread(target=_check_active_orders_on_startup, args=(lsb,), daemon=True).start()

    bot = tg_bot.bot

    @bot.message_handler(commands=["smm"])
    def cmd_smm(msg):
        if not tg_bot.auth.is_authorized(msg.from_user.id):
            return
        _send_smm_main(bot, msg.chat.id, None)

    @bot.message_handler(commands=["smm_start"])
    def cmd_smm_start(msg):
        if not tg_bot.auth.is_authorized(msg.from_user.id):
            return
        global RUNNING
        if RUNNING:
            bot.send_message(msg.chat.id, "✅ AutoSMM уже запущен.")
            return
        RUNNING = True
        threading.Thread(target=_start_order_checking, args=(lsb,), daemon=True).start()
        bot.send_message(msg.chat.id, "✅ AutoSMM успешно запущен.")
        logger.info(f"{LOGGER_PREFIX} Запущен вручную")

    @bot.message_handler(commands=["smm_stop"])
    def cmd_smm_stop(msg):
        if not tg_bot.auth.is_authorized(msg.from_user.id):
            return
        global RUNNING
        if not RUNNING:
            bot.send_message(msg.chat.id, "❌ AutoSMM не запущен.")
            return
        RUNNING = False
        bot.send_message(msg.chat.id, "🛑 AutoSMM остановлен.")
        logger.info(f"{LOGGER_PREFIX} Остановлен вручную")

    @bot.message_handler(commands=["smm_status"])
    def cmd_smm_status(msg):
        if not tg_bot.auth.is_authorized(msg.from_user.id):
            return
        cfg2 = _load_config()
        lots   = len(cfg2.get("lot_mapping", {}))
        orders = _load_orders_data()
        active = sum(1 for o in orders if o.get("status") != "completed" and not o.get("is_refunded"))
        bot.send_message(
            msg.chat.id,
            f"🔍 <b>Статус AutoSMM</b>\n\n"
            f"{'🟢 Запущен' if RUNNING else '🔴 Остановлен'}\n"
            f"🏷 Лотов: <code>{lots}</code>\n"
            f"📦 Активных заказов: <code>{active}</code>\n"
            f"⏳ Ожидают ссылки: <code>{len(waiting_for_link)}</code>\n"
            f"🔧 lot_mapping: <code>{len(lot_mapping)}</code> лотов",
            parse_mode="HTML",
        )

    @bot.message_handler(commands=["smm_delete"])
    def cmd_smm_delete(msg):
        if not tg_bot.auth.is_authorized(msg.from_user.id):
            return
        for p in (ORDERS_PATH, ORDERS_DATA_PATH):
            if os.path.exists(p):
                os.remove(p)
        bot.send_message(msg.chat.id, "✅ Файлы заказов успешно удалены.")

    @bot.message_handler(commands=["smm_help"])
    def cmd_smm_help(msg):
        if not tg_bot.auth.is_authorized(msg.from_user.id):
            return
        bot.send_message(msg.chat.id, _lot_help_text(), parse_mode="HTML")

    @bot.message_handler(
        func=lambda m: tg_bot.user_states.get(m.from_user.id, {}).get("state", "").startswith("smm_"),
        content_types=["text"],
    )
    def smm_text_handler(msg):
        if not tg_bot.auth.is_authorized(msg.from_user.id):
            return
        sd = tg_bot.user_states.get(msg.from_user.id, {})
        state = sd.get("state", "")
        _handle_smm_state(bot, tg_bot, msg, state, sd, lsb)

    @bot.message_handler(
        func=lambda m: m.from_user.id in waiting_for_json_upload,
        content_types=["document"],
    )
    def smm_json_upload(msg):
        if not tg_bot.auth.is_authorized(msg.from_user.id):
            return
        user_id = msg.from_user.id
        waiting_for_json_upload.discard(user_id)
        file_info = bot.get_file(msg.document.file_id)
        content   = bot.download_file(file_info.file_path)
        try:
            data = json.loads(content.decode("utf-8"))
            if "lot_mapping" not in data:
                bot.send_message(msg.chat.id, "❌ В файле нет ключа 'lot_mapping'.")
                return
            _save_config(data)
            lot_mapping.clear()
            lot_mapping.update(data.get("lot_mapping", {}))
            kb = InlineKeyboardMarkup()
            kb.add(InlineKeyboardButton("🔙 Назад", callback_data="smm_return_to_settings"))
            bot.send_message(msg.chat.id, "✅ Конфиг успешно загружен и сохранён!", reply_markup=kb)
        except json.JSONDecodeError as e:
            bot.send_message(msg.chat.id, f"❌ Ошибка JSON: {e}")
        except Exception as e:
            bot.send_message(msg.chat.id, f"❌ Ошибка при загрузке файла: {e}")

    @bot.callback_query_handler(func=lambda c: c.data == "smm_return_to_settings")
    def cb_return_to_settings(call):
        if not tg_bot.auth.is_authorized(call.from_user.id):
            return
        _send_smm_main(bot, call.message.chat.id, call.message.message_id)
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data == "smm_toggle_run")
    def cb_toggle_run(call):
        if not tg_bot.auth.is_authorized(call.from_user.id):
            return
        global RUNNING
        RUNNING = not RUNNING
        if RUNNING:
            threading.Thread(target=_start_order_checking, args=(lsb,), daemon=True).start()
        bot.answer_callback_query(call.id, f"AutoSMM {'запущен ✅' if RUNNING else 'остановлен 🛑'}")
        _send_smm_main(bot, call.message.chat.id, call.message.message_id)

    @bot.callback_query_handler(func=lambda c: c.data == "smm_lot_settings")
    def cb_lot_settings(call):
        if not tg_bot.auth.is_authorized(call.from_user.id):
            return
        kb = InlineKeyboardMarkup(row_width=1)
        kb.add(InlineKeyboardButton("🔍 Поиск лота", callback_data="smm_search_lot"))
        kb.add(InlineKeyboardButton("📋 Список лотов", callback_data="smm_show_lots_list"))
        kb.add(InlineKeyboardButton("🗑 Удалить все лоты", callback_data="smm_delete_all_lots"))
        kb.add(InlineKeyboardButton("🔄 Переиндексировать лоты", callback_data="smm_reindex_lots"))
        kb.add(InlineKeyboardButton("🔙 Назад", callback_data="smm_return_to_settings"))
        try:
            bot.edit_message_text("🏷 <b>Управление лотами</b>", call.message.chat.id, call.message.message_id, parse_mode="HTML", reply_markup=kb)
        except Exception:
            bot.send_message(call.message.chat.id, "🏷 <b>Управление лотами</b>", parse_mode="HTML", reply_markup=kb)
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data == "smm_show_lots_list")
    def cb_show_lots_list(call):
        if not tg_bot.auth.is_authorized(call.from_user.id):
            return
        try:
            bot.edit_message_text("Выберите лот:", call.message.chat.id, call.message.message_id, reply_markup=_generate_lots_keyboard(0))
        except Exception:
            bot.send_message(call.message.chat.id, "Выберите лот:", reply_markup=_generate_lots_keyboard(0))
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data == "smm_search_lot")
    def cb_search_lot(call):
        if not tg_bot.auth.is_authorized(call.from_user.id):
            return
        tg_bot.user_states[call.from_user.id] = {"state": "smm_search_lot"}
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("🔙 Назад", callback_data="smm_lot_settings"))
        try:
            bot.edit_message_text("Введите название или часть названия лота для поиска:", call.message.chat.id, call.message.message_id, reply_markup=kb)
        except Exception:
            bot.send_message(call.message.chat.id, "Введите название или часть названия лота для поиска:", reply_markup=kb)
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data.startswith("smm_prev_page_") or c.data.startswith("smm_next_page_"))
    def cb_page_nav(call):
        if not tg_bot.auth.is_authorized(call.from_user.id):
            return
        try:
            page = int(call.data.split("_")[-1])
        except ValueError:
            page = 0
        try:
            bot.edit_message_text("Выберите лот:", call.message.chat.id, call.message.message_id, reply_markup=_generate_lots_keyboard(page))
        except Exception:
            pass
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data.startswith("smm_edit_lot_"))
    def cb_edit_lot(call):
        if not tg_bot.auth.is_authorized(call.from_user.id):
            return
        lot_key = call.data[len("smm_edit_lot_"):]
        _show_lot_detail(bot, call.message.chat.id, call.message.message_id, lot_key)
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data.startswith("smm_change_name_"))
    def cb_change_name(call):
        if not tg_bot.auth.is_authorized(call.from_user.id):
            return
        lot_key = call.data[len("smm_change_name_"):]
        tg_bot.user_states[call.from_user.id] = {"state": "smm_change_name", "lot_key": lot_key}
        try:
            bot.edit_message_text(f"Введите новое название для {lot_key}:", call.message.chat.id, call.message.message_id)
        except Exception:
            bot.send_message(call.message.chat.id, f"Введите новое название для {lot_key}:")
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data.startswith("smm_change_id_"))
    def cb_change_id(call):
        if not tg_bot.auth.is_authorized(call.from_user.id):
            return
        lot_key = call.data[len("smm_change_id_"):]
        tg_bot.user_states[call.from_user.id] = {"state": "smm_change_id", "lot_key": lot_key}
        try:
            bot.edit_message_text(f"Введите новый ID услуги для {lot_key}:", call.message.chat.id, call.message.message_id)
        except Exception:
            bot.send_message(call.message.chat.id, f"Введите новый ID услуги для {lot_key}:")
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data.startswith("smm_change_qty_"))
    def cb_change_qty(call):
        if not tg_bot.auth.is_authorized(call.from_user.id):
            return
        lot_key = call.data[len("smm_change_qty_"):]
        tg_bot.user_states[call.from_user.id] = {"state": "smm_change_qty", "lot_key": lot_key}
        try:
            bot.edit_message_text(f"Введите новое количество для {lot_key}:", call.message.chat.id, call.message.message_id)
        except Exception:
            bot.send_message(call.message.chat.id, f"Введите новое количество для {lot_key}:")
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data.startswith("smm_change_snum_"))
    def cb_change_snum(call):
        if not tg_bot.auth.is_authorized(call.from_user.id):
            return
        lot_key = call.data[len("smm_change_snum_"):]
        tg_bot.user_states[call.from_user.id] = {"state": "smm_change_snum", "lot_key": lot_key}
        try:
            bot.edit_message_text(f"Введите номер сервиса для {lot_key}:", call.message.chat.id, call.message.message_id)
        except Exception:
            bot.send_message(call.message.chat.id, f"Введите номер сервиса для {lot_key}:")
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data.startswith("smm_delete_one_lot_"))
    def cb_delete_one_lot(call):
        if not tg_bot.auth.is_authorized(call.from_user.id):
            return
        lot_key = call.data[len("smm_delete_one_lot_"):]
        cfg2 = _load_config()
        if lot_key in cfg2.get("lot_mapping", {}):
            del cfg2["lot_mapping"][lot_key]
            _reindex_lots(cfg2)
            try:
                bot.edit_message_text(f"✅ Лот {lot_key} удалён и лоты переиндексированы.", call.message.chat.id, call.message.message_id, reply_markup=_generate_lots_keyboard(0))
            except Exception:
                bot.send_message(call.message.chat.id, f"✅ Лот {lot_key} удалён.", reply_markup=_generate_lots_keyboard(0))
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data == "smm_return_to_lots")
    def cb_return_to_lots(call):
        if not tg_bot.auth.is_authorized(call.from_user.id):
            return
        try:
            bot.edit_message_text("Выберите лот:", call.message.chat.id, call.message.message_id, reply_markup=_generate_lots_keyboard(0))
        except Exception:
            bot.send_message(call.message.chat.id, "Выберите лот:", reply_markup=_generate_lots_keyboard(0))
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data == "smm_delete_all_lots")
    def cb_delete_all_lots(call):
        if not tg_bot.auth.is_authorized(call.from_user.id):
            return
        kb = InlineKeyboardMarkup()
        kb.add(
            InlineKeyboardButton("Да, удалить", callback_data="smm_confirm_delete_all"),
            InlineKeyboardButton("Нет, отменить", callback_data="smm_return_to_settings"),
        )
        try:
            bot.edit_message_text("Вы уверены, что хотите удалить все лоты?", call.message.chat.id, call.message.message_id, reply_markup=kb)
        except Exception:
            bot.send_message(call.message.chat.id, "Вы уверены?", reply_markup=kb)
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data == "smm_confirm_delete_all")
    def cb_confirm_delete_all(call):
        if not tg_bot.auth.is_authorized(call.from_user.id):
            return
        cfg2 = _load_config()
        preserved_svc  = cfg2.get("services", {})
        preserved_ncid = cfg2.get("notification_chat_id")
        new_cfg = dict(DEFAULT_CONFIG)
        new_cfg["services"] = preserved_svc
        new_cfg["notification_chat_id"] = preserved_ncid
        _save_config(new_cfg)
        lot_mapping.clear()
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("🔙 Назад", callback_data="smm_return_to_settings"))
        try:
            bot.edit_message_text("✅ Все лоты удалены. Сервисы и Chat ID сохранены.", call.message.chat.id, call.message.message_id, reply_markup=kb)
        except Exception:
            bot.send_message(call.message.chat.id, "✅ Все лоты удалены.", reply_markup=kb)
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data == "smm_reindex_lots")
    def cb_reindex_lots(call):
        if not tg_bot.auth.is_authorized(call.from_user.id):
            return
        cfg2 = _load_config()
        _reindex_lots(cfg2)
        bot.answer_callback_query(call.id, "✅ Лоты переиндексированы")
        _send_smm_main(bot, call.message.chat.id, call.message.message_id)

    @bot.callback_query_handler(func=lambda c: c.data == "smm_add_new_lot")
    def cb_add_new_lot(call):
        if not tg_bot.auth.is_authorized(call.from_user.id):
            return
        tg_bot.user_states[call.from_user.id] = {"state": "smm_lot_add_name"}
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except Exception:
            pass
        bot.send_message(call.message.chat.id, "Введите название лота (как оно указано в заказе Starvell):")
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data == "smm_api_settings")
    def cb_api_settings(call):
        if not tg_bot.auth.is_authorized(call.from_user.id):
            return
        _show_api_settings(bot, call.message.chat.id, call.message.message_id)
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data.startswith("smm_edit_apiurl_"))
    def cb_edit_apiurl(call):
        if not tg_bot.auth.is_authorized(call.from_user.id):
            return
        idx = call.data[len("smm_edit_apiurl_"):]
        tg_bot.user_states[call.from_user.id] = {"state": "smm_edit_apiurl", "srv_num": idx}
        try:
            bot.edit_message_text(f"Введите новый URL для сервиса #{idx}:", call.message.chat.id, call.message.message_id)
        except Exception:
            bot.send_message(call.message.chat.id, f"Введите новый URL для сервиса #{idx}:")
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data.startswith("smm_edit_apikey_"))
    def cb_edit_apikey(call):
        if not tg_bot.auth.is_authorized(call.from_user.id):
            return
        idx = call.data[len("smm_edit_apikey_"):]
        tg_bot.user_states[call.from_user.id] = {"state": "smm_edit_apikey", "srv_num": idx}
        try:
            bot.edit_message_text(f"Введите новый ключ для сервиса #{idx}:", call.message.chat.id, call.message.message_id)
        except Exception:
            bot.send_message(call.message.chat.id, f"Введите новый ключ для сервиса #{idx}:")
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data.startswith("smm_check_balance_"))
    def cb_check_balance(call):
        if not tg_bot.auth.is_authorized(call.from_user.id):
            return
        idx = call.data[len("smm_check_balance_"):]
        cfg2 = _load_config()
        svc = cfg2["services"].get(str(idx))
        if not svc:
            bot.answer_callback_query(call.id, f"Сервис #{idx} не найден")
            return
        try:
            url = f"{svc['api_url']}?action=balance&key={svc['api_key']}"
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            bal = data.get("balance", "0")
            kb = InlineKeyboardMarkup()
            kb.add(InlineKeyboardButton("🔙 К настройкам API", callback_data="smm_api_settings"))
            try:
                bot.edit_message_text(
                    f"💰 <b>Баланс сервиса #{idx}</b>\n\n"
                    f"• Текущий баланс: <code>{bal}</code>\n"
                    f"• Сервис: <code>{svc['api_url'].split('/')[2]}</code>\n"
                    f"• Время: <code>{datetime.now().strftime('%H:%M:%S')}</code>",
                    call.message.chat.id, call.message.message_id,
                    parse_mode="HTML", reply_markup=kb,
                )
            except Exception:
                bot.send_message(call.message.chat.id, f"💰 Баланс сервиса #{idx}: {bal}", reply_markup=kb)
        except requests.Timeout:
            kb = InlineKeyboardMarkup()
            kb.add(InlineKeyboardButton("🔄 Повторить", callback_data=f"smm_check_balance_{idx}"))
            kb.add(InlineKeyboardButton("🔙 Назад", callback_data="smm_api_settings"))
            try:
                bot.edit_message_text(f"⚠️ Таймаут сервиса #{idx}", call.message.chat.id, call.message.message_id, reply_markup=kb)
            except Exception:
                bot.send_message(call.message.chat.id, f"⚠️ Таймаут сервиса #{idx}", reply_markup=kb)
        except Exception as e:
            kb = InlineKeyboardMarkup()
            kb.add(InlineKeyboardButton("🔄 Повторить", callback_data=f"smm_check_balance_{idx}"))
            kb.add(InlineKeyboardButton("🔙 Назад", callback_data="smm_api_settings"))
            try:
                bot.edit_message_text(f"❌ Ошибка: <code>{str(e)[:100]}</code>", call.message.chat.id, call.message.message_id, parse_mode="HTML", reply_markup=kb)
            except Exception:
                bot.send_message(call.message.chat.id, f"❌ Ошибка: {e}", reply_markup=kb)
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data == "smm_add_service")
    def cb_add_service(call):
        if not tg_bot.auth.is_authorized(call.from_user.id):
            return
        tg_bot.user_states[call.from_user.id] = {"state": "smm_add_service"}
        try:
            bot.edit_message_text("Введите номер нового сервиса (число):", call.message.chat.id, call.message.message_id)
        except Exception:
            bot.send_message(call.message.chat.id, "Введите номер нового сервиса (число):")
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data == "smm_delete_service")
    def cb_delete_service(call):
        if not tg_bot.auth.is_authorized(call.from_user.id):
            return
        tg_bot.user_states[call.from_user.id] = {"state": "smm_delete_service"}
        try:
            bot.edit_message_text("Введите номер сервиса для удаления:", call.message.chat.id, call.message.message_id)
        except Exception:
            bot.send_message(call.message.chat.id, "Введите номер сервиса для удаления:")
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data == "smm_manage_websites")
    def cb_manage_websites(call):
        if not tg_bot.auth.is_authorized(call.from_user.id):
            return
        _show_websites(bot, call.message.chat.id, call.message.message_id)
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data == "smm_add_website")
    def cb_add_website(call):
        if not tg_bot.auth.is_authorized(call.from_user.id):
            return
        tg_bot.user_states[call.from_user.id] = {"state": "smm_add_website"}
        try:
            bot.edit_message_text("Введите домен для добавления (например: reddit.com):", call.message.chat.id, call.message.message_id)
        except Exception:
            bot.send_message(call.message.chat.id, "Введите домен для добавления:")
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data.startswith("smm_delete_website_"))
    def cb_delete_website(call):
        if not tg_bot.auth.is_authorized(call.from_user.id):
            return
        site = call.data[len("smm_delete_website_"):]
        links = _load_valid_links()
        if site in links:
            links.remove(site)
            _save_valid_links(links)
            bot.answer_callback_query(call.id, f"✅ {site} удалён")
        else:
            bot.answer_callback_query(call.id, f"❌ {site} не найден")
        _show_websites(bot, call.message.chat.id, call.message.message_id)

    @bot.callback_query_handler(func=lambda c: c.data == "smm_edit_messages")
    def cb_edit_messages(call):
        if not tg_bot.auth.is_authorized(call.from_user.id):
            return
        cfg2 = _load_config()
        mp = cfg2["messages"].get("after_payment", "")
        mc = cfg2["messages"].get("after_confirmation", "")
        kb = InlineKeyboardMarkup(row_width=1)
        kb.add(
            InlineKeyboardButton("Изменить текст после оплаты", callback_data="smm_edit_msg_payment"),
            InlineKeyboardButton("Изменить текст после подтверждения", callback_data="smm_edit_msg_confirm"),
        )
        kb.add(InlineKeyboardButton("🔙 Назад", callback_data="smm_return_to_settings"))
        try:
            bot.edit_message_text(
                f"⚙ <b>Шаблоны сообщений</b>\n\n"
                f"<b>После оплаты:</b>\n<code>{html.escape(mp[:200])}</code>\n\n"
                f"<b>После подтверждения:</b>\n<code>{html.escape(mc[:200])}</code>",
                call.message.chat.id, call.message.message_id, parse_mode="HTML", reply_markup=kb,
            )
        except Exception:
            bot.send_message(call.message.chat.id, "⚙ Шаблоны сообщений", reply_markup=kb)
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data == "smm_edit_msg_payment")
    def cb_edit_msg_payment(call):
        if not tg_bot.auth.is_authorized(call.from_user.id):
            return
        tg_bot.user_states[call.from_user.id] = {"state": "smm_edit_msg_payment"}
        try:
            bot.edit_message_text("Введите новый текст после оплаты:", call.message.chat.id, call.message.message_id)
        except Exception:
            bot.send_message(call.message.chat.id, "Введите новый текст после оплаты:")
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data == "smm_edit_msg_confirm")
    def cb_edit_msg_confirm(call):
        if not tg_bot.auth.is_authorized(call.from_user.id):
            return
        tg_bot.user_states[call.from_user.id] = {"state": "smm_edit_msg_confirm"}
        try:
            bot.edit_message_text("Введите новый текст после подтверждения ссылки:", call.message.chat.id, call.message.message_id)
        except Exception:
            bot.send_message(call.message.chat.id, "Введите новый текст после подтверждения:")
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data == "smm_files_menu")
    def cb_files_menu(call):
        if not tg_bot.auth.is_authorized(call.from_user.id):
            return
        kb = InlineKeyboardMarkup(row_width=2)
        kb.row(
            InlineKeyboardButton("📤 Экспорт файлов", callback_data="smm_export_files"),
            InlineKeyboardButton("📥 Загрузить JSON", callback_data="smm_upload_json"),
        )
        kb.row(
            InlineKeyboardButton("📝 Логи ошибок", callback_data="smm_export_errors"),
            InlineKeyboardButton("🗑 Удалить заказы", callback_data="smm_delete_orders_file"),
        )
        kb.add(InlineKeyboardButton("📊 Статистика", callback_data="smm_show_orders"))
        kb.add(InlineKeyboardButton("🔙 Назад", callback_data="smm_return_to_settings"))
        try:
            bot.edit_message_text("📁 <b>Бэкап и аналитика</b>", call.message.chat.id, call.message.message_id, parse_mode="HTML", reply_markup=kb)
        except Exception:
            bot.send_message(call.message.chat.id, "📁 Бэкап и аналитика", reply_markup=kb)
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data == "smm_show_orders")
    def cb_show_orders(call):
        if not tg_bot.auth.is_authorized(call.from_user.id):
            return
        stats = _get_statistics()
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("🔙 Назад", callback_data="smm_files_menu"))
        if not stats:
            try:
                bot.edit_message_text("❌ Нет данных о заказах.", call.message.chat.id, call.message.message_id, reply_markup=kb)
            except Exception:
                bot.send_message(call.message.chat.id, "❌ Нет данных о заказах.", reply_markup=kb)
            bot.answer_callback_query(call.id)
            return
        text = (
            f"📊 <b>Статистика заказов AutoSMM</b>\n\n"
            f"За 24 часа: {stats['day_orders']} заказов на {stats['day_total']} ₽ (чистая: {stats['day_chistota']} ₽)\n"
            f"За неделю: {stats['week_orders']} заказов на {stats['week_total']} ₽ (чистая: {stats['week_chistota']} ₽)\n"
            f"За месяц: {stats['month_orders']} заказов на {stats['month_total']} ₽ (чистая: {stats['month_chistota']} ₽)\n"
            f"За всё время: {stats['all_time_orders']} заказов на {stats['all_time_total']} ₽ (чистая: {stats['all_time_chistota']} ₽)"
        )
        try:
            bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="HTML", reply_markup=kb)
        except Exception:
            bot.send_message(call.message.chat.id, text, parse_mode="HTML", reply_markup=kb)
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data == "smm_export_files")
    def cb_export_files(call):
        if not tg_bot.auth.is_authorized(call.from_user.id):
            return
        for fpath in (CONFIG_PATH, ORDERS_PATH, ORDERS_DATA_PATH):
            if os.path.exists(fpath):
                try:
                    with open(fpath, "rb") as f:
                        bot.send_document(call.message.chat.id, f, caption=f"Файл: {os.path.basename(fpath)}")
                except Exception as e:
                    bot.send_message(call.message.chat.id, f"Ошибка отправки {fpath}: {e}")
            else:
                bot.send_message(call.message.chat.id, f"Файл не найден: {fpath}")
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data == "smm_export_errors")
    def cb_export_errors(call):
        if not tg_bot.auth.is_authorized(call.from_user.id):
            return
        if os.path.exists(LOG_PATH):
            try:
                with open(LOG_PATH, "rb") as f:
                    bot.send_document(call.message.chat.id, f, caption="Лог ошибок AutoSMM")
            except Exception as e:
                bot.send_message(call.message.chat.id, f"Ошибка отправки лога: {e}")
        else:
            bot.send_message(call.message.chat.id, "Лог-файл не найден.")
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data == "smm_delete_orders_file")
    def cb_delete_orders_file(call):
        if not tg_bot.auth.is_authorized(call.from_user.id):
            return
        for p in (ORDERS_PATH, ORDERS_DATA_PATH):
            if os.path.exists(p):
                os.remove(p)
        try:
            bot.edit_message_text("✅ Файлы заказов удалены.", call.message.chat.id, call.message.message_id)
        except Exception:
            bot.send_message(call.message.chat.id, "✅ Файлы заказов удалены.")
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data == "smm_upload_json")
    def cb_upload_json(call):
        if not tg_bot.auth.is_authorized(call.from_user.id):
            return
        waiting_for_json_upload.add(call.from_user.id)
        try:
            bot.edit_message_text("Пришлите файл JSON (auto_smm_config.json).", call.message.chat.id, call.message.message_id)
        except Exception:
            bot.send_message(call.message.chat.id, "Пришлите файл JSON.")
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data == "smm_misc_settings")
    def cb_misc_settings(call):
        if not tg_bot.auth.is_authorized(call.from_user.id):
            return
        _show_misc_settings(bot, call.message.chat.id, call.message.message_id)
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data in ("smm_toggle_auto_refunds", "smm_toggle_confirm_link", "smm_toggle_auto_start"))
    def cb_toggles(call):
        if not tg_bot.auth.is_authorized(call.from_user.id):
            return
        key_map = {
            "smm_toggle_auto_refunds":  "auto_refunds",
            "smm_toggle_confirm_link":  "confirm_link",
            "smm_toggle_auto_start":    "auto_start",
        }
        key = key_map[call.data]
        cfg2 = _load_config()
        cfg2[key] = not cfg2.get(key, True)
        _save_config(cfg2)
        bot.answer_callback_query(call.id, f"{'✅ Включено' if cfg2[key] else '❌ Выключено'}")
        _show_misc_settings(bot, call.message.chat.id, call.message.message_id)

    @bot.callback_query_handler(func=lambda c: c.data == "smm_set_notification_chat_id")
    def cb_set_notification_chat_id(call):
        if not tg_bot.auth.is_authorized(call.from_user.id):
            return
        tg_bot.user_states[call.from_user.id] = {"state": "smm_set_notif_chat_id"}
        try:
            bot.edit_message_text(
                f"Введите Chat ID для уведомлений (ваш ID: {call.message.chat.id}):",
                call.message.chat.id, call.message.message_id,
            )
        except Exception:
            bot.send_message(call.message.chat.id, "Введите Chat ID для уведомлений:")
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data == "smm_links_menu")
    def cb_links_menu(call):
        if not tg_bot.auth.is_authorized(call.from_user.id):
            return
        kb = InlineKeyboardMarkup(row_width=2)
        kb.row(
            InlineKeyboardButton("🌐 Twiboost", url="https://twiboost.com"),
            InlineKeyboardButton("🌐 Vexboost", url="https://vexboost.ru"),
        )
        kb.add(InlineKeyboardButton("🔙 Назад", callback_data="smm_return_to_settings"))
        try:
            bot.edit_message_text("📚 <b>Полезные ресурсы</b>", call.message.chat.id, call.message.message_id, parse_mode="HTML", reply_markup=kb)
        except Exception:
            bot.send_message(call.message.chat.id, "📚 Полезные ресурсы", reply_markup=kb)
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data == "smm_show_lot_help")
    def cb_show_lot_help(call):
        if not tg_bot.auth.is_authorized(call.from_user.id):
            return
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("🔙 Назад", callback_data="smm_return_to_settings"))
        try:
            bot.edit_message_text(_lot_help_text(), call.message.chat.id, call.message.message_id, parse_mode="HTML", reply_markup=kb)
        except Exception:
            bot.send_message(call.message.chat.id, _lot_help_text(), parse_mode="HTML", reply_markup=kb)
        bot.answer_callback_query(call.id)


def _handle_smm_state(bot, tg_bot, msg, state: str, sd: dict, lsb) -> None:
    chat_id = msg.chat.id
    text    = msg.text.strip() if msg.text else ""
    uid     = msg.from_user.id

    kb_back = InlineKeyboardMarkup()
    kb_back.add(InlineKeyboardButton("◀️ К лотам", callback_data="smm_return_to_lots"))

    if state == "smm_search_lot":
        tg_bot.user_states.pop(uid, None)
        if not text:
            bot.send_message(chat_id, "❌ Поисковый запрос не может быть пустым.")
            return
        cfg2 = _load_config()
        found = {k: v for k, v in cfg2.get("lot_mapping", {}).items() if text.lower() in v.get("name", "").lower()}
        if not found:
            kb = InlineKeyboardMarkup()
            kb.add(InlineKeyboardButton("🔍 Новый поиск", callback_data="smm_search_lot"))
            kb.add(InlineKeyboardButton("🔙 К настройкам лотов", callback_data="smm_lot_settings"))
            bot.send_message(chat_id, f"❌ Лоты с '{text}' не найдены.", reply_markup=kb)
            return
        kb = InlineKeyboardMarkup(row_width=1)
        for lot_key, lot_data in found.items():
            name = lot_data.get("name", "?")
            sid  = lot_data.get("service_id", "?")
            qty  = lot_data.get("quantity", "?")
            snum = lot_data.get("service_number", 1)
            kb.add(InlineKeyboardButton(f"{name} [ID={sid}, Q={qty}, S={snum}]", callback_data=f"smm_edit_lot_{lot_key}"))
        kb.add(InlineKeyboardButton("🔍 Новый поиск", callback_data="smm_search_lot"))
        kb.add(InlineKeyboardButton("🔙 К настройкам лотов", callback_data="smm_lot_settings"))
        bot.send_message(chat_id, f"🔍 Результаты поиска '{text}':", reply_markup=kb)

    elif state == "smm_lot_add_name":
        tg_bot.user_states[uid] = {"state": "smm_lot_add_service_id", "lot_name": text}
        bot.send_message(chat_id, "Введите ID услуги в SMM-сервисе (service_id, число):")

    elif state == "smm_lot_add_service_id":
        try:
            service_id = int(text)
        except ValueError:
            bot.send_message(chat_id, "❌ Введите целое число.")
            return
        tg_bot.user_states[uid].update({"state": "smm_lot_add_quantity", "service_id": service_id})
        bot.send_message(chat_id, "Введите базовое количество на 1 единицу заказа:")

    elif state == "smm_lot_add_quantity":
        try:
            qty = int(text)
        except ValueError:
            bot.send_message(chat_id, "❌ Введите целое число.")
            return
        tg_bot.user_states[uid].update({"state": "smm_lot_add_srvnum", "quantity": qty})
        cfg2 = _load_config()
        srv_list = ", ".join(f"#{k}" for k in cfg2["services"].keys())
        bot.send_message(chat_id, f"Введите номер сервиса ({srv_list}):")

    elif state == "smm_lot_add_srvnum":
        try:
            srv_num = int(text)
        except ValueError:
            bot.send_message(chat_id, "❌ Введите целое число.")
            return
        lot_data_saved = tg_bot.user_states.pop(uid, {})
        cfg2 = _load_config()
        lot_num = len(cfg2["lot_mapping"]) + 1
        lot_key = f"lot_{lot_num}"
        cfg2["lot_mapping"][lot_key] = {
            "name": lot_data_saved.get("lot_name", ""),
            "service_id": lot_data_saved.get("service_id", 0),
            "quantity": lot_data_saved.get("quantity", 1),
            "service_number": srv_num,
        }
        _save_config(cfg2)
        lot_mapping.update(cfg2["lot_mapping"])
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("◀️ К лотам", callback_data="smm_return_to_lots"))
        bot.send_message(
            chat_id,
            f"✅ Лот добавлен:\n"
            f"🏷 {lot_data_saved.get('lot_name')}\n"
            f"🔢 service_id={lot_data_saved.get('service_id')} qty={lot_data_saved.get('quantity')} сервис=#{srv_num}",
            reply_markup=kb,
        )

    elif state == "smm_change_name":
        lot_key = sd.get("lot_key", "")
        tg_bot.user_states.pop(uid, None)
        cfg2 = _load_config()
        if lot_key in cfg2.get("lot_mapping", {}):
            cfg2["lot_mapping"][lot_key]["name"] = text
            _save_config(cfg2)
            lot_mapping.update(cfg2["lot_mapping"])
            bot.send_message(chat_id, f"✅ Название {lot_key} изменено на {text}.", reply_markup=kb_back)
        else:
            bot.send_message(chat_id, f"❌ Лот {lot_key} не найден.", reply_markup=kb_back)

    elif state == "smm_change_id":
        lot_key = sd.get("lot_key", "")
        tg_bot.user_states.pop(uid, None)
        try:
            new_id = int(text)
        except ValueError:
            bot.send_message(chat_id, "❌ ID услуги должно быть числом.")
            return
        cfg2 = _load_config()
        if lot_key in cfg2.get("lot_mapping", {}):
            cfg2["lot_mapping"][lot_key]["service_id"] = new_id
            _save_config(cfg2)
            lot_mapping.update(cfg2["lot_mapping"])
            bot.send_message(chat_id, f"✅ ID услуги для {lot_key} изменён на {new_id}.", reply_markup=kb_back)
        else:
            bot.send_message(chat_id, f"❌ Лот {lot_key} не найден.", reply_markup=kb_back)

    elif state == "smm_change_qty":
        lot_key = sd.get("lot_key", "")
        tg_bot.user_states.pop(uid, None)
        try:
            new_qty = int(text)
        except ValueError:
            bot.send_message(chat_id, "❌ Количество должно быть числом.")
            return
        cfg2 = _load_config()
        if lot_key in cfg2.get("lot_mapping", {}):
            cfg2["lot_mapping"][lot_key]["quantity"] = new_qty
            _save_config(cfg2)
            lot_mapping.update(cfg2["lot_mapping"])
            bot.send_message(chat_id, f"✅ Количество для {lot_key} изменено на {new_qty}.", reply_markup=kb_back)
        else:
            bot.send_message(chat_id, f"❌ Лот {lot_key} не найден.", reply_markup=kb_back)

    elif state == "smm_change_snum":
        lot_key = sd.get("lot_key", "")
        tg_bot.user_states.pop(uid, None)
        try:
            new_snum = int(text)
        except ValueError:
            bot.send_message(chat_id, "❌ Номер сервиса должен быть числом.")
            return
        cfg2 = _load_config()
        if str(new_snum) not in cfg2.get("services", {}):
            bot.send_message(chat_id, f"❌ Сервис #{new_snum} не существует.")
            return
        if lot_key in cfg2.get("lot_mapping", {}):
            cfg2["lot_mapping"][lot_key]["service_number"] = new_snum
            _save_config(cfg2)
            lot_mapping.update(cfg2["lot_mapping"])
            bot.send_message(chat_id, f"✅ Номер сервиса для {lot_key} изменён на {new_snum}.", reply_markup=kb_back)
        else:
            bot.send_message(chat_id, f"❌ Лот {lot_key} не найден.", reply_markup=kb_back)

    elif state == "smm_edit_apiurl":
        tg_bot.user_states[uid].update({"state": "smm_edit_apikey_step"})
        tg_bot.user_states[uid]["api_url"] = text
        bot.send_message(chat_id, f"Введите API Key для сервиса #{sd.get('srv_num')}:")

    elif state == "smm_edit_apikey_step":
        srv_num = sd.get("srv_num", "1")
        api_url = sd.get("api_url", "")
        tg_bot.user_states.pop(uid, None)
        cfg2 = _load_config()
        cfg2["services"].setdefault(str(srv_num), {})
        cfg2["services"][str(srv_num)]["api_url"] = api_url
        cfg2["services"][str(srv_num)]["api_key"] = text
        _save_config(cfg2)
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("🔙 К настройкам API", callback_data="smm_api_settings"))
        bot.send_message(chat_id, f"✅ Сервис #{srv_num} обновлён.", reply_markup=kb)

    elif state == "smm_edit_apikey":
        srv_num = sd.get("srv_num", "1")
        tg_bot.user_states.pop(uid, None)
        cfg2 = _load_config()
        cfg2["services"].setdefault(str(srv_num), {})
        cfg2["services"][str(srv_num)]["api_key"] = text
        _save_config(cfg2)
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("🔙 К настройкам API", callback_data="smm_api_settings"))
        bot.send_message(chat_id, f"✅ API Key сервиса #{srv_num} обновлён.", reply_markup=kb)

    elif state == "smm_add_service":
        tg_bot.user_states.pop(uid, None)
        try:
            srv_num = int(text)
            if srv_num < 1:
                raise ValueError
        except ValueError:
            bot.send_message(chat_id, "❌ Номер сервиса должен быть положительным числом.")
            return
        cfg2 = _load_config()
        if str(srv_num) in cfg2["services"]:
            bot.send_message(chat_id, f"❌ Сервис #{srv_num} уже существует.")
            return
        cfg2["services"][str(srv_num)] = {"api_url": "https://example.com/api/v2", "api_key": "YOUR_API_KEY"}
        _save_config(cfg2)
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("🔙 К настройкам API", callback_data="smm_api_settings"))
        bot.send_message(chat_id, f"✅ Сервис #{srv_num} добавлен. Настройте его URL и ключ.", reply_markup=kb)

    elif state == "smm_delete_service":
        tg_bot.user_states.pop(uid, None)
        try:
            srv_num = int(text)
        except ValueError:
            bot.send_message(chat_id, "❌ Введите число.")
            return
        cfg2 = _load_config()
        if str(srv_num) not in cfg2["services"]:
            bot.send_message(chat_id, f"❌ Сервис #{srv_num} не существует.")
            return
        del cfg2["services"][str(srv_num)]
        _save_config(cfg2)
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("🔙 К настройкам API", callback_data="smm_api_settings"))
        bot.send_message(chat_id, f"✅ Сервис #{srv_num} удалён.", reply_markup=kb)

    elif state == "smm_add_website":
        tg_bot.user_states.pop(uid, None)
        domain = text.lower()
        links = _load_valid_links()
        if domain not in links:
            links.append(domain)
            _save_valid_links(links)
            bot.send_message(chat_id, f"✅ Сайт {domain} успешно добавлен.")
        else:
            bot.send_message(chat_id, f"❌ Сайт {domain} уже есть в списке.")

    elif state == "smm_edit_msg_payment":
        tg_bot.user_states.pop(uid, None)
        cfg2 = _load_config()
        cfg2["messages"]["after_payment"] = text
        _save_config(cfg2)
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("🔙 Назад", callback_data="smm_return_to_settings"))
        bot.send_message(chat_id, "✅ Текст после оплаты обновлён.", reply_markup=kb)

    elif state == "smm_edit_msg_confirm":
        tg_bot.user_states.pop(uid, None)
        cfg2 = _load_config()
        cfg2["messages"]["after_confirmation"] = text
        _save_config(cfg2)
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("🔙 Назад", callback_data="smm_return_to_settings"))
        bot.send_message(chat_id, "✅ Текст после подтверждения обновлён.", reply_markup=kb)

    elif state == "smm_set_notif_chat_id":
        tg_bot.user_states.pop(uid, None)
        try:
            new_chat_id = int(text)
        except ValueError:
            bot.send_message(chat_id, "❌ Введите корректный Chat ID (целое число).")
            return
        cfg2 = _load_config()
        cfg2["notification_chat_id"] = new_chat_id
        _save_config(cfg2)
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("🔙 К настройкам", callback_data="smm_return_to_settings"))
        bot.send_message(chat_id, f"✅ Chat ID установлен: {new_chat_id}", reply_markup=kb)


def _send_smm_main(bot, chat_id: int, msg_id: int | None) -> None:
    cfg = _load_config()
    lmap          = cfg.get("lot_mapping", {})
    auto_refunds  = cfg.get("auto_refunds", True)
    confirm_link  = cfg.get("confirm_link", True)
    auto_start    = cfg.get("auto_start", True)
    notif_chat_id = cfg.get("notification_chat_id", "Не задан")

    text = (
        f"⚫️ <b>AutoSMM v{VERSION} — Панель управления</b> ⚫️\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🚀 <b>Статус:</b> {'🟢 Запущен' if RUNNING else '🔴 Остановлен'}\n\n"
        f"💡 <b>Основные параметры:</b>\n"
        f" • Лотов в базе: <code>{len(lmap)}</code>\n"
        f" • Автовозвраты: {'✅' if auto_refunds else '❌'}\n"
        f" • Подтверждение ссылки: {'✅' if confirm_link else '❌'}\n"
        f" • Автозапуск: {'✅' if auto_start else '❌'}\n\n"
        f"📞 <b>Уведомления:</b> <code>{notif_chat_id}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━"
    )

    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("🛍️ Каталог лотов", callback_data="smm_lot_settings"),
        InlineKeyboardButton("➕ Создать новый лот", callback_data="smm_add_new_lot"),
    )
    kb.add(InlineKeyboardButton("🔌 Интеграция API", callback_data="smm_api_settings"))
    kb.add(
        InlineKeyboardButton("🌐 Доверенные сайты", callback_data="smm_manage_websites"),
        InlineKeyboardButton("💬 Шаблоны сообщений", callback_data="smm_edit_messages"),
    )
    kb.add(
        InlineKeyboardButton("📊 Бэкап и аналитика", callback_data="smm_files_menu"),
        InlineKeyboardButton("⚙️ Тонкая настройка", callback_data="smm_misc_settings"),
    )
    kb.add(InlineKeyboardButton("📚 Полезные ресурсы", callback_data="smm_links_menu"))
    kb.add(InlineKeyboardButton("❓ Справка по лотам", callback_data="smm_show_lot_help"))
    kb.add(InlineKeyboardButton(
        "🛑 Остановить" if RUNNING else "▶️ Запустить",
        callback_data="smm_toggle_run",
    ))

    if msg_id:
        try:
            bot.edit_message_text(text, chat_id, msg_id, parse_mode="HTML", reply_markup=kb)
            return
        except Exception:
            pass
    bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=kb)


def _show_lot_detail(bot, chat_id: int, msg_id: int, lot_key: str) -> None:
    cfg = _load_config()
    ld = cfg.get("lot_mapping", {}).get(lot_key)
    if not ld:
        try:
            bot.edit_message_text(f"❌ Лот {lot_key} не найден.", chat_id, msg_id)
        except Exception:
            bot.send_message(chat_id, f"❌ Лот {lot_key} не найден.")
        return

    text = (
        f"<b>{lot_key}</b>\n"
        f"Название: <code>{html.escape(ld.get('name', ''))}</code>\n"
        f"ID услуги: <code>{ld.get('service_id')}</code>\n"
        f"Кол-во: <code>{ld.get('quantity')}</code>\n"
        f"Сервис#: <code>{ld.get('service_number', 1)}</code>"
    )
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("Изменить название",   callback_data=f"smm_change_name_{lot_key}"),
        InlineKeyboardButton("Изменить ID услуги",  callback_data=f"smm_change_id_{lot_key}"),
        InlineKeyboardButton("Изменить количество", callback_data=f"smm_change_qty_{lot_key}"),
        InlineKeyboardButton("Изменить сервис#",    callback_data=f"smm_change_snum_{lot_key}"),
    )
    kb.add(InlineKeyboardButton("❌ Удалить лот", callback_data=f"smm_delete_one_lot_{lot_key}"))
    kb.add(InlineKeyboardButton("◀️ К списку",    callback_data="smm_return_to_lots"))
    try:
        bot.edit_message_text(text, chat_id, msg_id, parse_mode="HTML", reply_markup=kb)
    except Exception:
        bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=kb)


def _show_api_settings(bot, chat_id: int, msg_id: int) -> None:
    cfg = _load_config()
    services = cfg.get("services", {})
    lines = ["🔌 <b>Настройки API</b>\n"]
    kb = InlineKeyboardMarkup(row_width=2)
    for num, svc in services.items():
        url_short = svc.get("api_url", "")[:35]
        key_short = svc.get("api_key", "")[:8] + "..."
        lines.append(f"• Сервис #{num}:\n  <code>{html.escape(url_short)}</code>\n  Ключ: <code>{key_short}</code>")
        kb.row(
            InlineKeyboardButton(f"✏️ URL #{num}",  callback_data=f"smm_edit_apiurl_{num}"),
            InlineKeyboardButton(f"✏️ KEY #{num}",  callback_data=f"smm_edit_apikey_{num}"),
        )
        kb.add(InlineKeyboardButton(f"💰 Баланс #{num}", callback_data=f"smm_check_balance_{num}"))
    kb.row(
        InlineKeyboardButton("➕ Добавить сервис", callback_data="smm_add_service"),
        InlineKeyboardButton("➖ Удалить сервис",  callback_data="smm_delete_service"),
    )
    kb.add(InlineKeyboardButton("🔙 Назад", callback_data="smm_return_to_settings"))
    try:
        bot.edit_message_text("\n".join(lines), chat_id, msg_id, parse_mode="HTML", reply_markup=kb)
    except Exception:
        bot.send_message(chat_id, "\n".join(lines), parse_mode="HTML", reply_markup=kb)


def _show_websites(bot, chat_id: int, msg_id: int) -> None:
    links = _load_valid_links()
    kb = InlineKeyboardMarkup(row_width=2)
    for site in links:
        kb.add(
            InlineKeyboardButton(site, callback_data=f"smm_noop"),
            InlineKeyboardButton("Удалить", callback_data=f"smm_delete_website_{site}"),
        )
    kb.add(InlineKeyboardButton("➕ Добавить сайт", callback_data="smm_add_website"))
    kb.add(InlineKeyboardButton("🔙 Назад", callback_data="smm_return_to_settings"))
    try:
        bot.edit_message_text("🌐 <b>Доверенные сайты</b>", chat_id, msg_id, parse_mode="HTML", reply_markup=kb)
    except Exception:
        bot.send_message(chat_id, "🌐 Доверенные сайты", parse_mode="HTML", reply_markup=kb)


def _show_misc_settings(bot, chat_id: int, msg_id: int) -> None:
    cfg = _load_config()
    auto_refunds  = cfg.get("auto_refunds", True)
    confirm_link  = cfg.get("confirm_link", True)
    auto_start    = cfg.get("auto_start", True)
    notif_chat_id = cfg.get("notification_chat_id", "Не задан")

    text = (
        f"⚙️ <b>Тонкая настройка AutoSMM</b>\n\n"
        f"• Автовозвраты: {'✅ Включены' if auto_refunds else '❌ Выключены'}\n"
        f"• Подтверждение ссылки: {'✅ Включено' if confirm_link else '❌ Выключено'}\n"
        f"• Автозапуск плагина: {'✅ Включён' if auto_start else '❌ Выключен'}\n\n"
        f"📞 Chat ID для уведомлений: <code>{notif_chat_id}</code>"
    )
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton(f"🔄 {'Выключить' if auto_refunds else 'Включить'} автовозвраты", callback_data="smm_toggle_auto_refunds"),
        InlineKeyboardButton(f"✅ {'Выключить' if confirm_link else 'Включить'} подтверждение ссылки", callback_data="smm_toggle_confirm_link"),
        InlineKeyboardButton(f"🚀 {'Выключить' if auto_start else 'Включить'} автозапуск", callback_data="smm_toggle_auto_start"),
    )
    kb.add(InlineKeyboardButton("📩 Указать Chat ID для уведомлений", callback_data="smm_set_notification_chat_id"))
    kb.add(InlineKeyboardButton("🔙 Назад", callback_data="smm_return_to_settings"))
    try:
        bot.edit_message_text(text, chat_id, msg_id, parse_mode="HTML", reply_markup=kb)
    except Exception:
        bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=kb)


def _lot_help_text() -> str:
    return (
        "🔧 <b>Справка по настройке лотов</b>\n\n"
        "<b>Проблема:</b> Плагин не находит лоты из-за переменных количеств в заказах.\n\n"
        "✅ <b>ПРАВИЛЬНО:</b>\n"
        "• Название лота: «Подписчики Instagram»\n"
        "• Заказ: «Подписчики Instagram x2» → Лот найден ✅\n"
        "• Заказ: «Подписчики Instagram x100» → Лот найден ✅\n\n"
        "❌ <b>НЕПРАВИЛЬНО:</b>\n"
        "• Название лота: «Подписчики Instagram x1»\n"
        "• Заказ: «Подписчики Instagram x2» → Лот НЕ найден ❌\n\n"
        "<b>Рекомендации:</b>\n"
        "1. В названии лота указывайте ТОЛЬКО название услуги\n"
        "2. НЕ добавляйте количество в название лота\n"
        "3. Используйте ключевые слова, точно описывающие услугу\n"
        "4. Избегайте спецсимволов\n\n"
        "<b>Примеры:</b>\n"
        "• «Подписчики Instagram»\n"
        "• «Лайки ВКонтакте»\n"
        "• «Просмотры YouTube»\n"
        "• «Репосты TikTok»"
    )


BIND_TO_TELEGRAM_COMMANDS = [register_commands]
BIND_TO_NEW_ORDER         = [on_new_order]
BIND_TO_NEW_MESSAGE       = [on_new_message]
BIND_TO_DELETE            = None  