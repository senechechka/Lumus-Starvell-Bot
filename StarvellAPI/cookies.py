"""Работа с cookie-сессией Starvell (аналог golden_key FunPay)."""

_DEFAULT_COOKIES = {
    "starvell.theme": "dark",
    "starvell.time_zone": "Europe/Moscow",
}


def parse_cookie_string(raw: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for part in (raw or "").split(";"):
        item = part.strip()
        if not item or "=" not in item:
            continue
        key, value = item.split("=", 1)
        key = key.strip()
        if key:
            result[key] = value.strip()
    return result


def build_cookies(
    session_token: str,
    sid_cookie: str | None = None,
    my_games_cookie: str | None = None,
) -> dict[str, str]:
    cookies = dict(_DEFAULT_COOKIES)
    raw = (session_token or "").strip()
    if "=" in raw:
        cookies.update(parse_cookie_string(raw))
    elif raw:
        cookies["session"] = raw
    if sid_cookie:
        cookies["sid"] = sid_cookie
    if my_games_cookie:
        cookies["starvell.my_games"] = my_games_cookie
    return {k: v for k, v in cookies.items() if v}


def cookies_to_header(cookies: dict[str, str]) -> str:
    return "; ".join(f"{k}={v}" for k, v in cookies.items())
