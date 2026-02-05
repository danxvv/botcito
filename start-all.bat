@echo off
REM Start both Discord Bot and Voice MCP Server simultaneously
REM Use Ctrl+C in either window to stop that process

echo Starting Voice MCP Server and Discord Bot...
echo.

REM Start Voice MCP Server in a new window
start "Voice MCP Server" cmd /k "cd /d \"%USERPROFILE%\voiceapi\" && uv run python mcp_server.py --http --port 8080"

REM Wait a moment for the TTS model to start loading
timeout /t 2 /nobreak >nul

REM Start Discord Bot in the current window
cd /d "%USERPROFILE%\discordbotcito"
echo Starting Discord Bot...
uv run python main.py
