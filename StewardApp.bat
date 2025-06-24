@echo off
title Sistema di Gestione Steward
color 0A

echo ========================================
echo   SISTEMA DI GESTIONE STEWARD
echo ========================================
echo.
echo Avvio del server Flask...
echo.

cd /d "C:\Users\anton\Desktop\cursor"

echo Attivazione ambiente virtuale...
call .venv\Scripts\activate

echo.
echo Avvio del server Flask...
echo Il server sarà disponibile su: http://localhost:5000
echo.
echo Apertura del browser tra 3 secondi...
timeout /t 3 /nobreak >nul

echo Apertura del browser...
start http://localhost:5000

echo.
echo ========================================
echo   SERVER AVVIATO CON SUCCESSO!
echo ========================================
echo.
echo ✅ Browser aperto su http://localhost:5000
echo ✅ Server Flask attivo
echo.
echo Per fermare il server, premi CTRL+C
echo.
echo ========================================

python app.py

echo.
echo Server arrestato.
pause 