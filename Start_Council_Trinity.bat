@echo off
chcp 65001 >nul
title Council Trinity Lab - Launcher
cd /d C:\Inthasap_Guard\Council_Lab
echo ============================================================
echo   COUNCIL TRINITY LAB
echo ============================================================
echo [1] Closing old server on 8091 (if any)...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8091 ^| findstr LISTENING') do taskkill /f /pid %%a >nul 2>&1
timeout /t 1 /nobreak >nul
echo [2] Starting Council Trinity Server (window stays open)...
start "Council Trinity Server" cmd /k "cd /d C:\Inthasap_Guard\Council_Lab && python council_web.py"
echo [3] Waiting for server to come up...
timeout /t 6 /nobreak >nul
start "" http://127.0.0.1:8091
echo.
echo   Browser opened: http://127.0.0.1:8091
echo   *** KEEP the "Council Trinity Server" window OPEN ***
echo   (If that window shows red error and closes, tell PiJun)
echo.
pause
