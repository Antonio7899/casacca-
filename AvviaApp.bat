@echo off
title Sistema di Gestione Steward - Avvio Automatico
color 0A

echo ========================================
echo   SISTEMA DI GESTIONE STEWARD
echo ========================================
echo.
echo Avvio automatico del server...
echo.

cd /d "C:\Users\anton\Desktop\cursor"

echo [1/4] Attivazione ambiente virtuale...
call .venv\Scripts\activate

echo [2/4] Avvio del server Flask...
echo Il server sarà disponibile su: http://localhost:5000
echo.

echo [3/4] Trovando l'IP del computer...
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr "IPv4"') do (
    set IP=%%a
    goto :found_ip
)
:found_ip
set IP=%IP: =%

echo ✅ IP del computer: %IP%
echo.

echo [4/4] Apertura del browser...
timeout /t 2 /nobreak >nul
start http://localhost:5000

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

python app.py

echo.
echo Server arrestato.
pause 