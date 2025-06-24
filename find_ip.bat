@echo off
title Trova IP del Computer
color 0E

echo ========================================
echo   TROVA IP DEL COMPUTER
echo ========================================
echo.
echo Questo ti mostrerà l'indirizzo IP del tuo computer
echo per permettere l'accesso da dispositivi mobili.
echo.

echo Attendi, sto trovando l'IP...
ipconfig | findstr "IPv4"

echo.
echo ========================================
echo   ISTRUZIONI PER ACCESSO MOBILE
echo ========================================
echo.
echo 1. Copia uno degli indirizzi IP sopra (es: 192.168.1.100)
echo 2. Sul tuo smartphone/tablet, apri il browser
echo 3. Vai su: http://[IP]:5000
echo    (esempio: http://192.168.1.100:5000)
echo.
echo ✅ L'app funzionerà su tutti i dispositivi!
echo.

pause 