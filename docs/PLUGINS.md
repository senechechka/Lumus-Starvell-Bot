# Инструкция по созданию плагинов LSB

## Обзор

Плагины — Python-файлы (`.py`) в папке `plugins/`. После добавления или изменения плагина **обязательно выполните `/restart`** в Telegram-боте.

## Структура плагина

```python
NAME = "Название плагина"
VERSION = "1.0.0"
DESCRIPTION = "Краткое описание"
CREDITS = "Автор (@username)"
UUID = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"  # UUID4

# Опционально
SETTINGS_PAGE = False

def my_handler(lsb, event=None):
    ...

BIND_TO_POST_START = [my_handler]
```

## Обязательные поля (токены)

| Поле | Описание |
|------|----------|
| `NAME` | Название плагина |
| `VERSION` | Версия (semver) |
| `DESCRIPTION` | Описание |
| `CREDITS` | Автор |
| `UUID` | Уникальный UUID4 |

Без этих полей плагин **не загрузится**.

## Разрешённые события (BIND_TO_*)

Только перечисленные ниже константы. Произвольные имена **игнорируются**.

| Константа | Когда вызывается | Аргументы handler |
|-----------|------------------|-------------------|
| `BIND_TO_PRE_INIT` | До инициализации LSB | `(lsb)` |
| `BIND_TO_POST_INIT` | После инициализации | `(lsb)` |
| `BIND_TO_PRE_START` | Перед стартом мониторинга | `(lsb)` |
| `BIND_TO_POST_START` | После старта | `(lsb)` |
| `BIND_TO_NEW_MESSAGE` | Новое сообщение от покупателя | `(lsb, event)` |
| `BIND_TO_NEW_ORDER` | Новый заказ | `(lsb, event)` |
| `BIND_TO_PAYMENT` | Оплата | `(lsb, event)` |
| `BIND_TO_ORDER_CONFIRM` | Подтверждение заказа | `(lsb, event)` |
| `BIND_TO_REVIEW` | Отзыв | `(lsb, event)` |
| `BIND_TO_DELETE` | Остановка бота | `(lsb)` |
| `BIND_TO_TELEGRAM_COMMANDS` | Регистрация TG-команд | `(lsb, tg_bot)` |
| `BIND_TO_PLUGIN_MENU` | Своё меню плагина в Telegram | `(lsb, tg_bot, chat_id, message_id, plugin_uuid)` |

### Сигнатура handler

```python
def handler(lsb, *args, **kwargs):
    # lsb — экземпляр LSB (ядро бота)
    # lsb.account — аккаунт Starvell
    # lsb.tg_bot — Telegram control panel
    # lsb.main_cfg — ConfigParser основного конфига
    pass
```

## События Starvell

- `NewMessageEvent`: `chat_id`, `username`, `text`, `interlocutor_id`
- `NewOrderEvent`: `order_id`, `username`, `lot_title`, `price`
- `PaymentEvent`: `order_id`, `username`, `amount`
- `OrderConfirmEvent`: `order_id`, `username`
- `ReviewEvent`: `order_id`, `username`, `rating`, `text`

## Telegram-команды из плагина

```python
def register_commands(lsb, tg_bot):
    @tg_bot.bot.message_handler(commands=["mycommand"])
    def cmd(msg):
        if tg_bot.auth.is_authorized(msg.from_user.id):
            tg_bot.bot.send_message(msg.chat.id, "Hello from plugin!")

BIND_TO_TELEGRAM_COMMANDS = [register_commands]
```

## Список команд плагина (COMMANDS)

Укажите команды, чтобы они отображались в карточке плагина:

```python
COMMANDS = [
    {"command": "mycommand", "description": "Описание команды"},
    ("other", "Альтернативный формат"),
]
```

## Своё меню плагина (BIND_TO_PLUGIN_MENU)

```python
def open_plugin_menu(lsb, tg_bot, chat_id, message_id, plugin_uuid):
    from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup
    from tg_bot.CBT import CBT

    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("◀️ Назад", callback_data=f"{CBT.PLUGIN_VIEW}:{plugin_uuid}"))
    tg_bot.bot.edit_message_text("Моё меню", chat_id, message_id, reply_markup=kb)

BIND_TO_PLUGIN_MENU = open_plugin_menu
```

Пользователь открывает его через: **Плагины → [плагин] → Меню плагина**.

## Отключение плагина без удаления

Первой строкой файла добавьте комментарий с `noplug`:

```python
# noplug
```

## Безопасность

- Не устанавливайте плагины из непроверенных источников
- Плагин получает доступ к session_token и Telegram-боту
- LSB выполняет только handlers из списков `BIND_TO_*`

## Пример

См. `plugins/example_plugin.py`
