class ConfigParseError(Exception):
    """Ошибка парсинга конфигурационного файла."""


class UnauthorizedError(Exception):
    """Ошибка авторизации на Starvell."""


class PluginLoadError(Exception):
    """Ошибка загрузки плагина."""
