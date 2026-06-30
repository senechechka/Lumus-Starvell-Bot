"""
Переменные для подстановки в сообщения ($time, $date и т.д.).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any


VARIABLES = {
    "$time": "Текущее время (ЧЧ:ММ:СС)",
    "$date": "Текущая дата (ДД.ММ.ГГГГ)",
    "$datetime": "Дата и время",
    "$username": "Имя покупателя",
    "$seller": "Ваш ник на Starvell",
    "$lot": "Название лота",
    "$lot_price": "Цена лота",
    "$order_id": "ID заказа",
    "$balance": "Баланс на Starvell",
    "$chat_id": "ID чата Starvell",
}


def format_variables(text: str, context: dict[str, Any] | None = None) -> str:
    context = context or {}
    now = datetime.now()
    replacements = {
        "$time": now.strftime("%H:%M:%S"),
        "$date": now.strftime("%d.%m.%Y"),
        "$datetime": now.strftime("%d.%m.%Y %H:%M:%S"),
        "$username": str(context.get("username", "")),
        "$seller": str(context.get("seller", "")),
        "$lot": str(context.get("lot", "")),
        "$lot_price": str(context.get("lot_price", "")),
        "$order_id": str(context.get("order_id", "")),
        "$balance": str(context.get("balance", "")),
        "$chat_id": str(context.get("chat_id", "")),
    }
    result = text
    for key, value in replacements.items():
        result = result.replace(key, value)
    return result


def variables_help_text() -> str:
    lines = ["<b>Переменные</b> (нажмите на код, чтобы скопировать):"]
    for var, desc in VARIABLES.items():
        lines.append(f"• <code>{var}</code> — {desc}")
    return "\n".join(lines)


def variables_help_plain() -> str:
    lines = ["Переменные (вставьте в текст):"]
    for var, desc in VARIABLES.items():
        lines.append(f"  {var} — {desc}")
    return "\n".join(lines)
