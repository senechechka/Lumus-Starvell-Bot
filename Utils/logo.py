"""
Генерация логотипа LSB из исходного изображения (Pillow).
"""
from __future__ import annotations

import os
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "assets" / "logo_source.png"
LOGO_PNG = ROOT / "assets" / "logo.png"
LOGO_ICO = ROOT / "LSB.ico"
ASCII_CACHE = ROOT / "assets" / "logo_ascii.txt"

ASCII_CHARS = "@%#*+=-:. "


def ensure_logo_assets() -> None:
    if not SOURCE.exists():
        return
    img = Image.open(SOURCE).convert("RGBA")
    img.save(LOGO_PNG)

    icon_sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
    icon = img.copy()
    icon.save(LOGO_ICO, format="ICO", sizes=icon_sizes)

    ascii_art = image_to_ascii(img, width=48)
    ASCII_CACHE.write_text(ascii_art, encoding="utf-8")


def image_to_ascii(img: Image.Image, width: int = 48) -> str:
    gray = img.convert("L")
    ratio = gray.height / gray.width
    height = max(8, int(width * ratio * 0.45))
    gray = gray.resize((width, height))
    pixels = list(gray.get_flattened_data())
    lines = []
    for y in range(height):
        row = []
        for x in range(width):
            pixel = pixels[y * width + x]
            idx = int(pixel / 255 * (len(ASCII_CHARS) - 1))
            row.append(ASCII_CHARS[idx])
        lines.append("".join(row))
    return "\n".join(lines)


def get_ascii_logo() -> str:
    if ASCII_CACHE.exists():
        return ASCII_CACHE.read_text(encoding="utf-8")
    if SOURCE.exists():
        ensure_logo_assets()
        if ASCII_CACHE.exists():
            return ASCII_CACHE.read_text(encoding="utf-8")
    return r"""
    ✦ LUMUS STARVELL BOT ✦
         ★  LSB  ★
"""


def print_startup_banner(version: str) -> None:
    from colorama import Fore, Style

    logo = get_ascii_logo()
    print(f"{Fore.YELLOW}{Style.BRIGHT}{logo}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{Style.BRIGHT}Lumus Starvell Bot (LSB) v{version}{Style.RESET_ALL}\n")


if __name__ == "__main__":
    ensure_logo_assets()
    print(get_ascii_logo())
