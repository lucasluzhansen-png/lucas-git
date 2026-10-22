@echo off
cd /d "%~dp0"
set PYTHONPATH=src
set PYTHONIOENCODING=utf-8
python -m hansen.hoje auto
echo.
pause
