"""
Система плагинов LSB.
"""
from __future__ import annotations

import importlib.util
import json
import logging
import os
import sys
import uuid
from types import ModuleType
from typing import Any, Callable

from Utils.exceptions import PluginLoadError

logger = logging.getLogger("LSB")

REQUIRED_FIELDS = ("NAME", "VERSION", "DESCRIPTION", "CREDITS", "UUID")
ALLOWED_BINDS = {
    "BIND_TO_PRE_INIT",
    "BIND_TO_POST_INIT",
    "BIND_TO_PRE_START",
    "BIND_TO_POST_START",
    "BIND_TO_NEW_MESSAGE",
    "BIND_TO_NEW_ORDER",
    "BIND_TO_PAYMENT",
    "BIND_TO_ORDER_CONFIRM",
    "BIND_TO_REVIEW",
    "BIND_TO_DELETE",
    "BIND_TO_TELEGRAM_COMMANDS",
    "BIND_TO_PLUGIN_MENU",
}

STATE_FILE = "storage/plugins/state.json"


class PluginData:
    def __init__(self, module: ModuleType, path: str, enabled: bool = True):
        self.module = module
        self.path = path
        self.name = getattr(module, "NAME", "Unknown")
        self.version = getattr(module, "VERSION", "0.0.0")
        self.description = getattr(module, "DESCRIPTION", "")
        self.credits = getattr(module, "CREDITS", "")
        self.uuid = str(getattr(module, "UUID", ""))
        self.enabled = enabled
        self.commands: list[dict[str, str]] = self._parse_commands(module)
        self.menu_handler: Callable | None = self._parse_menu_handler(module)
        self.handlers: dict[str, list[Callable]] = {}

        for bind in ALLOWED_BINDS:
            if bind == "BIND_TO_PLUGIN_MENU":
                continue
            value = getattr(module, bind, None)
            if value is None:
                continue
            if bind == "BIND_TO_DELETE":
                if callable(value):
                    self.handlers[bind] = [value]
            elif isinstance(value, list):
                self.handlers[bind] = [h for h in value if callable(h)]
            elif callable(value):
                self.handlers[bind] = [value]

    @staticmethod
    def _parse_commands(module: ModuleType) -> list[dict[str, str]]:
        raw = getattr(module, "COMMANDS", None)
        if not raw:
            return []
        result = []
        for item in raw:
            if isinstance(item, dict):
                cmd = item.get("command") or item.get("cmd") or ""
                desc = item.get("description") or item.get("desc") or ""
                if cmd:
                    result.append({"command": str(cmd).lstrip("/"), "description": str(desc)})
            elif isinstance(item, (list, tuple)) and len(item) >= 1:
                result.append({"command": str(item[0]).lstrip("/"), "description": str(item[1]) if len(item) > 1 else ""})
        return result

    @staticmethod
    def _parse_menu_handler(module: ModuleType) -> Callable | None:
        value = getattr(module, "BIND_TO_PLUGIN_MENU", None)
        if callable(value):
            return value
        if isinstance(value, list) and value and callable(value[0]):
            return value[0]
        return None


class PluginManager:
    def __init__(self, plugins_dir: str = "plugins"):
        self.plugins_dir = plugins_dir
        self.plugins: dict[str, PluginData] = {}
        self._disabled: set[str] = set()
        self._load_state()

    def _load_state(self) -> None:
        if not os.path.exists(STATE_FILE):
            return
        try:
            with open(STATE_FILE, encoding="utf-8") as f:
                data = json.load(f)
            self._disabled = set(data.get("disabled", []))
        except (json.JSONDecodeError, TypeError):
            self._disabled = set()

    def _save_state(self) -> None:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump({"disabled": list(self._disabled)}, f, ensure_ascii=False, indent=2)

    def load_all(self) -> None:
        self.plugins.clear()
        if not os.path.isdir(self.plugins_dir):
            os.makedirs(self.plugins_dir, exist_ok=True)
            return

        for filename in os.listdir(self.plugins_dir):
            if not filename.endswith(".py") or filename.startswith("_"):
                continue
            path = os.path.join(self.plugins_dir, filename)
            try:
                with open(path, encoding="utf-8") as f:
                    first_line = f.readline()
                if "noplug" in first_line.lower():
                    continue
                plugin = self._load_file(path)
                plugin.enabled = plugin.uuid not in self._disabled
                self.plugins[plugin.uuid] = plugin
                logger.info(f"$PLUGINПлагин загружен: {plugin.name} v{plugin.version}")
            except Exception as e:
                logger.error(f"$ERRORНе удалось загрузить плагин {filename}: {e}")

    def _load_file(self, path: str) -> PluginData:
        name = os.path.splitext(os.path.basename(path))[0]
        spec = importlib.util.spec_from_file_location(f"lsb_plugin_{name}", path)
        if spec is None or spec.loader is None:
            raise PluginLoadError(f"Не удалось создать spec для {path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)

        for field in REQUIRED_FIELDS:
            if not hasattr(module, field):
                raise PluginLoadError(f"Отсутствует обязательное поле {field}")
            if field == "UUID":
                try:
                    uuid.UUID(str(getattr(module, field)))
                except ValueError as e:
                    raise PluginLoadError(f"UUID должен быть валидным UUID4: {e}") from e

        return PluginData(module, path)

    def run_handlers(self, bind: str, lsb: Any, *args, **kwargs) -> None:
        for plugin in self.plugins.values():
            if not plugin.enabled:
                continue
            for handler in plugin.handlers.get(bind, []):
                try:
                    handler(lsb, *args, **kwargs)
                except Exception as e:
                    logger.error(f"$ERRORПлагин {plugin.name} ({bind}): {e}")

    def set_enabled(self, plugin_uuid: str, enabled: bool) -> None:
        plugin = self.plugins.get(plugin_uuid)
        if not plugin:
            return
        plugin.enabled = enabled
        if enabled:
            self._disabled.discard(plugin_uuid)
        else:
            self._disabled.add(plugin_uuid)
        self._save_state()

    def delete_plugin(self, plugin_uuid: str) -> bool:
        plugin = self.plugins.get(plugin_uuid)
        if not plugin:
            return False
        try:
            if os.path.exists(plugin.path):
                os.remove(plugin.path)
        except OSError as e:
            logger.error(f"$ERRORНе удалось удалить {plugin.path}: {e}")
            return False
        self.plugins.pop(plugin_uuid, None)
        self._disabled.discard(plugin_uuid)
        self._save_state()
        logger.info(f"$PLUGINПлагин удалён: {plugin.name}")
        return True

    def list_plugins(self) -> list[PluginData]:
        return list(self.plugins.values())

    def get_by_uuid(self, plugin_uuid: str) -> PluginData | None:
        return self.plugins.get(plugin_uuid)
