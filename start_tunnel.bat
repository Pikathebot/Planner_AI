@echo off
TITLE Cloudflare Tunnel - Planner Agent
SETLOCAL EnableDelayedExpansion

echo ======================================================
echo   🌐 CLOUDFLARE TUNNEL - EXPOSING LOCAL SERVER
echo ======================================================
echo.

:: Configuration
SET "LOCAL_URL=http://localhost:8000"
SET "CLOUDFLARE_EXE=.\cloudflared.exe"

:: Check if cloudflared.exe exists
if not exist "%CLOUDFLARE_EXE%" (
    echo [!] cloudflared.exe not found in current directory.
    echo Please ensure the executable is present.
    pause
    exit /b 1
)

echo [1/2] Checking Local Server URL: %LOCAL_URL%
echo [2/2] Initializing Cloudflare (TryCloudflare)...
echo.
echo [!] IMPORTANT: Copy the "https://*.trycloudflare.com" URL 
echo     that appears below to share your application.
echo.
echo Press Ctrl+C to stop the tunnel.
echo ======================================================
echo.

"%CLOUDFLARE_EXE%" tunnel --url %LOCAL_URL%

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [!] Tunnel interrupted or failed to start.
    pause
)
