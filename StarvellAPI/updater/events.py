"""События мониторинга Starvell."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class NewMessageEvent:
    chat_id: str
    username: str
    text: str
    interlocutor_id: int | None = None
    raw: dict[str, Any] = field(default_factory=dict)
    is_new_chat: bool = False


@dataclass
class NewOrderEvent:
    order_id: str
    username: str
    lot_title: str
    price: float
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class PaymentEvent:
    order_id: str
    username: str
    amount: float
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class OrderConfirmEvent:
    order_id: str
    username: str
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class ReviewEvent:
    order_id: str
    username: str
    rating: int
    text: str
    raw: dict[str, Any] = field(default_factory=dict)
