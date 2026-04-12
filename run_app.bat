@echo off
TITLE Planner Agent - FastAPI Server
echo ======================================================
echo   ✨ LOCAL AI PLANNING AGENT - STARTING SERVER
echo ======================================================
echo.
echo [1/3] Activating Virtual Environment...
call .\venv\Scripts\activate

echo [2/3] Starting Uvicorn on http://localhost:8000 ...
echo Press Ctrl+C to stop the server.
echo.

uvicorn server:app --host 0.0.0.0 --port 8000 --log-level info --workers 1

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [!] Server failed to start. Ensure Ollama is running and venv is intact.
    pause
)
