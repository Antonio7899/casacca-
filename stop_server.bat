@echo off
title Ferma Server Flask
color 0C

echo ========================================
echo   ARRESTO SERVER FLASK
echo ========================================
echo.

echo Fermando tutti i processi Python...
taskkill /f /im python.exe 2>nul

echo.
echo ✅ Server Flask arrestato
echo ✅ Tutti i processi Python terminati
echo.

pause 