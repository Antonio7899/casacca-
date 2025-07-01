@echo off
title Sistema di Gestione Steward - Avvio Automatico
color 0A

echo ========================================
echo   SISTEMA DI GESTIONE STEWARD
echo ========================================
echo.
echo Avvio automatico del server...
echo.

cd /d %~dp0
REM Attiva l'ambiente virtuale se esiste
if exist .venv\Scripts\activate.bat (
    call .venv\Scripts\activate.bat
)
REM Avvia il server Flask su tutte le interfacce
start "" python app.py
REM Attendi qualche secondo per l'avvio
ping 127.0.0.1 -n 3 > nul
REM Ottieni l'indirizzo IP locale
for /f "tokens=2 delims=: " %%a in ('ipconfig ^| findstr /C:"IPv4"') do set IP=%%a
REM Rimuovi spazi
set IP=%IP: =%
REM Apri il browser sulla dashboard
start http://%IP%:5001

echo.
echo ========================================
echo   ✅ APP AVVIATA CON SUCCESSO!
echo ========================================
echo.
echo 🌐 Accesso locale: http://localhost:5000
echo 📱 Accesso mobile: http://%IP%:5000
echo.
echo 📋 ISTRUZIONI PER MOBILE:
echo 1. Sul tuo Android, apri il browser
echo 2. Vai su: http://%IP%:5000
echo 3. L'app funzionerà su tutti i dispositivi!
echo.
echo ⚠️  Per fermare il server, premi CTRL+C
echo ========================================

echo.
echo Server arrestato.
pause 