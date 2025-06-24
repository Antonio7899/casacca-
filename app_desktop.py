import webbrowser
import time
import os
import sys

def main():
    print("=== Sistema di Gestione Steward - Desktop App ===")
    print()
    print("ISTRUZIONI:")
    print("1. Questo launcher aprirà il browser")
    print("2. Devi avviare manualmente il server Flask")
    print("3. Per avviare il server, apri un terminale e esegui:")
    print("   .venv\\Scripts\\activate")
    print("   python app.py")
    print()
    
    # Aspetta un po' per dare tempo di leggere le istruzioni
    print("Apertura del browser tra 3 secondi...")
    time.sleep(3)
    
    # Apri il browser
    print("Apertura del browser...")
    webbrowser.open("http://localhost:5000")
    
    print()
    print("=== STATO ===")
    print("✅ Browser aperto su http://localhost:5000")
    print("⚠️  Ricorda di avviare il server Flask manualmente!")
    print()
    print("Per avviare il server, apri un nuovo terminale e esegui:")
    print("cd C:\\Users\\anton\\Desktop\\cursor")
    print(".venv\\Scripts\\activate")
    print("python app.py")
    print()
    
    # Aspetta 10 secondi invece di usare input()
    print("Questa finestra si chiuderà automaticamente tra 10 secondi...")
    time.sleep(10)

if __name__ == "__main__":
    main() 