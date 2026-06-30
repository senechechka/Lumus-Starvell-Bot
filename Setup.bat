@echo off
chcp 65001 >nul
title Lumus Starvell Bot - Setup
cd /d "%~dp0"

echo ========================================
echo   Lumus Starvell Bot - Установка
echo ========================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [ОШИБКА] Python не найден. Установите Python 3.11+ и добавьте в PATH.
    pause
    exit /b 1
)

echo [1/3] Обновление pip...
python -m pip install --upgrade pip

echo [2/3] Установка зависимостей...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ОШИБКА] Не удалось установить зависимости.
    pause
    exit /b 1
)

echo [3/3] Генерация логотипа...
python Utils/logo.py

echo.
echo ========================================
echo   Установка завершена!
echo   Запустите Start.bat для первичной настройки.
echo ========================================
pause
