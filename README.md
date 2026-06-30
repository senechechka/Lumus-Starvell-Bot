# Lumus Starvell Bot (LSB)

Бот для автоматизации продаж на маркетплейсе [Starvell](https://starvell.com): автоответ, автоподнятие, уведомления в Telegram, плагины.

Архитектура вдохновлена [FunPay Cardinal](https://github.com/sidor0912/FunPayCardinal).

## Установка (Windows)

1. Установите [Python 3.11+](https://www.python.org/downloads/) с галочкой **Add to PATH**
2. Запустите `Setup.bat` — установит зависимости и сгенерирует логотип
3. Запустите `Start.bat` — первичная настройка конфига
4. Напишите боту `/start` и введите пароль

## Авторизация Starvell

Вместо golden_key FunPay используется **session_token** — cookie `session` с сайта starvell.com:

1. Войдите на starvell.com в браузере
2. DevTools → Application → Cookies → `session`
3. Скопируйте значение (или всю строку cookie) при первичной настройке

## Структура

```
├── main.py              # Точка входа
├── lsb.py               # Ядро бота
├── first_setup.py       # Первичная настройка
├── handlers.py          # Обработчики событий
├── plugin_manager.py    # Система плагинов
├── StarvellAPI/         # API клиент Starvell
├── tg_bot/              # Telegram control panel
├── Utils/               # Утилиты, логи, конфиги
├── configs/             # .txt конфиги
├── plugins/             # Плагины
└── docs/PLUGINS.md      # Документация плагинов
```

## Команды бота

| Команда | Описание |
|---------|----------|
| `/start` | Авторизация паролем |
| `/menu` | Главное меню |
| `/profile` | Профиль Starvell |
| `/session` | Как получить session_token |
| `/logs` | Логи текущей сессии (файл) |
| `/restart` | Перезапуск |
| `/help` | Справка |

## Конфиги

| Файл | Назначение |
|------|------------|
| `configs/_main.txt` | Основной конфиг |
| `configs/auto_response.txt` | Автоответы |
| `configs/auto_delivery.txt` | Автовыдача |
| `configs/commands.txt` | Пользовательские команды (JSON) |

## Лицензия

MIT
