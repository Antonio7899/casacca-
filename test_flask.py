from flask import Flask
app = Flask(__name__)

@app.route("/")
def home():
    return "Test Flask - Funziona!"

if __name__ == "__main__":
    print("Avvio server Flask di test...")
    app.run(host='0.0.0.0', port=5000) 