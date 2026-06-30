"""
Клиент аккаунта Starvell.
Авторизация через session cookie (получить в DevTools → Application → Cookies → session).
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

import requests
from bs4 import BeautifulSoup

from StarvellAPI.common.exceptions import RequestError, UnauthorizedError
from StarvellAPI.cookies import build_cookies, cookies_to_header
from StarvellAPI.http_headers import api_headers, next_data_headers, page_headers

logger = logging.getLogger("StarvellAPI")

BUILD_ID_TTL = 1800


class Account:
    def __init__(
        self,
        session_token: str,
        sid_cookie: str = "",
        my_games_cookie: str = "",
        user_agent: str | None = None,
        proxy: dict | None = None,
    ):
        self.session_token = session_token.strip()
        self.sid_cookie = sid_cookie.strip()
        self.my_games_cookie = my_games_cookie.strip()
        self.user_agent = user_agent
        self.proxy = proxy
        self.username: str | None = None
        self.user_id: int | None = None
        self.balance: float = 0.0
        self.active_orders: int = 0
        self._build_id: str | None = None
        self._build_id_at: float = 0.0
        self._session = requests.Session()
        if proxy:
            self._session.proxies.update(proxy)

    @property
    def cookies(self) -> dict[str, str]:
        return build_cookies(self.session_token, self.sid_cookie, self.my_games_cookie)

    def _headers(self, referer: str = "https://starvell.com/", api: bool = False) -> dict:
        headers = api_headers(referer) if api else page_headers(referer)
        if self.user_agent:
            headers["user-agent"] = self.user_agent
        headers["cookie"] = cookies_to_header(self.cookies)
        return headers

    def get(self) -> "Account":
        """Проверка сессии и загрузка профиля."""
        resp = self._session.get(
            "https://starvell.com/",
            headers=self._headers(),
            timeout=20,
        )
        if resp.status_code != 200:
            raise UnauthorizedError(f"Starvell вернул код {resp.status_code}")

        html = resp.text
        if "logout" not in html.lower() and "__NEXT_DATA__" not in html:
            raise UnauthorizedError("Сессия Starvell недействительна. Обновите session_token.")

        match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.DOTALL)
        if match:
            data = json.loads(match.group(1))
            self._parse_profile(data)
            build_id = data.get("buildId")
            if build_id:
                self._build_id = str(build_id)
                self._build_id_at = time.time()

        if not self.username:
            self._parse_profile_from_html(html)

        if not self.username:
            raise UnauthorizedError("Не удалось определить профиль. Проверьте session_token.")

        logger.info(f"$SUCCESSАвторизация Starvell: {self.username} (ID: {self.user_id})")
        self.refresh_stats()
        return self

    def _parse_profile(self, next_data: dict) -> None:
        props = next_data.get("props", {}).get("pageProps", {})
        user = props.get("currentUser") or props.get("user") or {}
        if isinstance(user, dict):
            self.username = user.get("username") or user.get("login")
            uid = user.get("id") or user.get("userId")
            if uid is not None:
                self.user_id = int(uid)
            balance = user.get("balance") or user.get("walletBalance")
            if balance is not None:
                try:
                    self.balance = float(balance)
                except (TypeError, ValueError):
                    pass

    def _parse_profile_from_html(self, html: str) -> None:
        soup = BeautifulSoup(html, "lxml")
        for script in soup.find_all("script"):
            text = script.string or script.get_text()
            if not text or "username" not in text:
                continue
            try:
                if text.strip().startswith("{"):
                    data = json.loads(text)
                    self._parse_profile({"props": {"pageProps": data}})
                    if self.username:
                        return
            except json.JSONDecodeError:
                continue

    def _get_build_id(self) -> str:
        if self._build_id and (time.time() - self._build_id_at) < BUILD_ID_TTL:
            return self._build_id
        resp = self._session.get("https://starvell.com/", headers=self._headers(), timeout=20)
        resp.raise_for_status()
        match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', resp.text, re.DOTALL)
        if not match:
            raise RequestError("buildId не найден")
        data = json.loads(match.group(1))
        build_id = data.get("buildId")
        if not build_id:
            raise RequestError("buildId пустой")
        self._build_id = str(build_id)
        self._build_id_at = time.time()
        return self._build_id

    def refresh_stats(self) -> None:
        """Обновляет баланс и количество активных заказов."""
        try:
            self._fetch_wallet()
            self._fetch_active_orders_count()
        except Exception as e:
            logger.warning(f"$TIMERНе удалось обновить статистику: {e}")

    def _fetch_wallet(self) -> None:
        headers = self._headers("https://starvell.com/wallet", api=True)
        resp = self._session.get("https://starvell.com/api/wallet/balance", headers=headers, timeout=20)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, dict):
                for key in ("balance", "available", "amount"):
                    if key in data:
                        try:
                            self.balance = float(data[key])
                            return
                        except (TypeError, ValueError):
                            pass
            elif isinstance(data, (int, float)):
                self.balance = float(data)

    def _fetch_active_orders_count(self) -> None:
        try:
            orders = self.fetch_sells()
            self.active_orders = sum(1 for o in orders if str(o.get("status", "")).upper() == "CREATED")
        except Exception as e:
            logger.warning(f"$TIMERНе удалось посчитать активные заказы: {e}")

    def fetch_sells(self) -> list[dict[str, Any]]:
        build_id = self._get_build_id()
        url = f"https://starvell.com/_next/data/{build_id}/account/sells.json"
        headers = next_data_headers("https://starvell.com/account/sells")
        headers["cookie"] = cookies_to_header(self.cookies)
        if self.user_agent:
            headers["user-agent"] = self.user_agent

        resp = self._session.get(url, headers=headers, timeout=20)

        if resp.status_code == 404:
            self._build_id = None
            self._build_id_at = 0.0
            build_id = self._get_build_id()
            url = f"https://starvell.com/_next/data/{build_id}/account/sells.json"
            headers["cookie"] = cookies_to_header(self.cookies)
            resp = self._session.get(url, headers=headers, timeout=20)

        resp.raise_for_status()
        data = resp.json()
        orders = data.get("pageProps", {}).get("orders") or []
        return orders if isinstance(orders, list) else []
    
    def get_categories_for_bump(self) -> list[dict[str, Any]]:
        categories = self._fetch_profile_offers()
        result = []
        seen: set[tuple[int, int]] = set()
        for cat in categories:
            if not isinstance(cat, dict):
                continue
            game_id = cat.get("gameId") or (cat.get("game") or {}).get("id")
            cat_id = cat.get("id")
            if game_id is None or cat_id is None:
                continue
            key = (int(game_id), int(cat_id))
            if key in seen:
                continue
            seen.add(key)
            result.append({"gameId": key[0], "categoryId": key[1]})
        return result

    def count_lots(self) -> tuple[int, int]:
        """Возвращает (число лотов, число категорий для автоподнятия)."""
        categories = self._fetch_profile_offers()
        lots = 0
        cat_ids: set[int] = set()
        for cat in categories:
            if not isinstance(cat, dict):
                continue
            cat_id = cat.get("id")
            if cat_id is not None:
                cat_ids.add(int(cat_id))
            offers = cat.get("offers") or []
            if isinstance(offers, list):
                lots += sum(1 for o in offers if isinstance(o, dict))
        return lots, len(cat_ids)

    def _fetch_profile_offers(self) -> list[dict[str, Any]]:
        if not self.user_id and not self.username:
            return []
        build_id = self._get_build_id()
        slug = self.username or str(self.user_id)
        url = f"https://starvell.com/_next/data/{build_id}/profile/{slug}.json"
        headers = next_data_headers(f"https://starvell.com/profile/{slug}")
        headers["cookie"] = cookies_to_header(self.cookies)
        if self.user_agent:
            headers["user-agent"] = self.user_agent
        resp = self._session.get(url, headers=headers, timeout=20)
        if resp.status_code != 200:
            return []
        data = resp.json()
        categories = (
            data.get("pageProps", {}).get("userProfileOffers")
            or data.get("pageProps", {}).get("bff", {}).get("userProfileOffers")
            or []
        )
        return categories if isinstance(categories, list) else []
    
    def fetch_order_details(self, order_id: str) -> dict[str, Any]:
        build_id = self._get_build_id()
        url = f"https://starvell.com/_next/data/{build_id}/order/{order_id}.json"
        headers = next_data_headers(f"https://starvell.com/order/{order_id}")
        headers["cookie"] = cookies_to_header(self.cookies)
        if self.user_agent:
            headers["user-agent"] = self.user_agent

        resp = self._session.get(url, headers=headers, timeout=20)

        if resp.status_code == 404:
            self._build_id = None
            self._build_id_at = 0.0
            build_id = self._get_build_id()
            url = f"https://starvell.com/_next/data/{build_id}/order/{order_id}.json"
            headers["cookie"] = cookies_to_header(self.cookies)
            resp = self._session.get(url, headers=headers, timeout=20)

        resp.raise_for_status()
        data = resp.json()
        return data.get("pageProps", {}) or {}

    def bump_categories(self, game_id: int, category_ids: list[int]) -> dict[str, Any]:
        headers = self._headers("https://starvell.com/", api=True)
        payload = {"gameId": game_id, "categoryIds": category_ids}
        resp = self._session.post(
            "https://starvell.com/api/offers/bump",
            headers=headers,
            json=payload,
            timeout=20,
        )
        result: dict[str, Any] = {"status": resp.status_code, "success": 200 <= resp.status_code < 300}
        try:
            result["json"] = resp.json()
        except ValueError:
            result["raw"] = resp.text[:500]
        return result
    
    def mark_seller_completed(self, order_id: str) -> bool:
        headers = self._headers(f"https://starvell.com/orders/{order_id}", api=True)
        url = f"https://starvell.com/api/orders/{order_id}/mark-seller-completed"
        payload = {"id": order_id}
        resp = self._session.post(url, headers=headers, json=payload, timeout=20)
        ok = 200 <= resp.status_code < 300
        if ok:
            logger.info(f"$SUCCESSЗаказ #{order_id} отмечен как выполненный продавцом")
        else:
            logger.error(f"$ERRORmark_seller_completed HTTP {resp.status_code}: {resp.text[:300]}")
        return ok

    def send_chat_message(self, chat_id: str, text: str, interlocutor_id: int | None = None) -> bool:
        import secrets
        import string
        alphabet = string.ascii_letters + string.digits
        client_socket_id = "".join(secrets.choice(alphabet) for _ in range(20))

        headers = self._headers(f"https://starvell.com/chat/{chat_id}", api=True)
        url = "https://starvell.com/api/messages/send"
        payload = {
            "chatId": chat_id,
            "clientSocketId": client_socket_id,
            "content": text,
        }
        resp = self._session.post(url, headers=headers, json=payload, timeout=20)
        ok = 200 <= resp.status_code < 300
        if ok:
            preview = text[:120] + ("…" if len(text) > 120 else "")
            logger.info(f"$SELLERИсходящее сообщение (чат {chat_id}): {preview}")
        else:
            logger.error(f"$ERRORsend_chat_message HTTP {resp.status_code}: {resp.text[:300]}")
        return ok
