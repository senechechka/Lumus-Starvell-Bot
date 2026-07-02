"""Работа с чатами Starvell (Next.js BFF API)."""
from __future__ import annotations

import logging
import secrets
import string
from typing import Any

from StarvellAPI.account import Account
from StarvellAPI.cookies import cookies_to_header
from StarvellAPI.http_headers import next_data_headers

logger = logging.getLogger("StarvellAPI")


def _client_socket_id() -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(20))


def fetch_chats(account: Account) -> list[dict[str, Any]]:
    build_id = account._get_build_id()
    url = f"https://starvell.com/_next/data/{build_id}/chat.json"
    headers = next_data_headers("https://starvell.com/chat")
    headers["cookie"] = cookies_to_header(account.cookies)
    if account.user_agent:
        headers["user-agent"] = account.user_agent

    resp = account._session.get(url, headers=headers, timeout=20)

    if resp.status_code == 404:
        account._build_id = None
        account._build_id_at = 0.0
        build_id = account._get_build_id()
        url = f"https://starvell.com/_next/data/{build_id}/chat.json"
        resp = account._session.get(url, headers=headers, timeout=20)

    resp.raise_for_status()
    data = resp.json()
    return data.get("pageProps", {}).get("chats") or []


def parse_chat_list(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [c for c in raw if isinstance(c, dict)]


def extract_interlocutor(chat: dict[str, Any], my_user_id: int) -> tuple[str, int | None]:
    last_msg = chat.get("lastMessage") or {}
    buyer = last_msg.get("buyer") or {}
    
    if buyer and buyer.get("id") and int(buyer["id"]) != my_user_id:
        return buyer.get("username") or "Покупатель", int(buyer["id"])

    participants = chat.get("participants") or []
    username = "Покупатель"
    interlocutor_id: int | None = None

    for p in participants:
        if not isinstance(p, dict):
            continue
        pid = p.get("id")
        if pid is not None and int(pid) != my_user_id:
            username = p.get("username") or "Покупатель"
            interlocutor_id = int(pid)
            break

    return username, interlocutor_id


def message_text(msg: dict[str, Any]) -> str:
    content = (msg.get("content") or msg.get("text") or "").strip()
    if content:
        return content
    images = msg.get("images") or []
    if isinstance(images, list) and images:
        return "📷 Фото"
    return ""


def message_author_id(msg: dict[str, Any]) -> int | None:
    author_id = msg.get("authorId")
    if author_id is None:
        return None
    try:
        return int(author_id)
    except (TypeError, ValueError):
        return None


def is_auto_message(msg: dict[str, Any]) -> bool:
    metadata = msg.get("metadata") or {}
    if bool(metadata.get("isAuto")):
        return True
    if msg.get("type") == "NOTIFICATION":
        return True
    return False