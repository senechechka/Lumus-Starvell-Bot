class UnauthorizedError(Exception):
    """Сессия Starvell недействительна."""


class RequestError(Exception):
    """Ошибка HTTP-запроса к Starvell."""
