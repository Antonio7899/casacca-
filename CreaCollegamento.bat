@echo off
title Crea Collegamento Desktop
color 0B

echo ========================================
echo   CREA COLLEGAMENTO SUL DESKTOP
echo ========================================
echo.

echo Creando collegamento sul desktop...
echo.

set "DESKTOP=%USERPROFILE%\Desktop"
set "SOURCE=%CD%\AvviaApp.bat"
set "LINK=%DESKTOP%\Sistema Steward.lnk"

echo Percorso desktop: %DESKTOP%
echo File sorgente: %SOURCE%
echo Collegamento: %LINK%
echo.

powershell -Command "$WshShell = New-Object -comObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut('%LINK%'); $Shortcut.TargetPath = '%SOURCE%'; $Shortcut.WorkingDirectory = '%CD%'; $Shortcut.Description = 'Sistema di Gestione Steward'; $Shortcut.IconLocation = '%CD%\static\favicon.ico'; $Shortcut.Save()"

echo.
echo ========================================
echo   ✅ COLLEGAMENTO CREATO!
echo ========================================
echo.
echo 📁 Il collegamento è stato creato sul desktop
echo 🖱️  Ora puoi avviare l'app con un doppio click!
echo.
echo 📱 Per usare su mobile:
echo 1. Doppio click su "Sistema Steward" sul desktop
echo 2. Copia l'IP che appare
echo 3. Sul telefono, vai su: http://[IP]:5000
echo.

pause 