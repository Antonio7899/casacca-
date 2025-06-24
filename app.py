from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
import pandas as pd
from datetime import datetime
import json

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///steward.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads'

db = SQLAlchemy(app)

# Modelli del database
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), default='user')

class Steward(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120))
    phone = db.Column(db.String(20))
    experience = db.Column(db.String(50))

class Event(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    date = db.Column(db.Date, nullable=False)
    location = db.Column(db.String(200))
    description = db.Column(db.Text)

class Presence(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    steward_id = db.Column(db.Integer, db.ForeignKey('steward.id'), nullable=False)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'), nullable=False)
    status = db.Column(db.String(20), default='present')
    check_in = db.Column(db.DateTime)
    check_out = db.Column(db.DateTime)

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    steward_id = db.Column(db.Integer, db.ForeignKey('steward.id'), nullable=False)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    type = db.Column(db.String(20))  # 'payment', 'expense'
    date = db.Column(db.DateTime, default=datetime.utcnow)
    description = db.Column(db.Text)

# Creazione delle tabelle
with app.app_context():
    db.create_all()

@app.route('/')
def index():
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Sistema di Gestione Steward</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body {
                font-family: Arial, sans-serif;
                margin: 0;
                padding: 20px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
            }
            .container {
                background: white;
                padding: 40px;
                border-radius: 15px;
                box-shadow: 0 10px 30px rgba(0,0,0,0.2);
                text-align: center;
                max-width: 500px;
                width: 100%;
            }
            h1 {
                color: #333;
                margin-bottom: 30px;
                font-size: 2.5em;
            }
            .status {
                background: #4CAF50;
                color: white;
                padding: 15px;
                border-radius: 8px;
                margin: 20px 0;
                font-size: 1.2em;
            }
            .info {
                background: #f0f0f0;
                padding: 20px;
                border-radius: 8px;
                margin: 20px 0;
                text-align: left;
            }
            .mobile-info {
                background: #e3f2fd;
                border-left: 4px solid #2196F3;
                padding: 15px;
                margin: 20px 0;
                text-align: left;
            }
            .button {
                background: #667eea;
                color: white;
                padding: 12px 24px;
                border: none;
                border-radius: 6px;
                cursor: pointer;
                font-size: 1.1em;
                margin: 10px;
                text-decoration: none;
                display: inline-block;
            }
            .button:hover {
                background: #5a6fd8;
            }
            @media (max-width: 600px) {
                .container {
                    margin: 10px;
                    padding: 20px;
                }
                h1 {
                    font-size: 2em;
                }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🏆 Sistema di Gestione Steward</h1>
            
            <div class="status">
                ✅ Backend attivo e funzionante!
            </div>
            
            <div class="info">
                <strong>📊 Funzionalità disponibili:</strong><br>
                • Gestione Steward<br>
                • Gestione Eventi<br>
                • Controllo Presenze<br>
                • Gestione Transazioni<br>
                • Import/Export Excel<br>
                • Upload Documenti
            </div>
            
            <div class="mobile-info">
                <strong>📱 Accesso Mobile:</strong><br>
                • Funziona su tutti i dispositivi<br>
                • Interfaccia responsive<br>
                • Accesso da browser mobile<br>
                • Nessuna app da installare
            </div>
            
            <a href="/login" class="button">🔐 Accedi</a>
            <a href="/register" class="button">📝 Registrati</a>
            
            <div style="margin-top: 30px; font-size: 0.9em; color: #666;">
                <strong>🌐 Accesso da mobile:</strong><br>
                Usa lo stesso indirizzo su smartphone/tablet
            </div>
        </div>
    </body>
    </html>
    '''

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            flash('Login effettuato con successo!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Username o password non validi!', 'error')
    
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Login - Sistema di Gestione Steward</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body {
                font-family: Arial, sans-serif;
                margin: 0;
                padding: 20px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
            }
            .login-container {
                background: white;
                padding: 40px;
                border-radius: 15px;
                box-shadow: 0 10px 30px rgba(0,0,0,0.2);
                width: 100%;
                max-width: 400px;
            }
            h1 {
                text-align: center;
                color: #333;
                margin-bottom: 30px;
            }
            .form-group {
                margin-bottom: 20px;
            }
            label {
                display: block;
                margin-bottom: 5px;
                color: #555;
                font-weight: bold;
            }
            input[type="text"], input[type="password"] {
                width: 100%;
                padding: 12px;
                border: 2px solid #ddd;
                border-radius: 6px;
                font-size: 16px;
                box-sizing: border-box;
            }
            input[type="text"]:focus, input[type="password"]:focus {
                border-color: #667eea;
                outline: none;
            }
            .login-btn {
                width: 100%;
                background: #667eea;
                color: white;
                padding: 12px;
                border: none;
                border-radius: 6px;
                font-size: 16px;
                cursor: pointer;
                transition: background 0.3s;
            }
            .login-btn:hover {
                background: #5a6fd8;
            }
            .register-link {
                text-align: center;
                margin-top: 20px;
            }
            .register-link a {
                color: #667eea;
                text-decoration: none;
            }
            .flash-message {
                padding: 15px;
                margin-bottom: 20px;
                border-radius: 6px;
            }
            .flash-success {
                background-color: #d4edda;
                color: #155724;
            }
            .flash-error {
                background-color: #f8d7da;
                color: #721c24;
            }
        </style>
    </head>
    <body>
        <div class="login-container">
            {% with messages = get_flashed_messages(with_categories=true) %}
                {% if messages %}
                    {% for category, message in messages %}
                        <div class="flash-message flash-{{ category }}">{{ message }}</div>
                    {% endfor %}
                {% endif %}
            {% endwith %}
            <h1>Login</h1>
            <form method="POST">
                <div class="form-group">
                    <label for="username">Username</label>
                    <input type="text" id="username" name="username" required>
                </div>
                <div class="form-group">
                    <label for="password">Password</label>
                    <input type="password" id="password" name="password" required>
                </div>
                <button type="submit" class="login-btn">Accedi</button>
            </form>
            <div class="register-link">
                <p>Non hai un account? <a href="/register">Registrati qui</a></p>
            </div>
        </div>
    </body>
    </html>
    '''

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        # Semplice validazione
        if User.query.filter_by(username=username).first():
            flash('Username già esistente!', 'error')
        else:
            new_user = User(username=username, password_hash=generate_password_hash(password, method='pbkdf2:sha256'))
            db.session.add(new_user)
            db.session.commit()
            flash('Registrazione avvenuta con successo! Effettua il login.', 'success')
            return redirect(url_for('login'))
            
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Registrazione - Sistema di Gestione Steward</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body {
                font-family: Arial, sans-serif;
                margin: 0;
                padding: 20px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
            }
            .register-container {
                background: white;
                padding: 40px;
                border-radius: 15px;
                box-shadow: 0 10px 30px rgba(0,0,0,0.2);
                width: 100%;
                max-width: 400px;
            }
            h1 {
                text-align: center;
                color: #333;
                margin-bottom: 30px;
            }
            .form-group {
                margin-bottom: 20px;
            }
            label {
                display: block;
                margin-bottom: 5px;
                color: #555;
                font-weight: bold;
            }
            input[type="text"], input[type="password"] {
                width: 100%;
                padding: 12px;
                border: 2px solid #ddd;
                border-radius: 6px;
                font-size: 16px;
                box-sizing: border-box;
            }
            input[type="text"]:focus, input[type="password"]:focus {
                border-color: #667eea;
                outline: none;
            }
            .register-btn {
                width: 100%;
                background: #667eea;
                color: white;
                padding: 12px;
                border: none;
                border-radius: 6px;
                font-size: 16px;
                cursor: pointer;
                transition: background 0.3s;
            }
            .register-btn:hover {
                background: #5a6fd8;
            }
            .login-link {
                text-align: center;
                margin-top: 20px;
            }
            .login-link a {
                color: #667eea;
                text-decoration: none;
            }
        </style>
    </head>
    <body>
        <div class="register-container">
             {% with messages = get_flashed_messages(with_categories=true) %}
                {% if messages %}
                    {% for category, message in messages %}
                        <div class="flash-message flash-{{ category }}">{{ message }}</div>
                    {% endfor %}
                {% endif %}
            {% endwith %}
            <h1>Registrati</h1>
            <form method="POST">
                <div class="form-group">
                    <label for="username">Username</label>
                    <input type="text" id="username" name="username" required>
                </div>
                <div class="form-group">
                    <label for="password">Password</label>
                    <input type="password" id="password" name="password" required>
                </div>
                <button type="submit" class="register-btn">Registrati</button>
            </form>
            <div class="login-link">
                <p>Hai già un account? <a href="/login">Accedi qui</a></p>
            </div>
        </div>
    </body>
    </html>
    '''

@app.route('/dashboard')
def dashboard():
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Dashboard - Gestione Steward</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body { 
                font-family: Arial, sans-serif; 
                margin: 0; 
                background-color: #f4f4f9; 
            }
            .header {
                background: #667eea;
                color: white;
                padding: 15px 30px;
                text-align: center;
                font-size: 1.5em;
            }
            .container {
                padding: 30px;
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
                gap: 30px;
            }
            .card {
                background: white;
                padding: 25px;
                border-radius: 10px;
                box-shadow: 0 5px 15px rgba(0,0,0,0.1);
                text-align: center;
            }
            .card h3 {
                margin-top: 0;
                color: #333;
                font-size: 1.4em;
            }
            .card p {
                color: #666;
                line-height: 1.6;
            }
            .btn {
                display: inline-block;
                margin-top: 15px;
                padding: 10px 20px;
                background: #667eea;
                color: white;
                text-decoration: none;
                border-radius: 5px;
                transition: background 0.3s;
            }
            .btn:hover {
                background: #5a6fd8;
            }
        </style>
    </head>
    <body>
        <div class="header">
            Dashboard di Gestione
        </div>
        <div class="container">
            <div class="card">
                <h3>👥 Gestione Steward</h3>
                <p>Gestisci i profili degli steward, le loro informazioni e competenze.</p>
                <a href="/stewards" class="btn">Gestisci Steward</a>
            </div>
            
            <div class="card">
                <h3>📅 Gestione Eventi</h3>
                <p>Crea nuovi eventi, modifica quelli esistenti e visualizza il calendario.</p>
                <a href="#" class="btn">Gestisci Eventi</a>
            </div>
            
            <div class="card">
                <h3>✅ Controllo Presenze</h3>
                <p>Registra le presenze degli steward agli eventi e visualizza i report.</p>
                <a href="#" class="btn">Controlla Presenze</a>
            </div>

            <div class="card">
                <h3>💰 Gestione Transazioni</h3>
                <p>Traccia pagamenti, rimborsi e spese relative a steward ed eventi.</p>
                <a href="#" class="btn">Gestisci Transazioni</a>
            </div>

            <div class="card">
                <h3>📤 Importa/Esporta</h3>
                <p>Carica dati da file Excel o esporta i dati del sistema.</p>
                <a href="#" class="btn">Importa/Esporta</a>
            </div>

            <div class="card">
                <h3>⚙️ Impostazioni</h3>
                <p>Configura le impostazioni generali dell'applicazione.</p>
                <a href="/logout" class="btn">Logout</a>
            </div>
        </div>
    </body>
    </html>
    '''

@app.route('/stewards')
def stewards():
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Gestione Steward</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; background-color: #f4f4f9; }
            h1 { color: #333; }
            a { 
                display: inline-block; 
                margin-top: 20px; 
                padding: 10px 15px; 
                background-color: #667eea; 
                color: white; 
                text-decoration: none; 
                border-radius: 5px;
            }
            a:hover { background-color: #5a6fd8; }
        </style>
    </head>
    <body>
        <h1>Gestione Steward</h1>
        <p>Questa è la pagina per la gestione degli steward. Prossimamente qui potrai aggiungere, modificare e visualizzare gli steward.</p>
        <a href="/dashboard">Torna alla Dashboard</a>
    </body>
    </html>
    '''

@app.route('/logout')
def logout():
    # Qui in futuro gestiremo la logica di sessione
    return redirect(url_for('login'))


# API Endpoints (Esempi, da implementare)

# GESTIONE STEWARD (CRUD)
@app.route('/api/stewards', methods=['GET'])
def get_stewards():
    stewards = Steward.query.all()
    return jsonify([{'id': s.id, 'name': s.name, 'email': s.email, 'phone': s.phone, 'experience': s.experience} for s in stewards])

@app.route('/api/stewards', methods=['POST'])
def add_steward():
    data = request.get_json()
    new_steward = Steward(name=data['name'], email=data.get('email'), phone=data.get('phone'), experience=data.get('experience'))
    db.session.add(new_steward)
    db.session.commit()
    return jsonify({'id': new_steward.id, 'name': new_steward.name}), 201

# ... Altri endpoint per update, delete, ecc.


# GESTIONE EVENTI (CRUD)
# ...


# GESTIONE PRESENZE
# ...


# GESTIONE TRANSAZIONI
# ...


# UPLOAD E EXPORT
# ...


if __name__ == '__main__':
    # Per il deploy su hosting cloud
    # app.run() # Questo è per il locale
    # Il Procfile userà gunicorn, quindi questa parte non verrà eseguita in produzione
    app.run(debug=True)