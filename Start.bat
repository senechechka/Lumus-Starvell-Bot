@echo off
chcp 65001 >nul
title Lumus Starvell Bot
cd /d "%~dp0"
python main.py
if errorlevel 1 pause
