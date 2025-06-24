@echo off
echo === Avvio Server Flask ===
cd /d "C:\Users\anton\Desktop\cursor"
call .venv\Scripts\activate
echo Server Flask avviato su http://localhost:5000
echo Premi CTRL+C per fermare il server
python app.py
pause 