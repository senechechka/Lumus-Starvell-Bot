"""HTTP-заголовки для запросов к Starvell."""

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
SEC_CH_UA = '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"'
ACCEPT_LANGUAGE = "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7"
ORIGIN = "https://starvell.com"

_CLIENT_HINTS = {
    "sec-ch-ua": SEC_CH_UA,
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
}


def api_headers(referer: str = "https://starvell.com/", json: bool = True) -> dict:
    headers = {
        "accept": "*/*",
        "accept-language": ACCEPT_LANGUAGE,
        "referer": referer,
        **_CLIENT_HINTS,
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "user-agent": USER_AGENT,
        "origin": ORIGIN,
    }
    if json:
        headers["content-type"] = "application/json"
    return headers


def page_headers(referer: str | None = None) -> dict:
    headers = {
        "accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "image/avif,image/webp,image/apng,*/*;q=0.8"
        ),
        "accept-language": ACCEPT_LANGUAGE,
        **_CLIENT_HINTS,
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "same-origin" if referer else "none",
        "sec-fetch-user": "?1",
        "upgrade-insecure-requests": "1",
        "user-agent": USER_AGENT,
    }
    if referer:
        headers["referer"] = referer
    return headers


def next_data_headers(referer: str = "https://starvell.com/") -> dict:
    headers = api_headers(referer, json=False)
    headers["x-nextjs-data"] = "1"
    return headers
