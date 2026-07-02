# Инструкция по созданию плагинов LSB

## Обзор

Плагины — Python-файлы (`.py`) в папке `plugins/`. После добавления или изменения плагина **обязательно выполните `/restart`** в Telegram-боте.

Загрузить плагин можно через Telegram: **Меню → Плагины → Добавить плагин** — отправьте `.py` файл боту, он проверит его валидность и уведомит об успехе.

---

## Структура плагина

```python
NAME = "Название плагина"
VERSION = "1.0.0"
DESCRIPTION = "Краткое описание"
CREDITS = "Автор (@username)"
UUID = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"  # UUID4

COMMANDS = [
    {"command": "mycommand", "description": "Описание команды"},
]

def my_handler(lsb, event=None):
    ...

BIND_TO_POST_START = [my_handler]
```

---

## Обязательные поля

| Поле | Описание |
|------|----------|
| `NAME` | Название плагина |
| `VERSION` | Версия (semver) |
| `DESCRIPTION` | Описание |
| `CREDITS` | Автор |
| `UUID` | Уникальный UUID4 |

Без этих полей плагин **не загрузится**. UUID должен быть валидным UUID4 — сгенерируйте на [uuidgenerator.net](https://www.uuidgenerator.net/).

---

## Разрешённые события (BIND_TO_*)

Только перечисленные ниже константы. Произвольные имена **игнорируются**.

| Константа | Когда вызывается | Аргументы handler |
|-----------|------------------|-------------------|
| `BIND_TO_PRE_INIT` | До инициализации LSB | `(lsb)` |
| `BIND_TO_POST_INIT` | После инициализации | `(lsb)` |
| `BIND_TO_PRE_START` | Перед стартом мониторинга | `(lsb)` |
| `BIND_TO_POST_START` | После старта | `(lsb)` |
| `BIND_TO_NEW_MESSAGE` | Новое сообщение от покупателя | `(lsb, event: NewMessageEvent)` |
| `BIND_TO_NEW_ORDER` | Новый заказ | `(lsb, event: NewOrderEvent)` |
| `BIND_TO_PAYMENT` | Оплата | `(lsb, event: PaymentEvent)` |
| `BIND_TO_ORDER_CONFIRM` | Подтверждение заказа | `(lsb, event: OrderConfirmEvent)` |
| `BIND_TO_REVIEW` | Отзыв | `(lsb, event: ReviewEvent)` |
| `BIND_TO_DELETE` | Остановка бота | `(lsb)` |
| `BIND_TO_TELEGRAM_COMMANDS` | Регистрация TG-команд | `(lsb, tg_bot)` |
| `BIND_TO_PLUGIN_MENU` | Своё меню плагина в Telegram | `(lsb, tg_bot, chat_id, message_id, plugin_uuid)` |

### Сигнатура handler

```python
def handler(lsb, *args, **kwargs):
    # lsb — экземпляр LSB (ядро бота)
    # lsb.account   — аккаунт Starvell (методы ниже)
    # lsb.tg_bot    — Telegram-бот (методы ниже)
    # lsb.main_cfg  — ConfigParser основного конфига
    # lsb.plugins   — PluginManager
    pass
```

---

## События Starvell

### NewMessageEvent
```python
event.chat_id          # str  — ID чата
event.username         # str  — имя покупателя
event.text             # str  — текст сообщения
event.interlocutor_id  # int | None — ID покупателя
event.is_new_chat      # bool — первое сообщение в чате
event.raw              # dict — сырые данные чата
```

### NewOrderEvent
```python
event.order_id    # str   — ID заказа
event.username    # str   — имя покупателя
event.lot_title   # str   — название лота
event.price       # float — сумма в копейках (делить на 100 для рублей)
event.raw         # dict  — сырые данные заказа
```

### PaymentEvent
```python
event.order_id  # str   — ID заказа
event.username  # str   — имя покупателя
event.amount    # float — сумма в копейках (делить на 100 для рублей)
event.raw       # dict
```

### OrderConfirmEvent
```python
event.order_id  # str  — ID заказа
event.username  # str  — имя покупателя
event.raw       # dict
```

### ReviewEvent
```python
event.order_id  # str  — ID заказа
event.username  # str  — имя покупателя
event.rating    # int  — оценка (1–5)
event.text      # str  — текст отзыва
event.raw       # dict
```

> ⚠️ **Важно:** суммы в `price` и `amount` хранятся в **копейках**. Для отображения делите на 100: `price / 100`.

---

## Методы lsb.account

```python
# Отправить сообщение покупателю в чат
lsb.account.send_chat_message(chat_id: str, text: str, interlocutor_id: int | None = None) -> bool

# Обновить баланс и активные заказы
lsb.account.refresh_stats() -> None

# Получить список лотов и категорий
lsb.account.count_lots() -> tuple[int, int]  # (лотов, категорий)

# Получить категории для автоподнятия
lsb.account.get_categories_for_bump() -> list[dict]

# Поднять категории
lsb.account.bump_categories(game_id: int, category_ids: list[int]) -> dict

# Сделать возврат заказа покупателю
lsb.account.refund_order(order_id: str) -> bool

# Атрибуты аккаунта
lsb.account.username      # str  — имя пользователя
lsb.account.user_id       # int  — ID пользователя
lsb.account.balance       # float — баланс в рублях
lsb.account.active_orders # int  — активных заказов
lsb.account.cookies       # dict — куки сессии
lsb.account.user_agent    # str | None
lsb.account._session      # requests.Session для кастомных запросов
```

---

## Методы lsb.tg_bot

```python
# Отправить уведомление всем авторизованным пользователям
lsb.tg_bot.send_notification(text: str) -> None

# Отправить уведомление о новом сообщении с кнопками "Ответить" и "Открыть чат"
lsb.tg_bot.send_new_message_notification(
    chat_id: str,
    username: str,
    text: str,
    interlocutor_id: int | None
) -> None

# Отправить главное меню
lsb.tg_bot.send_main_menu(chat_id: int, message_id: int | None = None) -> None

# Объект telebot.TeleBot
lsb.tg_bot.bot

# Менеджер авторизации
lsb.tg_bot.auth.is_authorized(user_id: int) -> bool

# Состояния пользователей (для диалогов)
lsb.tg_bot.user_states: dict[int, dict]
```

---

## Telegram-команды из плагина

Команды регистрируются через `BIND_TO_TELEGRAM_COMMANDS`. Важно: хендлеры плагина регистрируются **до** основных хендлеров бота, поэтому команды работают корректно.

```python
def register_commands(lsb, tg_bot):
    bot = tg_bot.bot

    @bot.message_handler(commands=["mycommand"])
    def cmd(msg):
        if not tg_bot.auth.is_authorized(msg.from_user.id):
            return
        tg_bot.bot.send_message(msg.chat.id, "Hello from plugin!")

    # Callback-кнопки
    @bot.callback_query_handler(func=lambda c: c.data == "my_callback")
    def cb(call):
        if not tg_bot.auth.is_authorized(call.from_user.id):
            return
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, "Callback!")

BIND_TO_TELEGRAM_COMMANDS = [register_commands]
```

### Диалоги через user_states

Для многошаговых диалогов используйте `tg_bot.user_states`. Префикс состояния должен быть уникальным для вашего плагина.

```python
def register_commands(lsb, tg_bot):
    bot = tg_bot.bot

    @bot.message_handler(commands=["ask"])
    def cmd_ask(msg):
        if not tg_bot.auth.is_authorized(msg.from_user.id):
            return
        tg_bot.user_states[msg.from_user.id] = {"state": "myplugin_waiting_input"}
        bot.send_message(msg.chat.id, "Введите текст:")

    @bot.message_handler(
        func=lambda m: tg_bot.user_states.get(m.from_user.id, {}).get("state", "").startswith("myplugin_"),
        content_types=["text"],
    )
    def state_handler(msg):
        if not tg_bot.auth.is_authorized(msg.from_user.id):
            return
        state = tg_bot.user_states.pop(msg.from_user.id, {}).get("state", "")
        if state == "myplugin_waiting_input":
            bot.send_message(msg.chat.id, f"Вы ввели: {msg.text}")
```

---

## Список команд плагина (COMMANDS)

Команды отображаются в карточке плагина в Telegram (раздел **Плагины → [плагин] → Команды**):

```python
COMMANDS = [
    {"command": "mycommand", "description": "Описание команды"},
    {"command": "mycommand2", "description": "Другая команда"},
]
```

---

## Своё меню плагина (BIND_TO_PLUGIN_MENU)

Открывается через **Меню → Плагины → [плагин] → Меню плагина**.

```python
def open_plugin_menu(lsb, tg_bot, chat_id, message_id, plugin_uuid):
    from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup
    from tg_bot.CBT import CBT

    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("◀️ Назад", callback_data=f"{CBT.PLUGIN_VIEW}:{plugin_uuid}"))
    tg_bot.bot.edit_message_text("Моё меню", chat_id, message_id, reply_markup=kb)

BIND_TO_PLUGIN_MENU = open_plugin_menu
```

---

## Хранение данных плагина

Используйте папку `storage/` для хранения файлов плагина:

```python
import json, os

STORAGE_PATH = os.path.join("storage", "plugins", "myplugin_data.json")
os.makedirs(os.path.dirname(STORAGE_PATH), exist_ok=True)

def load_data() -> dict:
    if not os.path.exists(STORAGE_PATH):
        return {}
    with open(STORAGE_PATH, encoding="utf-8") as f:
        return json.load(f)

def save_data(data: dict) -> None:
    tmp = STORAGE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    if os.path.exists(STORAGE_PATH):
        os.remove(STORAGE_PATH)
    os.rename(tmp, STORAGE_PATH)
```

Рекомендуемая структура папок:
```
storage/
  plugins/      — данные плагинов (JSON, кэш)
  logs/         — логи плагинов
  cache/        — временные файлы
```

---

## Логирование

```python
import logging
logger = logging.getLogger("LSB.myplugin")

logger.info("Сообщение")
logger.warning("Предупреждение")
logger.error("Ошибка")

# Для записи ошибок в отдельный файл:
import os
LOG_PATH = os.path.join("storage", "logs", "myplugin.log")
_fh = logging.FileHandler(LOG_PATH, encoding="utf-8")
_fh.setLevel(logging.ERROR)
_fh.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
logger.addHandler(_fh)
```

---

## Отключение плагина без удаления

Первой строкой файла добавьте комментарий с `noplug`:

```python
# noplug
```

Или через меню: **Меню → Плагины → [плагин] → ❌ Выключен**.

---

## Полный пример плагина

```python
from __future__ import annotations
import logging
import os
import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lsb import LSB

NAME = "Example Plugin"
VERSION = "1.0.0"
DESCRIPTION = "Пример плагина для LSB. Отправляет приветствие новым покупателям."
CREDITS = "LSB Team"
UUID = "12345678-1234-1234-1234-123456789012"

COMMANDS = [
    {"command": "example", "description": "Пример команды"},
]

logger = logging.getLogger("LSB.example_plugin")
STORAGE_PATH = os.path.join("storage", "plugins", "example.json")
os.makedirs(os.path.dirname(STORAGE_PATH), exist_ok=True)


def on_new_message(lsb: "LSB", event) -> None:
    if not event.is_new_chat:
        return
    greeting = lsb.main_cfg.get("Global", "greeting_text", fallback="")
    if greeting and lsb.account:
        lsb.account.send_chat_message(event.chat_id, greeting, event.interlocutor_id)
        logger.info(f"Приветствие отправлено в чат {event.chat_id}")


def on_new_order(lsb: "LSB", event) -> None:
    price_rub = event.price / 100  # копейки -> рубли
    logger.info(f"Новый заказ #{event.order_id} от {event.username} на {price_rub:.2f} ₽")
    if lsb.tg_bot:
        lsb.tg_bot.send_notification(
            f"🛒 Новый заказ от {event.username}\n"
            f"💰 {price_rub:.2f} ₽\n"
            f"📦 {event.lot_title}"
        )


def register_commands(lsb: "LSB", tg_bot) -> None:
    bot = tg_bot.bot

    @bot.message_handler(commands=["example"])
    def cmd_example(msg):
        if not tg_bot.auth.is_authorized(msg.from_user.id):
            return
        bot.send_message(
            msg.chat.id,
            f"👤 Аккаунт: {lsb.account.username}\n"
            f"💰 Баланс: {lsb.account.balance:.2f} ₽\n"
            f"📦 Активных заказов: {lsb.account.active_orders}"
        )


def on_delete(lsb: "LSB") -> None:
    logger.info("Example Plugin выгружен")


BIND_TO_NEW_MESSAGE       = [on_new_message]
BIND_TO_NEW_ORDER         = [on_new_order]
BIND_TO_TELEGRAM_COMMANDS = [register_commands]
BIND_TO_DELETE            = on_delete
```

---

## Безопасность

- Не устанавливайте плагины из непроверенных источников
- Плагин получает полный доступ к session_token и Telegram-боту
- LSB выполняет только handlers из списков `BIND_TO_*`
- При загрузке плагина через бота он автоматически проверяется на наличие обязательных полей — если что-то отсутствует, файл удаляется и бот сообщает об ошибке