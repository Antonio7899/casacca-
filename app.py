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
            }
            .login-btn:hover {
                background: #5a6fd8;
            }
            .back-link {
                text-align: center;
                margin-top: 20px;
            }
            .back-link a {
                color: #667eea;
                text-decoration: none;
            }
        </style>
    </head>
    <body>
        <div class="login-container">
            <h1>🔐 Login</h1>
            <form method="POST">
                <div class="form-group">
                    <label for="username">Username:</label>
                    <input type="text" id="username" name="username" required>
                </div>
                <div class="form-group">
                    <label for="password">Password:</label>
                    <input type="password" id="password" name="password" required>
                </div>
                <button type="submit" class="login-btn">Accedi</button>
            </form>
            <div class="back-link">
                <a href="/">← Torna alla home</a>
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
        
        if User.query.filter_by(username=username).first():
            flash('Username già esistente!', 'error')
        else:
            user = User(username=username, password_hash=generate_password_hash(password))
            db.session.add(user)
            db.session.commit()
            flash('Registrazione effettuata con successo!', 'success')
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
            }
            .register-btn:hover {
                background: #5a6fd8;
            }
            .back-link {
                text-align: center;
                margin-top: 20px;
            }
            .back-link a {
                color: #667eea;
                text-decoration: none;
            }
        </style>
    </head>
    <body>
        <div class="register-container">
            <h1>📝 Registrazione</h1>
            <form method="POST">
                <div class="form-group">
                    <label for="username">Username:</label>
                    <input type="text" id="username" name="username" required>
                </div>
                <div class="form-group">
                    <label for="password">Password:</label>
                    <input type="password" id="password" name="password" required>
                </div>
                <button type="submit" class="register-btn">Registrati</button>
            </form>
            <div class="back-link">
                <a href="/">← Torna alla home</a>
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
        <title>Dashboard - Sistema di Gestione Steward</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body {
                font-family: Arial, sans-serif;
                margin: 0;
                padding: 20px;
                background: #f5f5f5;
            }
            .dashboard {
                max-width: 1200px;
                margin: 0 auto;
            }
            .header {
                background: white;
                padding: 20px;
                border-radius: 10px;
                margin-bottom: 20px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }
            .grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
                gap: 20px;
            }
            .card {
                background: white;
                padding: 20px;
                border-radius: 10px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }
            .card h3 {
                margin-top: 0;
                color: #333;
            }
            .btn {
                background: #667eea;
                color: white;
                padding: 10px 20px;
                border: none;
                border-radius: 5px;
                cursor: pointer;
                text-decoration: none;
                display: inline-block;
                margin: 5px;
            }
            .btn:hover {
                background: #5a6fd8;
            }
            @media (max-width: 600px) {
                .grid {
                    grid-template-columns: 1fr;
                }
            }
        </style>
    </head>
    <body>
        <div class="dashboard">
            <div class="header">
                <h1>🏆 Dashboard - Sistema di Gestione Steward</h1>
                <p>Benvenuto nel sistema di gestione completo per steward ed eventi</p>
            </div>
            
            <div class="grid">
                <div class="card">
                    <h3>👥 Gestione Steward</h3>
                    <p>Gestisci i profili degli steward, le loro informazioni e competenze.</p>
                    <a href="#" class="btn">Gestisci Steward</a>
                </div>
                
                <div class="card">
                    <h3>📅 Gestione Eventi</h3>
                    <p>Crea e gestisci eventi, assegna steward e monitora le attività.</p>
                    <a href="#" class="btn">Gestisci Eventi</a>
                </div>
                
                <div class="card">
                    <h3>✅ Controllo Presenze</h3>
                    <p>Registra presenze, check-in/out e monitora la partecipazione.</p>
                    <a href="#" class="btn">Controlla Presenze</a>
                </div>
                
                <div class="card">
                    <h3>💰 Gestione Transazioni</h3>
                    <p>Gestisci pagamenti, spese e report finanziari.</p>
                    <a href="#" class="btn">Gestisci Transazioni</a>
                </div>
                
                <div class="card">
                    <h3>📊 Report e Analisi</h3>
                    <p>Genera report, esporta dati e analizza le performance.</p>
                    <a href="#" class="btn">Visualizza Report</a>
                </div>
                
                <div class="card">
                    <h3>📁 Documenti</h3>
                    <p>Carica e gestisci documenti, contratti e certificazioni.</p>
                    <a href="#" class="btn">Gestisci Documenti</a>
                </div>
            </div>
        </div>
    </body>
    </html>
    '''

if __name__ == '__main__':
    # Per il deploy su hosting cloud
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False) 