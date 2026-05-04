@echo off
REM Start the Discord Bot

cd /d "%USERPROFILE%\discordbotcito"
echo Starting Discord Bot...
uv run python main.py
