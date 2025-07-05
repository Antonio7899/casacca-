from flask import Flask, request, redirect, url_for, flash, get_flashed_messages, send_file, render_template_string, send_from_directory, jsonify, make_response, render_template, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import pandas as pd
import io
import os
from werkzeug.utils import secure_filename
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
import datetime
from datetime import date
import urllib.parse
import tempfile
import csv
import requests
from collections import Counter, defaultdict
from io import BytesIO
from reportlab.lib import colors
from reportlab.platypus import Table, TableStyle
import calendar

# 1. INIZIALIZZAZIONE
app = Flask(__name__)
app.config['SECRET_KEY'] = 'una-chiave-segreta-molto-difficile-da-indovinare'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///steward_v3.db'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
db = SQLAlchemy(app)


# 2. MODELLI DEL DATABASE (con anagrafica completa)
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)

class Steward(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    # Dati base
    nome = db.Column(db.String(50), nullable=False)
    cognome = db.Column(db.String(50), nullable=False)
    email = db.Column(db.String(120), unique=True)
    phone = db.Column(db.String(20))
    # Dati anagrafici
    address = db.Column(db.String(200))
    tax_code = db.Column(db.String(16), unique=True)
    iban = db.Column(db.String(27))
    # Dati documenti
    document_type = db.Column(db.String(50))
    document_number = db.Column(db.String(50))
    document_expiry = db.Column(db.Date)
    experience = db.Column(db.String(100))
    # Percorsi file documenti
    carta_identita_path = db.Column(db.String(255), nullable=False)
    codice_fiscale_path = db.Column(db.String(255), nullable=False)
    attestato_path = db.Column(db.String(255), nullable=False)
    autocertificazione_path = db.Column(db.String(255), nullable=False)
    patente_path = db.Column(db.String(255), nullable=False)

# --- NUOVO MODELLO FINANZIARIO ---
class MovimentoFinanziario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    steward_id = db.Column(db.Integer, db.ForeignKey('steward.id'), nullable=False)
    data = db.Column(db.Date, nullable=False, default=datetime.datetime.utcnow)
    descrizione = db.Column(db.String(255), nullable=False)
    importo = db.Column(db.Float, nullable=False)
    tipo = db.Column(db.String(10), nullable=False)  # 'entrata' o 'uscita'
    note = db.Column(db.String(255))
    allegato_path = db.Column(db.String(255))  # opzionale
    metodo_pagamento = db.Column(db.String(50))  # Nuovo campo
    pagamento_anticipato = db.Column(db.Boolean, default=False)  # Nuovo campo
    evento_id = db.Column(db.Integer, db.ForeignKey('evento.id'))  # Collega il pagamento all'evento
    pagato = db.Column(db.Boolean, default=False)  # Nuovo campo: True se il pagamento è stato effettuato
    steward = db.relationship('Steward', backref=db.backref('movimenti', lazy=True))

class Evento(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(200), nullable=False)
    descrizione = db.Column(db.Text)
    data_inizio = db.Column(db.DateTime, nullable=False)
    data_fine = db.Column(db.DateTime, nullable=False)
    luogo = db.Column(db.String(200))
    tipo_evento = db.Column(db.String(100))  # es. 'Sportivo', 'Culturale', 'Musicale', etc.
    stato = db.Column(db.String(20), default='pianificato')  # 'pianificato', 'in_corso', 'completato', 'cancellato'
    budget = db.Column(db.Float)
    note = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

class PartecipazioneEvento(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    evento_id = db.Column(db.Integer, db.ForeignKey('evento.id'), nullable=False)
    steward_id = db.Column(db.Integer, db.ForeignKey('steward.id'), nullable=False)
    ruolo = db.Column(db.String(100))  # es. 'Capo Steward', 'Steward', 'Supporto'
    numero_casacca = db.Column(db.Integer)  # Numero di casacca per l'evento
    data_assegnazione = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    stato = db.Column(db.String(20), default='assegnato')  # 'assegnato', 'confermato', 'rifiutato', 'completato'
    note = db.Column(db.Text)
    presente = db.Column(db.Boolean, default=True)  # Nuovo campo: True se presente, False se assente
    evento = db.relationship('Evento', backref=db.backref('partecipazioni', lazy=True))
    steward = db.relationship('Steward', backref=db.backref('partecipazioni_eventi', lazy=True))

class NotaSpese(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    steward_id = db.Column(db.Integer, db.ForeignKey('steward.id'), nullable=False)
    evento_id = db.Column(db.Integer, db.ForeignKey('evento.id'), nullable=False)
    data = db.Column(db.Date, nullable=False, default=datetime.datetime.utcnow)
    importo = db.Column(db.Float, nullable=False)
    descrizione = db.Column(db.String(255), nullable=False)
    allegato_path = db.Column(db.String(255))
    stato = db.Column(db.String(20), default='in_attesa')  # in_attesa, approvata, rifiutata
    steward = db.relationship('Steward', backref=db.backref('note_spese', lazy=True))
    evento = db.relationship('Evento', backref=db.backref('note_spese', lazy=True))

# Crea le tabelle se non esistono
with app.app_context():
    db.create_all()
    
    # Migrazione: aggiungi colonna numero_casacca se non esiste
    try:
        with db.engine.connect() as conn:
            # Controlla se la colonna numero_casacca esiste
            result = conn.execute(db.text("PRAGMA table_info(partecipazione_evento)"))
            columns = [row[1] for row in result.fetchall()]
            
            if 'numero_casacca' not in columns:
                # Aggiungi la colonna numero_casacca
                conn.execute(db.text("ALTER TABLE partecipazione_evento ADD COLUMN numero_casacca INTEGER"))
                conn.commit()
                print("✅ Colonna numero_casacca aggiunta alla tabella partecipazione_evento")
            # Nuova migrazione: aggiungi colonna 'presente' se non esiste
            if 'presente' not in columns:
                conn.execute(db.text("ALTER TABLE partecipazione_evento ADD COLUMN presente BOOLEAN DEFAULT 1"))
                conn.commit()
                print("✅ Colonna presente aggiunta alla tabella partecipazione_evento")
    except Exception as e:
        print(f"⚠️ Errore durante la migrazione: {e}")
        # Se c'è un errore, ricrea il database
        try:
            db.drop_all()
            db.create_all()
            print("✅ Database ricreato con successo")
        except Exception as e2:
            print(f"❌ Errore nella ricreazione del database: {e2}")

# Migrazione: aggiungi colonne se non esistono
with app.app_context():
    db.create_all()
    try:
        with db.engine.connect() as conn:
            result = conn.execute(db.text("PRAGMA table_info(movimento_finanziario)"))
            columns = [row[1] for row in result.fetchall()]
            if 'metodo_pagamento' not in columns:
                conn.execute(db.text("ALTER TABLE movimento_finanziario ADD COLUMN metodo_pagamento VARCHAR(50)"))
                conn.commit()
            if 'pagamento_anticipato' not in columns:
                conn.execute(db.text("ALTER TABLE movimento_finanziario ADD COLUMN pagamento_anticipato BOOLEAN DEFAULT 0"))
                conn.commit()
            if 'evento_id' not in columns:
                conn.execute(db.text("ALTER TABLE movimento_finanziario ADD COLUMN evento_id INTEGER"))
                conn.commit()
            if 'pagato' not in columns:
                conn.execute(db.text("ALTER TABLE movimento_finanziario ADD COLUMN pagato BOOLEAN DEFAULT 0"))
                conn.commit()
    except Exception as e:
        print(f"⚠️ Errore durante la migrazione finanza: {e}")

# Migrazione automatica tabella nota spese
with app.app_context():
    db.create_all()
    try:
        with db.engine.connect() as conn:
            result = conn.execute(db.text("PRAGMA table_info(nota_spese)"))
            columns = [row[1] for row in result.fetchall()]
            if 'importo' not in columns:
                conn.execute(db.text("CREATE TABLE IF NOT EXISTS nota_spese (id INTEGER PRIMARY KEY, steward_id INTEGER, evento_id INTEGER, data DATE, importo FLOAT, descrizione VARCHAR(255), allegato_path VARCHAR(255), stato VARCHAR(20))"))
                conn.commit()
    except Exception as e:
        print(f"⚠️ Errore durante la migrazione nota spese: {e}")


# 3. PAGINE PRINCIPALI (Login, Registrazione, Dashboard)
@app.route('/')
def index():
    return '''
    <!DOCTYPE html><html><head><title>Sistema Gestione Steward</title><meta name="viewport" content="width=device-width, initial-scale=1.0"><style>body{font-family:Arial,sans-serif;margin:0;padding:20px;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);min-height:100vh;display:flex;align-items:center;justify-content:center}.container{background:white;padding:40px;border-radius:15px;box-shadow:0 10px 30px rgba(0,0,0,0.2);text-align:center;max-width:500px;width:100%}h1{color:#333;margin-bottom:30px;font-size:2.5em}.button{background:#667eea;color:white;padding:12px 24px;border:none;border-radius:6px;cursor:pointer;font-size:1.1em;margin:10px;text-decoration:none;display:inline-block}.button:hover{background:#5a6fd8}</style></head><body><div class="container"><h1>🏆 Sistema di Gestione Steward</h1><a href="/login" class="button">🔐 Accedi</a><a href="/register" class="button">📝 Registrati</a></div></body></html>
    '''

def render_form_page(title, form_html, link_html, messages_html=''):
    return render_template_string('''
    <!DOCTYPE html><html><head><title>{{ title }}</title><meta name="viewport" content="width=device-width, initial-scale=1.0"><style>body{font-family:Arial,sans-serif;margin:0;padding:20px;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);display:flex;align-items:center;justify-content:center;min-height:100vh}.form-container{background:white;padding:40px;border-radius:15px;box-shadow:0 10px 30px rgba(0,0,0,0.2);width:100%;max-width:400px}h1{text-align:center;color:#333;margin-bottom:30px}.form-group{margin-bottom:20px}label{display:block;margin-bottom:5px;color:#555;font-weight:bold}input[type="text"],input[type="password"],input[type="email"]{width:100%;padding:12px;border:2px solid #ddd;border-radius:6px;font-size:16px;box-sizing:border-box}.btn{width:100%;background:#667eea;color:white;padding:12px;border:none;border-radius:6px;font-size:16px;cursor:pointer}.link{text-align:center;margin-top:20px}.link a{color:#667eea;text-decoration:none}.flash-message{padding:15px;margin-bottom:20px;border-radius:6px;text-align:center;display:flex;align-items:center;gap:10px;font-weight:bold}.flash-success{background-color:#d4edda;color:#155724;border:1px solid #c3e6cb}.flash-error{background-color:#f8d7da;color:#721c24;border:1px solid #f5c6cb}.flash-warning{background-color:#fff3cd;color:#856404;border:1px solid #ffeeba}</style></head><body><div class="form-container">{{ messages_html|safe }}<h1>{{ title }}</h1><form method="POST">{{ form_html|safe }}<button type="submit" class="btn">{{ title }}</button></form><div class="link">{{ link_html|safe }}</div></div></body></html>
    ''', title=title, form_html=form_html, link_html=link_html, messages_html=messages_html)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and password and check_password_hash(user.password_hash, password):
            session['username'] = username  # <--- AGGIUNTO
            return redirect(url_for('dashboard'))
        else:
            flash('⚠️ Username o password non validi!', 'warning')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        if User.query.filter_by(username=username).first():
            flash('⚠️ Username già esistente!', 'warning')
        elif not password:
            flash('❌ La password non può essere vuota!', 'error')
        else:
            new_user = User(username=username, password_hash=generate_password_hash(password, method='pbkdf2:sha256'))
            db.session.add(new_user)
            db.session.commit()
            flash('✅ Registrazione avvenuta con successo! Ora puoi effettuare il login.', 'success')
            return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/dashboard')
def dashboard():
    from datetime import datetime, timedelta, date
    from collections import Counter, defaultdict
    import calendar
    # Statistiche principali
    num_stewards = Steward.query.count()
    num_eventi = Evento.query.count()
    saldo = sum(m.importo if m.tipo == 'entrata' else -m.importo for m in MovimentoFinanziario.query.all())
    oggi = datetime.now()
    eventi_imminenti = Evento.query.filter(Evento.data_inizio >= oggi, Evento.data_inizio <= oggi + timedelta(days=7)).count()
    # Distribuzione eventi per tipo
    tipi_evento = [e.tipo_evento or 'Altro' for e in Evento.query.all()]
    tipo_labels = list(set(tipi_evento))
    tipo_data = [tipi_evento.count(t) for t in tipo_labels]
    # Distribuzione eventi per stato
    stati_evento = [e.stato or 'pianificato' for e in Evento.query.all()]
    stato_labels = list(set(stati_evento))
    stato_data = [stati_evento.count(s) for s in stato_labels]
    # Ultimi 5 eventi
    ultimi_eventi = Evento.query.order_by(Evento.data_inizio.desc()).limit(5).all()
    # Saldo per mese (ultimi 12 mesi)
    movimenti = MovimentoFinanziario.query.all()
    saldo_per_mese = defaultdict(float)
    for m in movimenti:
        key = m.data.strftime('%Y-%m')
        saldo_per_mese[key] += m.importo if m.tipo == 'entrata' else -m.importo
    mesi_ordinati = sorted(saldo_per_mese.keys())[-12:]
    saldi_mensili = [saldo_per_mese[m] for m in mesi_ordinati]
    # METEO prossimo evento
    meteo_info_dashboard = None
    prossimo_evento = Evento.query.filter(Evento.data_inizio >= oggi).order_by(Evento.data_inizio.asc()).first()
    if prossimo_evento and prossimo_evento.luogo and prossimo_evento.data_inizio:
        try:
            geo_url = f"https://nominatim.openstreetmap.org/search?format=json&q={prossimo_evento.luogo}"
            geo_resp = requests.get(geo_url, headers={"User-Agent": "StewardApp/1.0"}, timeout=5)
            geo_data = geo_resp.json()
            if geo_data:
                lat = geo_data[0]['lat']
                lon = geo_data[0]['lon']
                data_str = prossimo_evento.data_inizio.strftime('%Y-%m-%d')
                meteo_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,weathercode&timezone=Europe/Rome&start_date={data_str}&end_date={data_str}"
                meteo_resp = requests.get(meteo_url, timeout=5)
                meteo_data = meteo_resp.json()
                if 'daily' in meteo_data and meteo_data['daily']['time']:
                    idx = 0
                    tmax = meteo_data['daily']['temperature_2m_max'][idx]
                    tmin = meteo_data['daily']['temperature_2m_min'][idx]
                    rain = meteo_data['daily']['precipitation_sum'][idx]
                    code = meteo_data['daily']['weathercode'][idx]
                    code_map = {
                        0: ("Soleggiato", "☀️"),
                        1: ("Prevalentemente sereno", "🌤️"),
                        2: ("Parzialmente nuvoloso", "⛅"),
                        3: ("Coperto", "☁️"),
                        45: ("Nebbia", "🌫️"),
                        48: ("Nebbia gelata", "🌫️❄️"),
                        51: ("Pioviggine leggera", "🌦️"),
                        53: ("Pioviggine", "🌦️"),
                        55: ("Pioviggine intensa", "🌧️"),
                        61: ("Pioggia leggera", "🌦️"),
                        63: ("Pioggia", "🌧️"),
                        65: ("Pioggia intensa", "🌧️"),
                        71: ("Neve leggera", "🌨️"),
                        73: ("Neve", "🌨️"),
                        75: ("Neve intensa", "❄️"),
                        80: ("Rovesci leggeri", "🌦️"),
                        81: ("Rovesci", "🌧️"),
                        82: ("Rovesci forti", "⛈️"),
                    }
                    desc, icon = code_map.get(code, ("", "❓"))
                    meteo_info_dashboard = {
                        'desc': desc,
                        'icon': icon,
                        'tmin': tmin,
                        'tmax': tmax,
                        'rain': rain,
                        'evento': prossimo_evento
                    }
        except Exception as e:
            meteo_info_dashboard = {'desc': 'Errore nel recupero meteo', 'icon': '❓', 'tmin': '', 'tmax': '', 'rain': '', 'evento': prossimo_evento}
    # --- CALENDARIO ---
    eventi = Evento.query.order_by(Evento.data_inizio.asc()).all()
    eventi_cal = [
        {
            'id': e.id,
            'title': e.nome,
            'start': e.data_inizio.strftime('%Y-%m-%d'),
            'end': e.data_fine.strftime('%Y-%m-%d'),
            'color': '#28a745' if e.stato == 'completato' else '#17a2b8' if e.stato == 'pianificato' else '#dc3545' if e.stato == 'cancellato' else '#ffc107',
            'descrizione': e.descrizione or ''
        }
        for e in eventi
    ]
    # Festività italiane principali (fisse + Pasqua)
    def get_italian_holidays(year):
        # Feste fisse
        holidays = [
            (1, 1, "Capodanno"),
            (1, 6, "Epifania"),
            (4, 25, "Liberazione"),
            (5, 1, "Festa del Lavoro"),
            (6, 2, "Festa della Repubblica"),
            (8, 15, "Ferragosto"),
            (11, 1, "Ognissanti"),
            (12, 8, "Immacolata"),
            (12, 25, "Natale"),
            (12, 26, "S. Stefano")
        ]
        # Calcolo Pasqua (algoritmo di Gauss)
        a = year % 19
        b = year // 100
        c = year % 100
        d = b // 4
        e = b % 4
        f = (b + 8) // 25
        g = (b - f + 1) // 3
        h = (19 * a + b - d - g + 15) % 30
        i = c // 4
        k = c % 4
        l = (32 + 2 * e + 2 * i - h - k) % 7
        m = (a + 11 * h + 22 * l) // 451
        month = (h + l - 7 * m + 114) // 31
        day = ((h + l - 7 * m + 114) % 31) + 1
        holidays.append((month, day, "Pasqua"))
        return holidays
    # Prendo festività per quest'anno e il prossimo
    today = date.today()
    holidays = get_italian_holidays(today.year) + get_italian_holidays(today.year+1)
    holidays_list = [
        {
            'date': date(today.year if m >= today.month else today.year+1, m, d).strftime('%Y-%m-%d'),
            'label': label
        }
        for m, d, label in holidays
    ]
    # Domeniche dell'anno corrente e prossimo
    sundays = []
    for y in [today.year, today.year+1]:
        for m in range(1, 13):
            for d in range(1, calendar.monthrange(y, m)[1]+1):
                if date(y, m, d).weekday() == 6:
                    sundays.append(date(y, m, d).strftime('%Y-%m-%d'))
    return render_template('dashboard.html',
        num_stewards=num_stewards,
        num_eventi=num_eventi,
        saldo=saldo,
        eventi_imminenti=eventi_imminenti,
        tipo_labels=tipo_labels,
        tipo_data=tipo_data,
        stato_labels=stato_labels,
        stato_data=stato_data,
        ultimi_eventi=ultimi_eventi,
        mesi_ordinati=mesi_ordinati,
        saldi_mensili=saldi_mensili,
        meteo_info_dashboard=meteo_info_dashboard,
        eventi_cal=eventi_cal,
        holidays_list=holidays_list,
        sundays=sundays
    )

def send_document_notifications(stewards_list, scadenza_limite):
    # Placeholder: in produzione inviare email o notifiche reali
    notifications = []
    for s in stewards_list:
        missing_docs = []
        if not s.carta_identita_path:
            missing_docs.append("Carta d'Identità")
        if not s.codice_fiscale_path:
            missing_docs.append("Codice Fiscale")
        if not s.attestato_path:
            missing_docs.append("Attestato")
        if not s.autocertificazione_path:
            missing_docs.append("Autocertificazione")
        if not s.patente_path:
            missing_docs.append("Patente")
        is_expiring = s.document_expiry and s.document_expiry <= scadenza_limite
        if missing_docs or is_expiring:
            notifications.append(f"Notifica per {s.nome} {s.cognome}: "+
                (f"Documenti mancanti: {', '.join(missing_docs)}. " if missing_docs else '')+
                ("Documenti in scadenza." if is_expiring else ''))
    if notifications:
        print("[NOTIFICHE DOCUMENTI]")
        for n in notifications:
            print(n)

@app.route('/stewards', methods=['GET', 'POST'])
def stewards():
    from datetime import datetime, timedelta
    scadenza_limite = (datetime.now() + timedelta(days=30)).date()
    filter_missing = request.args.get('missing', '') == '1'
    filter_expiring = request.args.get('expiring', '') == '1'
    stewards_list = Steward.query.order_by(Steward.nome, Steward.cognome).all()
    send_document_notifications(stewards_list, scadenza_limite)
    filtered_stewards = []
    count_missing = 0
    count_expiring = 0
    for s in stewards_list:
        missing_docs = []
        if not s.carta_identita_path:
            missing_docs.append("Carta d'Identità")
        if not s.codice_fiscale_path:
            missing_docs.append("Codice Fiscale")
        if not s.attestato_path:
            missing_docs.append("Attestato")
        if not s.autocertificazione_path:
            missing_docs.append("Autocertificazione")
        if not s.patente_path:
            missing_docs.append("Patente")
        is_expiring = s.document_expiry and s.document_expiry <= scadenza_limite
        if missing_docs:
            count_missing += 1
        if is_expiring:
            count_expiring += 1
        if filter_missing and not missing_docs:
            continue
        if filter_expiring and not is_expiring:
            continue
        filtered_stewards.append(s)
    return render_template('stewards.html', stewards=filtered_stewards, scadenza_limite=scadenza_limite, count_missing=count_missing, count_expiring=count_expiring, filter_missing=filter_missing, filter_expiring=filter_expiring)

@app.route('/steward/<int:steward_id>/edit', methods=['GET', 'POST'])
def edit_steward(steward_id):
    import os
    steward = Steward.query.get_or_404(steward_id)
    if request.method == 'POST':
        steward.nome = request.form.get('nome')
        steward.cognome = request.form.get('cognome')
        steward.email = request.form.get('email')
        steward.phone = request.form.get('phone')
        steward.address = request.form.get('address')
        steward.tax_code = request.form.get('tax_code')
        steward.iban = request.form.get('iban')
        steward.document_type = request.form.get('document_type')
        steward.document_number = request.form.get('document_number')
        expiry_date_str = request.form.get('document_expiry')
        steward.document_expiry = datetime.datetime.strptime(expiry_date_str, '%Y-%m-%d').date() if expiry_date_str else None
        steward.experience = request.form.get('experience')

        upload_folder = os.path.join(os.getcwd(), 'uploads')
        os.makedirs(upload_folder, exist_ok=True)
        def update_file(field_name, current_path):
            file = request.files.get(field_name)
            if file and file.filename != '':
                filename = f"{field_name}_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}"
                file_path = os.path.join(upload_folder, filename)
                file.save(file_path)
                return file_path
            return current_path
        steward.carta_identita_path = update_file('carta_identita', steward.carta_identita_path)
        steward.codice_fiscale_path = update_file('codice_fiscale', steward.codice_fiscale_path)
        steward.attestato_path = update_file('attestato', steward.attestato_path)
        steward.autocertificazione_path = update_file('autocertificazione', steward.autocertificazione_path)
        steward.patente_path = update_file('patente', steward.patente_path)

        db.session.commit()
        flash('Dati steward aggiornati con successo!', 'success')
        return redirect(url_for('stewards'))

    # Form di modifica con visualizzazione link ai documenti
    def file_link(label, path, field):
        if path:
            filename = os.path.basename(path)
            return f'<div class="form-group"><label>{label}:</label> <a href="/download/{steward.id}/{field}" target="_blank">{filename}</a><br><input type="file" name="{field}" accept="image/*,.pdf"></div>'
        else:
            return f'<div class="form-group"><label>{label}:</label> <input type="file" name="{field}" accept="image/*,.pdf" required></div>'
    form_html = f'''
        <form method="POST" enctype="multipart/form-data"><div class="form-grid">
        <div class="form-group"><label for="nome">Nome</label><input type="text" id="nome" name="nome" value="{steward.nome}" required></div>
        <div class="form-group"><label for="cognome">Cognome</label><input type="text" id="cognome" name="cognome" value="{steward.cognome}" required></div>
        <div class="form-group"><label for="email">Email</label><input type="email" id="email" name="email" value="{steward.email or ''}"></div>
        <div class="form-group"><label for="phone">Telefono</label><input type="text" id="phone" name="phone" value="{steward.phone or ''}"></div>
        <div class="form-group"><label for="address">Indirizzo</label><input type="text" id="address" name="address" value="{steward.address or ''}"></div>
        <div class="form-group"><label for="tax_code">Codice Fiscale</label><input type="text" id="tax_code" name="tax_code" value="{steward.tax_code or ''}"></div>
        <div class="form-group"><label for="iban">IBAN</label><input type="text" id="iban" name="iban" value="{steward.iban or ''}"></div>
        <div class="form-group"><label for="document_type">Tipo Documento</label><input type="text" id="document_type" name="document_type" value="{steward.document_type or ''}"></div>
        <div class="form-group"><label for="document_number">Numero Documento</label><input type="text" id="document_number" name="document_number" value="{steward.document_number or ''}"></div>
        <div class="form-group"><label for="document_expiry">Data Scadenza Documento</label><input type="date" id="document_expiry" name="document_expiry" value="{steward.document_expiry.strftime('%Y-%m-%d') if steward.document_expiry else ''}"></div>
        <div class="form-group"><label for="experience">Esperienza</label><input type="text" id="experience" name="experience" value="{steward.experience or ''}"></div>
        {file_link("Carta d'Identità", steward.carta_identita_path, 'carta_identita')}
        {file_link("Codice Fiscale", steward.codice_fiscale_path, 'codice_fiscale')}
        {file_link("Attestato", steward.attestato_path, 'attestato')}
        {file_link("Autocertificazione", steward.autocertificazione_path, 'autocertificazione')}
        {file_link("Patente", steward.patente_path, 'patente')}
        </div><button type="submit" class="btn">Salva Modifiche</button></form>
    '''
    messages_html = ''.join(f'<div class="flash-message flash-{c}"><span style="font-size:1.2em;">{"✅" if c == "success" else "❌" if c == "error" else "⚠️"}</span><span>{m}</span></div>' for c, m in get_flashed_messages(with_categories=True))
    return f'''
    <!DOCTYPE html><html><head><title>Modifica Steward</title><meta name="viewport" content="width=device-width, initial-scale=1.0"><style>body{{font-family:Arial,sans-serif;margin:0;background-color:#f4f4f9}}.container{{max-width:800px;margin:20px auto;background:white;padding:20px 30px;border-radius:10px;box-shadow:0 5px 15px rgba(0,0,0,0.1)}}h1,h2{{color:#667eea;text-align:center}}.form-container{{background:#f9f9f9;padding:20px;border-radius:8px;margin-bottom:30px}}.form-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:20px}}.form-group{{margin-bottom:15px}}.form-group label{{display:block;margin-bottom:5px;font-weight:bold}}.form-group input{{width:100%;padding:10px;border:1px solid #ccc;border-radius:4px;box-sizing:border-box}}.btn{{padding:10px 15px;background-color:#667eea;color:white;border:none;border-radius:5px;cursor:pointer;text-decoration:none;display:inline-block;width:auto;text-align:center;margin-top:10px}}.flash-message{{padding:15px;margin:20px 0;border-radius:6px;text-align:center}}.flash-success{{background-color:#d4edda;color:#155724}}.flash-error{{background-color:#f8d7da;color:#721c24}}</style></head><body><div class="container">{messages_html}<h2>Modifica Steward</h2><div class="form-container">{form_html}</div><a href="/stewards" class="btn" style="background-color:#777; max-width:200px;">Torna alla Gestione Steward</a></div></body></html>
    '''

@app.route('/download/<int:steward_id>/<field>')
def download_document(steward_id, field):
    steward = Steward.query.get_or_404(steward_id)
    path = getattr(steward, f'{field}_path', None)
    if not path or not os.path.exists(path):
        return 'File non trovato', 404
    return send_file(path, as_attachment=True)

@app.route('/finanze', methods=['GET', 'POST'])
def finanze():
    from werkzeug.utils import secure_filename
    # Prendi username dalla sessione di login
    username = session.get('username', None)
    user = User.query.filter_by(username=username).first() if username else None
    is_admin = username == 'admin'
    print(f"[DEBUG] username: {username} | is_admin: {is_admin}")
    # Aggiunta movimento
    if request.method == 'POST':
        steward = Steward.query.filter_by(email=username).first() if user else None
        if not steward:
            flash('Utente non trovato o non autorizzato.', 'error')
            return redirect(url_for('finanze', username=username))
        data = request.form.get('data')
        descrizione = request.form.get('descrizione')
        importo = float(request.form.get('importo', 0))
        tipo = request.form.get('tipo')
        note = request.form.get('note')
        allegato = request.files.get('allegato')
        allegato_path = ''
        if allegato and allegato.filename:
            if not (allegato.filename.lower().endswith('.jpg') or allegato.filename.lower().endswith('.jpeg') or allegato.filename.lower().endswith('.pdf')):
                flash('L\'allegato deve essere JPG, JPEG o PDF.', 'warning')
                return redirect(url_for('finanze', username=username))
            upload_folder = os.path.join(os.getcwd(), 'uploads')
            os.makedirs(upload_folder, exist_ok=True)
            filename = f"allegato_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}_{secure_filename(allegato.filename)}"
            allegato_path = os.path.join(upload_folder, filename)
            allegato.save(allegato_path)
        nuovo = MovimentoFinanziario(
            steward_id=steward.id,
            data=datetime.datetime.strptime(data, '%Y-%m-%d').date() if data else datetime.date.today(),
            descrizione=descrizione,
            importo=importo,
            tipo=tipo,
            note=note,
            allegato_path=allegato_path
        )
        db.session.add(nuovo)
        db.session.commit()
        flash('Movimento aggiunto con successo!', 'success')
        return redirect(url_for('finanze', username=username))

    # Eliminazione movimento
    delete_id = request.args.get('delete')
    if delete_id and delete_id.isdigit():
        movimento = MovimentoFinanziario.query.get(int(delete_id))
        if movimento and (is_admin or (user and movimento.steward_id == Steward.query.filter_by(email=username).first().id)):
            if movimento.allegato_path and os.path.exists(movimento.allegato_path):
                os.remove(movimento.allegato_path)
            db.session.delete(movimento)
            db.session.commit()
            flash('Movimento eliminato.', 'success')
            return redirect(url_for('finanze', username=username))

    # --- FILTRI AVANZATI ---
    data_da = request.args.get('data_da')
    data_a = request.args.get('data_a')
    tipo_f = request.args.get('tipo')
    descr_f = request.args.get('descr')
    imp_min = request.args.get('imp_min')
    imp_max = request.args.get('imp_max')

    # Preparo la query o la lista vuota
    if is_admin:
        movimenti = MovimentoFinanziario.query.order_by(MovimentoFinanziario.data.desc())
    else:
        steward = Steward.query.filter_by(email=username).first() if user else None
        if steward:
            movimenti = MovimentoFinanziario.query.filter_by(steward_id=steward.id).order_by(MovimentoFinanziario.data.desc())
        else:
            movimenti = []

    # Applica filtri solo se movimenti è una query
    if not isinstance(movimenti, list):
        if data_da:
            try:
                movimenti = movimenti.filter(MovimentoFinanziario.data >= datetime.datetime.strptime(data_da, '%Y-%m-%d').date())
            except: pass
        if data_a:
            try:
                movimenti = movimenti.filter(MovimentoFinanziario.data <= datetime.datetime.strptime(data_a, '%Y-%m-%d').date())
            except: pass
        if tipo_f and tipo_f in ['entrata', 'uscita']:
            movimenti = movimenti.filter(MovimentoFinanziario.tipo == tipo_f)
        if descr_f:
            movimenti = movimenti.filter(MovimentoFinanziario.descrizione.ilike(f'%{descr_f}%'))
        if imp_min:
            try:
                movimenti = movimenti.filter(MovimentoFinanziario.importo >= float(imp_min))
            except: pass
        if imp_max:
            try:
                movimenti = movimenti.filter(MovimentoFinanziario.importo <= float(imp_max))
            except: pass
        movimenti_list = movimenti.all()
        print(f"[DEBUG] Movimenti trovati (query): {len(movimenti_list)}")
        movimenti = movimenti_list
    else:
        print(f"[DEBUG] Movimenti trovati (lista): {len(movimenti)}")

    saldo = sum(m.importo if m.tipo == 'entrata' else -m.importo for m in movimenti)
    
    # Prepara i dati per la tabella
    movimenti_data = []
    for m in movimenti:
        movimenti_data.append({
            'data': m.data.strftime('%d-%m-%Y'),
            'descrizione': m.descrizione,
            'tipo': m.tipo.title(),
            'importo': m.importo,
            'note': m.note or '',
            'allegato_path': m.allegato_path,
            'id': m.id
        })
    
    # Prepara i messaggi flash
    flash_messages = []
    for c, m in get_flashed_messages(with_categories=True):
        icon = "✅" if c == "success" else "❌" if c == "error" else "⚠️"
        flash_messages.append({'category': c, 'message': m, 'icon': icon})
    
    return render_template_string('''
    <!DOCTYPE html><html><head><title>Finanze</title><meta name="viewport" content="width=device-width, initial-scale=1.0"><style>body{font-family:Arial,sans-serif;margin:0;background:#f4f4f9}.header{background:#667eea;color:white;padding:15px 30px;text-align:center;font-size:1.5em}.container{padding:30px;max-width:900px;margin:auto}table{width:100%;border-collapse:collapse;margin-top:20px}th,td{padding:10px;border:1px solid #ddd;text-align:left}th{background:#667eea;color:white}tr:nth-child(even){background:#f9f9f9}.saldo{margin-top:20px;font-size:1.2em;font-weight:bold}.btn{background:#667eea;color:white;padding:10px 20px;border:none;border-radius:5px;text-decoration:none;cursor:pointer}.form-row{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:20px}.form-row input,.form-row select{padding:8px;border-radius:5px;border:1px solid #ccc}.flash-message{padding:10px;margin-bottom:10px;border-radius:6px;text-align:center;display:flex;align-items:center;gap:10px;font-weight:bold}.flash-success{background-color:#d4edda;color:#155724;border:1px solid #c3e6cb}.flash-error{background-color:#f8d7da;color:#721c24;border:1px solid #f5c6cb}.flash-warning{background-color:#fff3cd;color:#856404;border:1px solid #ffeeba}</style></head><body><div class="header">Gestione Finanze</div><div class="container">{% for msg in flash_messages %}<div class="flash-message flash-{{ msg.category }}"><span style="font-size:1.2em;">{{ msg.icon }}</span><span>{{ msg.message }}</span></div>{% endfor %}<a href="/dashboard" class="btn">Torna alla Dashboard</a> <a href="/finanze_dashboard?username={{ username or '' }}" class="btn" style="background:#17a2b8;">📊 Dashboard Finanziaria</a><div class="saldo">Saldo attuale: {{ "%.2f"|format(saldo) }} €</div><form method="get" style="margin-bottom:20px;display:flex;flex-wrap:wrap;gap:10px;align-items:center;"><input type="hidden" name="username" value="{{ username or '' }}"><input type="date" name="data_da" value="{{ data_da or '' }}" placeholder="Da"><input type="date" name="data_a" value="{{ data_a or '' }}" placeholder="A"><select name="tipo"><option value="">Tutti</option><option value="entrata" {{ 'selected' if tipo_f=='entrata' else '' }}>Entrata</option><option value="uscita" {{ 'selected' if tipo_f=='uscita' else '' }}>Uscita</option></select><input type="text" name="descr" placeholder="Descrizione" value="{{ descr_f or '' }}"><input type="number" step="0.01" name="imp_min" placeholder="Importo min" value="{{ imp_min or '' }}"><input type="number" step="0.01" name="imp_max" placeholder="Importo max" value="{{ imp_max or '' }}"><button type="submit" class="btn">Filtra</button><a href="/finanze?username={{ username or '' }}" class="btn" style="background:#aaa;">Azzera</a></form><form method="POST" enctype="multipart/form-data"><div class="form-row"><input type="date" name="data" required><input type="text" name="descrizione" placeholder="Descrizione" required><input type="number" step="0.01" name="importo" placeholder="Importo" required><select name="tipo" required><option value="entrata">Entrata</option><option value="uscita">Uscita</option></select><input type="text" name="note" placeholder="Note opzionali"><input type="file" name="allegato" accept=".jpg,.jpeg,.pdf"></div><button type="submit" class="btn">Aggiungi Movimento</button></form><table><tr><th>Data</th><th>Descrizione</th><th>Tipo</th><th>Importo</th><th>Note</th><th>Allegato</th><th>Elimina</th></tr>{% for m in movimenti_data %}<tr><td>{{ m.data }}</td><td>{{ m.descrizione }}</td><td>{{ m.tipo }}</td><td>{{ "%.2f"|format(m.importo) }} €</td><td>{{ m.note }}</td><td>{% if m.allegato_path %}<a href="/download_allegato/{{ m.id }}" target="_blank">Scarica</a>{% endif %}</td><td><a href="?delete={{ m.id }}&username={{ username or '' }}" onclick="return confirm('Sicuro di eliminare?')">🗑️</a></td></tr>{% endfor %}</table></div></body></html>
    ''', flash_messages=flash_messages, username=username, saldo=saldo, movimenti_data=movimenti_data, data_da=data_da, data_a=data_a, tipo_f=tipo_f, descr_f=descr_f, imp_min=imp_min, imp_max=imp_max)

# Download allegato
@app.route('/download_allegato/<int:mov_id>')
def download_allegato(mov_id):
    movimento = MovimentoFinanziario.query.get(mov_id)
    if movimento and movimento.allegato_path and os.path.exists(movimento.allegato_path):
        return send_file(movimento.allegato_path, as_attachment=True)
    flash('Allegato non trovato.', 'error')
    return redirect(url_for('finanze'))

@app.route('/finanze_dashboard')
def finanze_dashboard():
    import json
    # Usa username dalla querystring o dalla sessione
    username = request.args.get('username') or session.get('username')
    print(f'[DEBUG] Dashboard username: {username}')
    user = User.query.filter_by(username=username).first() if username else None
    is_admin = username == 'admin'
    print(f'[DEBUG] is_admin: {is_admin}')
    if is_admin:
        movimenti = MovimentoFinanziario.query.order_by(MovimentoFinanziario.data.asc()).all()
    else:
        steward = Steward.query.filter_by(email=username).first() if user else None
        movimenti = MovimentoFinanziario.query.filter_by(steward_id=steward.id).order_by(MovimentoFinanziario.data.asc()).all() if steward else []
    print(f'[DEBUG] Movimenti trovati: {len(movimenti)}')
    from collections import defaultdict
    saldo = 0
    saldo_per_data = []
    entrate_per_mese = defaultdict(float)
    uscite_per_mese = defaultdict(float)
    tipo_count = defaultdict(int)
    mesi_set = set()
    for m in movimenti:
        print(f'[DEBUG] Movimento: id={m.id}, data={m.data}, importo={m.importo}, tipo={m.tipo}')
        if m.tipo == 'entrata':
            saldo += m.importo
            entrate_per_mese[m.data.strftime('%Y-%m')] += m.importo
        else:
            saldo -= m.importo
            uscite_per_mese[m.data.strftime('%Y-%m')] += m.importo
        saldo_per_data.append({'x': m.data.strftime('%Y-%m-%d'), 'y': saldo})
        tipo_count[m.tipo] += 1
        mesi_set.add(m.data.strftime('%Y-%m'))
    mesi = sorted(list(mesi_set))
    entrate = [entrate_per_mese[m] for m in mesi]
    uscite = [uscite_per_mese[m] for m in mesi]
    print(f'[DEBUG] saldo_per_data: {saldo_per_data}')
    print(f'[DEBUG] mesi: {mesi}')
    print(f'[DEBUG] entrate: {entrate}')
    print(f'[DEBUG] uscite: {uscite}')
    print(f'[DEBUG] tipo_labels: {list(tipo_count.keys())}')
    print(f'[DEBUG] tipo_data: {list(tipo_count.values())}')
    # Converti i dizionari in liste per Jinja2
    tipo_labels = list(tipo_count.keys())
    tipo_data = list(tipo_count.values())
    return render_template_string("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Dashboard Finanziaria</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <script src="https://cdn.jsdelivr.net/npm/chart.js@4.3.3/dist/chart.umd.min.js"></script>
        <script src="https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns@3.0.0/dist/chartjs-adapter-date-fns.bundle.min.js"></script>
        <style>
            body { font-family: Arial,sans-serif; margin:0; background:#f4f4f9; }
            .header { background:#667eea; color:white; padding:15px 30px; text-align:center; font-size:1.5em; }
            .container { padding:30px; max-width:1000px; margin:auto; }
            .btn { background:#667eea; color:white; padding:10px 20px; border:none; border-radius:5px; text-decoration:none; cursor:pointer; margin-bottom:20px; display:inline-block; }
        </style>
    </head>
    <body>
        <div class="header">Dashboard Finanziaria</div>
        <div class="container">
            <a href="/finanze?username={{ username or '' }}" class="btn">Torna a Finanze</a>
            <h2>Andamento Saldo</h2>
            <canvas id="saldoChart"></canvas>
            <h2>Entrate/Uscite Mensili</h2>
            <canvas id="euChart"></canvas>
            <h2>Distribuzione Movimenti</h2>
            <canvas id="tipoChart"></canvas>
        </div>
        <script>
            const saldoData = {{ saldo_per_data|tojson }};
            const euLabels = {{ mesi|tojson }};
            const entrate = {{ entrate|tojson }};
            const uscite = {{ uscite|tojson }};
            const tipoLabels = {{ tipo_labels|tojson }};
            const tipoData = {{ tipo_data|tojson }};
            new Chart(document.getElementById('saldoChart'), {
                type:'line',
                data:{ datasets:[{ label:'Saldo', data:saldoData, borderColor:'#667eea', backgroundColor:'rgba(102,126,234,0.2)', fill:true }] },
                options:{ scales:{ x:{ type:'time', time:{ unit:'day' }, title:{ display:true, text:'Data' } }, y:{ title:{ display:true, text:'Saldo (€)' } } } }
            });
            new Chart(document.getElementById('euChart'), {
                type:'bar',
                data:{ labels:euLabels, datasets:[{ label:'Entrate', data:entrate, backgroundColor:'#4caf50' }, { label:'Uscite', data:uscite, backgroundColor:'#f44336' }] },
                options:{ scales:{ y:{ beginAtZero:true } } }
            });
            new Chart(document.getElementById('tipoChart'), {
                type:'doughnut',
                data:{ labels:tipoLabels, datasets:[{ data:tipoData, backgroundColor:['#4caf50','#f44336'] }] }
            });
        </script>
    </body>
    </html>
    """, saldo_per_data=saldo_per_data, mesi=mesi, entrate=entrate, uscite=uscite, tipo_labels=tipo_labels, tipo_data=tipo_data, username=username)

# --- Download file PDF steward (se non già presente) ---
@app.route('/uploads/<filename>')
def download_file(filename):
    import os
    uploads_dir = os.path.join(os.getcwd(), 'uploads')
    return send_from_directory(uploads_dir, filename, as_attachment=True)

@app.route('/event/<int:evento_id>/stewards', methods=['GET', 'POST'])
def event_stewards(evento_id):
    evento = Evento.query.get_or_404(evento_id)
    
    # --- METEO ---
    meteo_info = None
    if evento.luogo and evento.data_inizio:
        try:
            # Geocoding: ottieni lat/lon dal luogo (usando Nominatim OpenStreetMap)
            geo_url = f"https://nominatim.openstreetmap.org/search?format=json&q={evento.luogo}"
            geo_resp = requests.get(geo_url, headers={"User-Agent": "StewardApp/1.0"}, timeout=5)
            geo_data = geo_resp.json()
            if geo_data:
                lat = geo_data[0]['lat']
                lon = geo_data[0]['lon']
                # Previsioni meteo per la data dell'evento
                data_str = evento.data_inizio.strftime('%Y-%m-%d')
                meteo_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,weathercode&timezone=Europe/Rome&start_date={data_str}&end_date={data_str}"
                meteo_resp = requests.get(meteo_url, timeout=5)
                meteo_data = meteo_resp.json()
                if 'daily' in meteo_data and meteo_data['daily']['time']:
                    idx = 0  # solo un giorno richiesto
                    tmax = meteo_data['daily']['temperature_2m_max'][idx]
                    tmin = meteo_data['daily']['temperature_2m_min'][idx]
                    rain = meteo_data['daily']['precipitation_sum'][idx]
                    code = meteo_data['daily']['weathercode'][idx]
                    # Decodifica weathercode (semplificato)
                    code_map = {
                        0: ("Soleggiato", "☀️"),
                        1: ("Prevalentemente sereno", "🌤️"),
                        2: ("Parzialmente nuvoloso", "⛅"),
                        3: ("Coperto", "☁️"),
                        45: ("Nebbia", "🌫️"),
                        48: ("Nebbia gelata", "🌫️❄️"),
                        51: ("Pioviggine leggera", "🌦️"),
                        53: ("Pioviggine", "🌦️"),
                        55: ("Pioviggine intensa", "🌧️"),
                        61: ("Pioggia leggera", "🌦️"),
                        63: ("Pioggia", "🌧️"),
                        65: ("Pioggia intensa", "🌧️"),
                        71: ("Neve leggera", "🌨️"),
                        73: ("Neve", "🌨️"),
                        75: ("Neve intensa", "❄️"),
                        80: ("Rovesci leggeri", "🌦️"),
                        81: ("Rovesci", "🌧️"),
                        82: ("Rovesci forti", "⛈️"),
                    }
                    desc, icon = code_map.get(code, ("", "❓"))
                    meteo_info = {
                        'desc': desc,
                        'icon': icon,
                        'tmin': tmin,
                        'tmax': tmax,
                        'rain': rain
                    }
        except Exception as e:
            meteo_info = {'desc': 'Errore nel recupero meteo', 'icon': '❓', 'tmin': '', 'tmax': '', 'rain': ''}
    
    if request.method == 'POST':
        steward_id = request.form.get('steward_id')
        ruolo = request.form.get('ruolo')
        numero_casacca = request.form.get('numero_casacca')
        
        if not steward_id or not ruolo or not numero_casacca:
            flash('⚠️ Seleziona uno steward, un ruolo e inserisci il numero di casacca! (Obbligatorio)', 'warning')
            return redirect(url_for('event_stewards', evento_id=evento_id))
        # Controlla se lo steward è già assegnato
        existing = PartecipazioneEvento.query.filter_by(evento_id=evento_id, steward_id=steward_id).first()
        if existing:
            flash('⚠️ Questo steward è già assegnato a questo evento!', 'warning')
            return redirect(url_for('event_stewards', evento_id=evento_id))
        # Controlla se il numero di casacca è già assegnato
        existing_casacca = PartecipazioneEvento.query.filter_by(evento_id=evento_id, numero_casacca=numero_casacca).first()
        if existing_casacca:
            flash(f'⚠️ Il numero di casacca {numero_casacca} è già assegnato!', 'warning')
            return redirect(url_for('event_stewards', evento_id=evento_id))
        nuova_partecipazione = PartecipazioneEvento(
            evento_id=evento_id,
            steward_id=steward_id,
            ruolo=ruolo,
            numero_casacca=int(numero_casacca),
            note=request.form.get('note')
        )
        db.session.add(nuova_partecipazione)
        db.session.commit()
        flash('✅ Steward assegnato con successo!', 'success')
        return redirect(url_for('event_stewards', evento_id=evento_id))
    
    # Rimozione partecipazione
    remove_id = request.args.get('remove')
    if remove_id and remove_id.isdigit():
        partecipazione = PartecipazioneEvento.query.get(int(remove_id))
        if partecipazione and partecipazione.evento_id == evento_id:
            db.session.delete(partecipazione)
            db.session.commit()
            flash('🗑️ Partecipazione rimossa.', 'success')
            return redirect(url_for('event_stewards', evento_id=evento_id))
    
    # Aggiornamento stato partecipazione
    update_id = request.args.get('update')
    new_status = request.args.get('status')
    if update_id and update_id.isdigit() and new_status:
        partecipazione = PartecipazioneEvento.query.get(int(update_id))
        if partecipazione and partecipazione.evento_id == evento_id:
            partecipazione.stato = new_status
            db.session.commit()
            flash('✅ Stato aggiornato.', 'success')
            return redirect(url_for('event_stewards', evento_id=evento_id))
    
    # Lista steward disponibili (non ancora assegnati)
    steward_assegnati = [p.steward_id for p in evento.partecipazioni]
    
    # Debug: verifica quanti steward ci sono nel database
    total_stewards = Steward.query.count()
    print(f"DEBUG: Totale steward nel database: {total_stewards}")
    print(f"DEBUG: Steward assegnati a questo evento: {len(steward_assegnati)}")
    
    steward_disponibili = Steward.query.filter(~Steward.id.in_(steward_assegnati)).order_by(Steward.nome, Steward.cognome).all()
    print(f"DEBUG: Steward disponibili: {len(steward_disponibili)}")
    
    # Se non ci sono steward nel database, mostra un messaggio
    if total_stewards == 0:
        flash('⚠️ Non ci sono steward nel database. Aggiungi prima alcuni steward dalla sezione "Gestione Steward".', 'warning')
    
    # Lista partecipazioni
    partecipazioni = PartecipazioneEvento.query.filter_by(evento_id=evento_id).join(Steward).order_by(PartecipazioneEvento.numero_casacca, Steward.nome, Steward.cognome).all()
    
    # Prepara i messaggi flash
    flash_messages = []
    for c, m in get_flashed_messages(with_categories=True):
        icon = "✅" if c == "success" else "❌" if c == "error" else "⚠️"
        flash_messages.append({'category': c, 'message': m, 'icon': icon})
    
    return render_template_string('''
    <!DOCTYPE html><html><head><title>Gestione Steward Evento</title><meta name="viewport" content="width=device-width, initial-scale=1.0"><style>body{font-family:Arial,sans-serif;margin:0;background:#f4f4f9}.header{background:#667eea;color:white;padding:15px 30px;text-align:center;font-size:1.5em;position:relative}.container{padding:30px;max-width:1400px;margin:auto}.btn{background:#667eea;color:white;padding:8px 15px;border:none;border-radius:5px;text-decoration:none;cursor:pointer;margin:2px}.btn:hover{background:#5a6fd8}.btn-danger{background:#dc3545}.btn-success{background:#28a745}.btn-warning{background:#ffc107;color:#212529}.btn-info{background:#17a2b8}.flash-message{padding:10px;margin-bottom:10px;border-radius:6px;text-align:center;display:flex;align-items:center;gap:10px;font-weight:bold}.flash-success{background-color:#d4edda;color:#155724;border:1px solid #c3e6cb}.flash-error{background-color:#f8d7da;color:#721c24;border:1px solid #f5c6cb}.flash-warning{background-color:#fff3cd;color:#856404;border:1px solid #ffeeba}.form-row{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:20px}.form-row input,.form-row select,.form-row textarea{padding:8px;border-radius:5px;border:1px solid #ccc}.form-row textarea{resize:vertical;min-height:60px}.header-buttons{position:absolute;top:15px;right:30px}.header-buttons .btn{background:rgba(255,255,255,0.2);border:1px solid rgba(255,255,255,0.3)}.stato-badge{padding:4px 8px;border-radius:12px;color:white;font-size:0.8em;font-weight:bold}.event-info{background:#e9ecef;padding:15px;border-radius:8px;margin-bottom:20px}.event-info h3{margin-top:0}.two-columns{display:grid;grid-template-columns:1fr 1fr;gap:20px}@media (max-width:768px){.two-columns{grid-template-columns:1fr}}.export-buttons{margin:20px 0;text-align:center}.casacca-number{background:#007bff;color:white;padding:2px 6px;border-radius:10px;font-size:0.8em;font-weight:bold;margin-right:5px}.info-box{background:#e3f2fd;border-left:4px solid #2196f3;padding:10px;margin:10px 0;border-radius:5px}</style></head><body><div class="header">Gestione Steward - {{ evento.nome }}<div class="header-buttons"><a href="/events" class="btn">📋 Eventi</a><a href="/dashboard" class="btn">🏠 Dashboard</a></div></div><div class="container">{% if meteo_info %}<div class="info-box" style="background:#fffbe6;border-left:4px solid #ffc107;"><b>🌦️ Meteo previsto per {{ evento.data_inizio.strftime('%d/%m/%Y') }} a {{ evento.luogo }}:</b><br><span style="font-size:2em;">{{ meteo_info.icon }}</span> <b>{{ meteo_info.desc }}</b> | <b>Min:</b> {{ meteo_info.tmin }}°C | <b>Max:</b> {{ meteo_info.tmax }}°C | <b>Pioggia:</b> {{ meteo_info.rain }} mm</div>{% endif %}
    {% if total_stewards == 0 %}<div class="info-box"><strong>ℹ️ Informazione:</strong> Non ci sono steward nel database. <a href="/stewards" style="color:#2196f3;text-decoration:underline;">Aggiungi prima alcuni steward</a> per poterli assegnare agli eventi.</div>{% else %}<div class="info-box"><strong>ℹ️ Informazione:</strong> {{ steward_disponibili|length }} steward disponibili su {{ total_stewards }} totali nel database.</div>{% endif %}<div class="event-info"><h3>📅 Informazioni Evento</h3><p><strong>Data:</strong> {{ evento.data_inizio.strftime('%d/%m/%Y %H:%M') }} - {{ evento.data_fine.strftime('%d/%m/%Y %H:%M') }}</p><p><strong>Luogo:</strong> {{ evento.luogo or 'Non specificato' }}</p><p><strong>Tipo:</strong> {{ evento.tipo_evento or 'Non specificato' }}</p><p><strong>Stato:</strong> <span class="stato-badge" style="background-color:{{ {'pianificato': '#17a2b8', 'in_corso': '#28a745', 'completato': '#6c757d', 'cancellato': '#dc3545'}[evento.stato] }};">{{ evento.stato|title }}</span></p></div><div class="export-buttons">
        <a href="/event/{{ evento.id }}/export_excel" class="btn btn-success">📊 Esporta Excel</a>
        <a href="/event/{{ evento.id }}/presenze" class="btn btn-warning">📝 Presenze</a>
        <a href="/event/{{ evento.id }}/whatsapp_sondaggio" class="btn btn-warning">📱 Messaggio Sondaggio</a>
        <a href="/event/{{ evento.id }}/whatsapp_presenze" class="btn btn-info">👥 Messaggio Presenze</a>
+       <a href="/event/{{ evento.id }}/aggiungi_nota_spese" class="btn btn-info" style="background:#ffc107;color:#333;">➕ Aggiungi Nota Spese</a>
    </div><div class="two-columns"><div><h3>➕ Assegna Nuovo Steward</h3>{% if steward_disponibili %}<form method="POST"><div class="form-row"><select name="steward_id" required style="flex:2;"><option value="">Seleziona Steward</option>{% for steward in steward_disponibili %}<option value="{{ steward.id }}">{{ steward.nome }} {{ steward.cognome }} ({{ steward.email }})</option>{% endfor %}</select><select name="ruolo" required style="flex:1;"><option value="">Ruolo</option><option value="Capo Steward">Capo Steward</option><option value="Steward">Steward</option><option value="Supporto">Supporto</option><option value="Supervisore">Supervisore</option></select><input type="number" name="numero_casacca" placeholder="N° Casacca" min="1" style="flex:1;" required></div><div class="form-row"><textarea name="note" placeholder="Note (opzionale)"></textarea></div><button type="submit" class="btn">➕ Assegna Steward</button></form>{% else %}<p style="color:#666;font-style:italic;">Tutti gli steward sono già assegnati a questo evento o non ci sono steward disponibili.</p>{% endif %}</div><div><h3>👥 Steward Assegnati ({{ partecipazioni|length }})</h3>{% if partecipazioni %}<table style="width:100%;border-collapse:collapse;margin-top:10px;"><tr style="background:#667eea;color:white;"><th style="padding:8px;text-align:left;">Casacca</th><th style="padding:8px;text-align:left;">Steward</th><th style="padding:8px;text-align:left;">Ruolo</th><th style="padding:8px;text-align:left;">Stato</th><th style="padding:8px;text-align:left;">Azioni</th></tr>{% for p in partecipazioni %}<tr style="border-bottom:1px solid #ddd;"><td style="padding:8px;">{% if p.numero_casacca %}<span class="casacca-number">{{ p.numero_casacca }}</span>{% else %}-{% endif %}</td><td style="padding:8px;">{{ p.steward.nome }} {{ p.steward.cognome }}<br><small>{{ p.steward.email }}</small></td><td style="padding:8px;">{{ p.ruolo }}</td><td style="padding:8px;"><span class="stato-badge" style="background-color:{{ {'assegnato': '#17a2b8', 'confermato': '#28a745', 'rifiutato': '#dc3545', 'completato': '#6c757d'}[p.stato] }};">{{ p.stato|title }}</span></td><td style="padding:8px;"><div style="display:flex;gap:5px;flex-wrap:wrap;">{% if p.stato == 'assegnato' %}<a href="/event/{{ evento.id }}/stewards?update={{ p.id }}&status=confermato" class="btn btn-success" style="font-size:0.7em;padding:4px 6px;">✅</a><a href="/event/{{ evento.id }}/stewards?update={{ p.id }}&status=rifiutato" class="btn btn-danger" style="font-size:0.7em;padding:4px 6px;">❌</a>{% elif p.stato == 'confermato' %}<a href="/event/{{ evento.id }}/stewards?update={{ p.id }}&status=completato" class="btn btn-info" style="font-size:0.7em;padding:4px 6px;">✅</a>{% endif %}<a href="/event/{{ evento.id }}/stewards?remove={{ p.id }}" class="btn btn-danger" style="font-size:0.7em;padding:4px 6px;" onclick="return confirm('Rimuovere questo steward?')">🗑️</a></div></td></tr>{% endfor %}</table>{% else %}<p style="color:#666;font-style:italic;">Nessuno steward assegnato.</p>{% endif %}</div></div></div></body></html>
    ''', messages_html=''.join(f'<div class="flash-message flash-{m["category"]}"><span style="font-size:1.2em;">{m["icon"]}</span><span>{m["message"]}</span></div>' for m in flash_messages), evento=evento, steward_disponibili=steward_disponibili, partecipazioni=partecipazioni, total_stewards=total_stewards, meteo_info=meteo_info)

@app.route('/event/<int:evento_id>/export_excel')
def export_event_excel(evento_id):
    evento = Evento.query.get_or_404(evento_id)
    partecipazioni = PartecipazioneEvento.query.filter_by(evento_id=evento_id).join(Steward).order_by(PartecipazioneEvento.numero_casacca, Steward.nome, Steward.cognome).all()
    
    # Crea un DataFrame con i dati
    data = []
    for p in partecipazioni:
        data.append({
            'Numero Casacca': p.numero_casacca or '',
            'Nome': p.steward.nome,
            'Cognome': p.steward.cognome,
            'Email': p.steward.email,
            'Telefono': p.steward.phone or '',
            'Ruolo': p.ruolo,
            'Stato': p.stato,
            'Note': p.note or ''
        })
    
    df = pd.DataFrame(data)
    
    # Crea il file Excel
    uploads_dir = os.path.join(os.getcwd(), 'uploads')
    filename = f"evento_{evento_id}_{evento.nome.replace(' ', '_')}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    filepath = os.path.join(uploads_dir, filename)
    
    with pd.ExcelWriter(filepath, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Partecipanti', index=False)
        
        # Aggiungi informazioni evento
        info_data = {
            'Informazione': ['Nome Evento', 'Data Inizio', 'Data Fine', 'Luogo', 'Tipo Evento', 'Stato', 'Numero Partecipanti'],
            'Valore': [
                evento.nome,
                evento.data_inizio.strftime('%d/%m/%Y %H:%M'),
                evento.data_fine.strftime('%d/%m/%Y %H:%M'),
                evento.luogo or 'Non specificato',
                evento.tipo_evento or 'Non specificato',
                evento.stato,
                len(partecipazioni)
            ]
        }
        info_df = pd.DataFrame(info_data)
        info_df.to_excel(writer, sheet_name='Info Evento', index=False)
    
    return send_from_directory(uploads_dir, filename, as_attachment=True)

@app.route('/event/<int:evento_id>/whatsapp_sondaggio')
def whatsapp_sondaggio(evento_id):
    evento = Evento.query.get_or_404(evento_id)
    partecipazioni = PartecipazioneEvento.query.filter_by(evento_id=evento_id).join(Steward).all()
    
    # Prepara il messaggio per il sondaggio
    data_evento = evento.data_inizio.strftime('%d/%m/%Y')
    ora_evento = evento.data_inizio.strftime('%H:%M')
    
    messaggio = f"""📋 *SONDAGGIO PARTECIPAZIONE EVENTO*

🏆 *{evento.nome}*
📅 Data: {data_evento}
⏰ Ora: {ora_evento} 
📍 Luogo: {evento.luogo or 'Da confermare'}

👥 *Steward Assegnati ({len(partecipazioni)}):*
"""
    
    for p in partecipazioni:
        casacca = f" #{p.numero_casacca}" if p.numero_casacca else ""
        messaggio += f"• {p.steward.nome} {p.steward.cognome}{casacca} - {p.ruolo}\n"
    
    messaggio += f"""

❓ *Confermi la tua partecipazione?*

Rispondi con:
✅ = Confermo
❌ = Non posso partecipare
⏰ = Conferma più tardi

📱 *Link per rispondere:* [Clicca qui per rispondere al sondaggio]

---
*Messaggio generato automaticamente da StewardApp*"""
    
    # Codifica il messaggio per WhatsApp
    import urllib.parse
    encoded_message = urllib.parse.quote(messaggio)
    whatsapp_url = f"https://wa.me/?text={encoded_message}"
    
    return render_template_string('''
    <!DOCTYPE html><html><head><title>Messaggio Sondaggio WhatsApp</title><meta name="viewport" content="width=device-width, initial-scale=1.0"><style>body{font-family:Arial,sans-serif;margin:0;background:#f4f4f9}.header{background:#25d366;color:white;padding:15px 30px;text-align:center;font-size:1.5em}.container{padding:30px;max-width:800px;margin:auto}.btn{background:#25d366;color:white;padding:15px 30px;border:none;border-radius:8px;text-decoration:none;cursor:pointer;font-size:1.1em;margin:10px;display:inline-block}.btn:hover{background:#128c7e}.message-preview{background:white;padding:20px;border-radius:8px;margin:20px 0;border-left:4px solid #25d366;white-space:pre-wrap;font-family:monospace;max-height:400px;overflow-y:auto}.copy-btn{background:#667eea;color:white;padding:8px 15px;border:none;border-radius:5px;cursor:pointer;margin-left:10px}.copy-btn:hover{background:#5a6fd8}.back-btn{background:#6c757d;color:white;padding:10px 20px;border:none;border-radius:5px;text-decoration:none;display:inline-block;margin-top:20px}</style></head><body><div class="header">📱 Messaggio Sondaggio WhatsApp</div><div class="container"><h2>Messaggio preparato per {{ evento.nome }}</h2><div class="message-preview">{{ messaggio }}</div><div style="text-align:center;margin:30px 0;"><a href="{{ whatsapp_url }}" target="_blank" class="btn">📱 Apri WhatsApp</a><button onclick="copyToClipboard('{{ messaggio }}')" class="copy-btn">📋 Copia Messaggio</button></div><a href="/event/{{ evento.id }}/stewards" class="back-btn">← Torna alla Gestione Steward</a></div><script>function copyToClipboard(text) {navigator.clipboard.writeText(text).then(function() {alert('Messaggio copiato negli appunti!');}).catch(function(err) {console.error('Errore nella copia: ', err);});}</script></body></html>
    ''', evento=evento, messaggio=messaggio, whatsapp_url=whatsapp_url)

@app.route('/event/<int:evento_id>/whatsapp_presenze')
def whatsapp_presenze(evento_id):
    evento = Evento.query.get_or_404(evento_id)
    partecipazioni = PartecipazioneEvento.query.filter_by(evento_id=evento_id).join(Steward).order_by(PartecipazioneEvento.numero_casacca, Steward.nome, Steward.cognome).all()
    data_evento = evento.data_inizio.strftime('%d/%m/%Y')
    ora_evento = evento.data_inizio.strftime('%H:%M')
    messaggio = f"""📋 *LISTA PRESENZE EVENTO*

🏆 *{evento.nome}*
📅 Data: {data_evento}
⏰ Ora: {ora_evento}
📍 Luogo: {evento.luogo or 'Da confermare'}

👥 *Steward Assegnati ({len(partecipazioni)}):*
"""
    for p in partecipazioni:
        casacca = f"Casacca #{p.numero_casacca}" if p.numero_casacca else "❗NO_CASACCA"
        stato_emoji = {"assegnato": "⏳", "confermato": "✅", "rifiutato": "❌", "completato": "🏁"}
        messaggio += f"{stato_emoji.get(p.stato, '❓')} {casacca} - {p.steward.nome} {p.steward.cognome} ({p.ruolo})\n"
    messaggio += f"""

📊 *Riepilogo:*
• Totale assegnati: {len(partecipazioni)}
• Confermati: {len([p for p in partecipazioni if p.stato == 'confermato'])}
• Rifiutati: {len([p for p in partecipazioni if p.stato == 'rifiutato'])}
• Completati: {len([p for p in partecipazioni if p.stato == 'completato'])}

📱 *Link per aggiornamenti:* [Clicca qui per aggiornare presenze]

---
*Messaggio generato automaticamente da StewardApp*"""
    import urllib.parse
    encoded_message = urllib.parse.quote(messaggio)
    whatsapp_url = f"https://wa.me/?text={encoded_message}"
    return render_template_string('''
    <!DOCTYPE html><html><head><title>Messaggio Presenze WhatsApp</title><meta name="viewport" content="width=device-width, initial-scale=1.0"><style>body{font-family:Arial,sans-serif;margin:0;background:#f4f4f9}.header{background:#25d366;color:white;padding:15px 30px;text-align:center;font-size:1.5em}.container{padding:30px;max-width:800px;margin:auto}.btn{background:#25d366;color:white;padding:15px 30px;border:none;border-radius:8px;text-decoration:none;cursor:pointer;font-size:1.1em;margin:10px;display:inline-block}.btn:hover{background:#128c7e}.message-preview{background:white;padding:20px;border-radius:8px;margin:20px 0;border-left:4px solid #25d366;white-space:pre-wrap;font-family:monospace;max-height:400px;overflow-y:auto}.copy-btn{background:#667eea;color:white;padding:8px 15px;border:none;border-radius:5px;cursor:pointer;margin-left:10px}.copy-btn:hover{background:#5a6fd8}.back-btn{background:#6c757d;color:white;padding:10px 20px;border:none;border-radius:5px;text-decoration:none;display:inline-block;margin-top:20px}</style></head><body><div class="header">👥 Messaggio Presenze WhatsApp</div><div class="container"><h2>Lista Presenze per {{ evento.nome }}</h2><div class="message-preview">{{ messaggio }}</div><div style="text-align:center;margin:30px 0;"><a href="{{ whatsapp_url }}" target="_blank" class="btn">📱 Apri WhatsApp</a><button onclick="copyToClipboard('{{ messaggio }}')" class="copy-btn">📋 Copia Messaggio</button></div><a href="/event/{{ evento.id }}/stewards" class="back-btn">← Torna alla Gestione Steward</a></div><script>function copyToClipboard(text) {navigator.clipboard.writeText(text).then(function() {alert('Messaggio copiato negli appunti!');}).catch(function(err) {console.error('Errore nella copia: ', err);});}</script></body></html>
    ''', evento=evento, messaggio=messaggio, whatsapp_url=whatsapp_url)

@app.route('/event/<int:evento_id>/presenze', methods=['GET', 'POST'])
def presenze_evento(evento_id):
    evento = Evento.query.get_or_404(evento_id)
    # --- METEO ---
    meteo_info = None
    if evento.luogo and evento.data_inizio:
        try:
            geo_url = f"https://nominatim.openstreetmap.org/search?format=json&q={evento.luogo}"
            geo_resp = requests.get(geo_url, headers={"User-Agent": "StewardApp/1.0"}, timeout=5)
            geo_data = geo_resp.json()
            if geo_data:
                lat = geo_data[0]['lat']
                lon = geo_data[0]['lon']
                data_str = evento.data_inizio.strftime('%Y-%m-%d')
                meteo_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,weathercode&timezone=Europe/Rome&start_date={data_str}&end_date={data_str}"
                meteo_resp = requests.get(meteo_url, timeout=5)
                meteo_data = meteo_resp.json()
                if 'daily' in meteo_data and meteo_data['daily']['time']:
                    idx = 0
                    tmax = meteo_data['daily']['temperature_2m_max'][idx]
                    tmin = meteo_data['daily']['temperature_2m_min'][idx]
                    rain = meteo_data['daily']['precipitation_sum'][idx]
                    code = meteo_data['daily']['weathercode'][idx]
                    code_map = {
                        0: ("Soleggiato", "☀️"),
                        1: ("Prevalentemente sereno", "🌤️"),
                        2: ("Parzialmente nuvoloso", "⛅"),
                        3: ("Coperto", "☁️"),
                        45: ("Nebbia", "🌫️"),
                        48: ("Nebbia gelata", "🌫️❄️"),
                        51: ("Pioviggine leggera", "🌦️"),
                        53: ("Pioviggine", "🌦️"),
                        55: ("Pioviggine intensa", "🌧️"),
                        61: ("Pioggia leggera", "🌦️"),
                        63: ("Pioggia", "🌧️"),
                        65: ("Pioggia intensa", "🌧️"),
                        71: ("Neve leggera", "🌨️"),
                        73: ("Neve", "🌨️"),
                        75: ("Neve intensa", "❄️"),
                        80: ("Rovesci leggeri", "🌦️"),
                        81: ("Rovesci", "🌧️"),
                        82: ("Rovesci forti", "⛈️"),
                    }
                    desc, icon = code_map.get(code, ("", "❓"))
                    meteo_info = {
                        'desc': desc,
                        'icon': icon,
                        'tmin': tmin,
                        'tmax': tmax,
                        'rain': rain
                    }
        except Exception as e:
            meteo_info = {'desc': 'Errore nel recupero meteo', 'icon': '❓', 'tmin': '', 'tmax': '', 'rain': ''}
    filtro = request.args.get('filtro', 'tutti')
    partecipazioni_query = PartecipazioneEvento.query.filter_by(evento_id=evento_id).join(Steward).order_by(PartecipazioneEvento.numero_casacca, Steward.nome, Steward.cognome)
    partecipazioni = partecipazioni_query.all()
    if request.method == 'POST':
        # Aggiorna presenze e note
        for p in partecipazioni:
            key = f'presente_{p.id}'
            note_key = f'note_{p.id}'
            p.presente = (key in request.form)
            p.note = request.form.get(note_key, '')
        db.session.commit()
        flash('Presenze aggiornate!', 'success')
        return redirect(url_for('presenze_evento', evento_id=evento_id, filtro=filtro))
    # Filtri
    if filtro == 'presenti':
        partecipazioni = [p for p in partecipazioni if p.presente]
    elif filtro == 'assenti':
        partecipazioni = [p for p in partecipazioni if not p.presente]
    # Riepilogo
    totale = len(partecipazioni_query.all())
    presenti = len([p for p in partecipazioni_query.all() if p.presente])
    assenti = totale - presenti
    # Prepara dati per la tabella
    table_rows = ''
    for p in partecipazioni:
        checked = 'checked' if p.presente else ''
        row_style = 'background-color:#ffd6d6;' if not p.presente else ''
        table_rows += f'''<tr style="{row_style}">
            <td>{p.numero_casacca or ''}</td>
            <td>{p.steward.nome} {p.steward.cognome}</td>
            <td>{p.ruolo}</td>
            <td style='text-align:center;'><input type="checkbox" name="presente_{p.id}" {checked}></td>
            <td><input type="text" name="note_{p.id}" value="{p.note or ''}" style="width:100%"></td>
        </tr>'''
    # Messaggio WhatsApp
    msg = f"Presenze evento: {evento.nome} ({evento.data_inizio.strftime('%d/%m/%Y')})\n"
    for p in partecipazioni_query.all():
        stato = '✅' if p.presente else '❌'
        casacca = f"#{p.numero_casacca}" if p.numero_casacca else "❗NO_CASACCA"
        msg += f"{stato} {casacca} {p.steward.nome} {p.steward.cognome} - {p.ruolo}\n"
    import urllib.parse
    whatsapp_url = f"https://wa.me/?text={urllib.parse.quote(msg)}"
    # HTML
    return render_template_string('''
    <!DOCTYPE html><html><head><title>Presenze Evento</title><meta name="viewport" content="width=device-width, initial-scale=1.0"><style>body{font-family:Arial,sans-serif;margin:0;background:#f4f4f9}.header{background:#667eea;color:white;padding:15px 30px;text-align:center;font-size:1.5em}.container{padding:30px;max-width:900px;margin:auto}table{width:100%;border-collapse:collapse;margin-top:20px}th,td{padding:10px;border:1px solid #ddd;text-align:left}th{background:#667eea;color:white}tr:nth-child(even){background:#f9f9f9}.btn{background:#667eea;color:white;padding:10px 20px;border:none;border-radius:5px;text-decoration:none;cursor:pointer;margin:5px}.btn-whatsapp{background:#25d366}.btn-save{background:#28a745}.btn-back{background:#6c757d}.btn-pay{background:#ffc107;color:#212529}.flash-message{padding:10px;margin-bottom:10px;border-radius:6px;text-align:center;font-weight:bold}.flash-success{background-color:#d4edda;color:#155724}.flash-error{background-color:#f8d7da;color:#721c24}</style></head><body><div class="header">Presenze - {{ evento.nome }}</div><div class="container">{% for c, m in get_flashed_messages(with_categories=True) %}<div class="flash-message flash-{{c}}">{{m}}</div>{% endfor %}<form method="POST"><table><tr><th>Casacca</th><th>Nome</th><th>Ruolo</th><th>Presente</th></tr>{{ table_rows|safe }}</table><button type="submit" class="btn btn-save">💾 Salva Presenze</button></form><div style="margin:20px 0;"><button class="btn btn-whatsapp" onclick="copyMsg()">📋 Copia lista WhatsApp</button> <a href="{{ whatsapp_url }}" target="_blank" class="btn btn-whatsapp">📱 Invia su WhatsApp</a> <a href="/event/{{ evento.id }}/genera_pagamenti" class="btn btn-pay">💶 Genera Pagamenti</a> <a href="/event/{{ evento.id }}/stewards" class="btn btn-back">← Torna a Gestione Steward</a></div><textarea id="msg" style="width:100%;height:100px;">{{ msg }}</textarea><script>function copyMsg(){var t=document.getElementById('msg');t.select();document.execCommand('copy');alert('Messaggio copiato!');}</script></div></body></html>
    ''', evento=evento, partecipazioni=partecipazioni, table_rows=table_rows, msg=msg, whatsapp_url=whatsapp_url, meteo_info=meteo_info)

@app.route('/event/<int:evento_id>/presenze_export_excel')
def presenze_evento_export_excel(evento_id):
    import pandas as pd
    import tempfile
    import os
    evento = Evento.query.get_or_404(evento_id)
    partecipazioni = PartecipazioneEvento.query.filter_by(evento_id=evento_id).join(Steward).order_by(PartecipazioneEvento.numero_casacca, Steward.nome, Steward.cognome).all()
    data = []
    for p in partecipazioni:
        data.append({
            'Nome': p.steward.nome,
            'Cognome': p.steward.cognome,
            'Ruolo': p.ruolo,
            'Numero Casacca': p.numero_casacca or '',
            'Presenza': 'Presente' if p.presente else 'Assente'
        })
    df = pd.DataFrame(data)
    with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp:
        df.to_excel(tmp.name, sheet_name='Presenze', index=False, engine='openpyxl')
        tmp_path = tmp.name
    from flask import send_file
    response = send_file(
        tmp_path,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'presenze_evento_{evento_id}_{evento.nome.replace(" ", "_")}.xlsx'
    )
    # Pulizia file temporaneo dopo invio
    @response.call_on_close
    def cleanup():
        try:
            os.remove(tmp_path)
        except Exception:
            pass
    return response

# 7. ESECUZIONE
# ... altre funzioni e route ...

@app.route('/notifiche_eventi')
def notifiche_eventi():
    print('DEBUG: Funzione notifiche_eventi eseguita!')
    now = datetime.datetime.now()
    domani = now + datetime.timedelta(days=1)
    prossime_ore = now + datetime.timedelta(hours=6)
    # Eventi imminenti e urgenti
    eventi_imminenti = Evento.query.filter(Evento.data_inizio >= now, Evento.data_inizio <= domani, Evento.stato == 'pianificato').all()
    eventi_urgenti = Evento.query.filter(Evento.data_inizio >= now, Evento.data_inizio <= prossime_ore, Evento.stato == 'pianificato').all()
    # Eventi senza steward
    eventi_senza_steward = []
    for evento in Evento.query.filter_by(stato='pianificato').all():
        if not evento.partecipazioni:
            eventi_senza_steward.append(evento)
    # Eventi con pagamenti in sospeso
    eventi_pagamenti_sospesi = []
    for evento in Evento.query.filter_by(stato='pianificato').all():
        pagamenti_sospesi = MovimentoFinanziario.query.filter_by(evento_id=evento.id, tipo='uscita', pagato=False).count()
        if pagamenti_sospesi > 0:
            eventi_pagamenti_sospesi.append((evento, pagamenti_sospesi))
    # Riepilogo presenze per ogni evento
    def presenze_riassunto(evento):
        tot = len(evento.partecipazioni)
        presenti = len([p for p in evento.partecipazioni if p.presente])
        assenti = tot - presenti
        return tot, presenti, assenti
    return render_template_string('''
    <!DOCTYPE html><html><head><title>Notifiche Eventi</title><meta name="viewport" content="width=device-width, initial-scale=1.0"><style>body{font-family:Arial,sans-serif;margin:0;background:#f4f4f9}.header{background:#dc3545;color:white;padding:15px 30px;text-align:center;font-size:1.5em;position:relative}.container{padding:30px;max-width:1200px;margin:auto}.btn{background:#667eea;color:white;padding:8px 15px;border:none;border-radius:5px;text-decoration:none;cursor:pointer;margin:2px}.btn:hover{background:#5a6fd8}.btn-danger{background:#dc3545}.btn-success{background:#28a745}.btn-warning{background:#ffc107;color:#212529}.btn-info{background:#17a2b8}.header-buttons{position:absolute;top:15px;right:30px}.header-buttons .btn{background:rgba(255,255,255,0.2);border:1px solid rgba(255,255,255,0.3)}.notification-section{margin-bottom:30px;background:white;border-radius:8px;padding:20px;box-shadow:0 2px 4px rgba(0,0,0,0.1)}.notification-section h3{margin-top:0;color:#333}.event-card{background:#f8f9fa;border-left:4px solid #dc3545;padding:15px;margin:10px 0;border-radius:5px}.event-card.urgent{border-left-color:#dc3545;background:#fff5f5}.event-card.warning{border-left-color:#ffc107;background:#fffbf0}.event-card.info{border-left-color:#17a2b8;background:#f0f8ff}.event-card.payment{border-left-color:#28a745;background:#f6fff6}.event-card h4{margin:0 0 10px 0;color:#333}.event-card p{margin:5px 0;color:#666}.event-actions{display:flex;gap:5px;margin-top:10px;flex-wrap:wrap}.event-actions .btn{font-size:0.8em;padding:4px 8px}.no-events{color:#666;font-style:italic;text-align:center;padding:20px}</style></head><body><div class="header">🚨 Notifiche Eventi<div class="header-buttons"><a href="/dashboard" class="btn">🏠 Dashboard</a><a href="/events" class="btn">📋 Eventi</a></div></div><div class="container">
    <div class="notification-section"><h3>💶 Eventi con Pagamenti in Sospeso - {{ eventi_pagamenti_sospesi|length }}</h3>{% if eventi_pagamenti_sospesi %}{% for evento, n_pag in eventi_pagamenti_sospesi %}<div class="event-card payment"><h4>🏆 {{ evento.nome }}</h4><p><strong>⏰ Inizio:</strong> {{ evento.data_inizio.strftime('%d/%m/%Y %H:%M') }}</p><p><strong>📍 Luogo:</strong> {{ evento.luogo or 'Non specificato' }}</p><p style="color:#dc3545;font-weight:bold;">⚠️ Pagamenti in sospeso: {{ n_pag }}</p><div class="event-actions"><a href="/event/{{ evento.id }}/pagamenti" class="btn btn-success">💶 Gestisci Pagamenti</a></div></div>{% endfor %}{% else %}<p class="no-events">Nessun evento con pagamenti in sospeso.</p>{% endif %}</div>
    <div class="notification-section"><h3>🚨 Eventi Urgenti (entro 6 ore) - {{ eventi_urgenti|length }}</h3>{% if eventi_urgenti %}{% for evento in eventi_urgenti %}<div class="event-card urgent"><h4>🏆 {{ evento.nome }}</h4><p><strong>⏰ Inizio:</strong> {{ evento.data_inizio.strftime('%d/%m/%Y %H:%M') }}</p><p><strong>📍 Luogo:</strong> {{ evento.luogo or 'Non specificato' }}</p><p><strong>👥 Steward:</strong> {{ evento.partecipazioni|length }} assegnati</p><div class="event-actions"><a href="/event/{{ evento.id }}/stewards" class="btn btn-success">👥 Gestisci Steward</a><a href="/event/{{ evento.id }}/whatsapp_sondaggio" class="btn btn-warning">📱 Sondaggio</a><a href="/event/{{ evento.id }}/whatsapp_presenze" class="btn btn-info">👥 Presenze</a></div></div>{% endfor %}{% else %}<p class="no-events">Nessun evento urgente.</p>{% endif %}</div>
    <div class="notification-section"><h3>⚠️ Eventi Imminenti (entro 24 ore) - {{ eventi_imminenti|length }}</h3>{% if eventi_imminenti %}{% for evento in eventi_imminenti %}{% if evento not in eventi_urgenti %}<div class="event-card warning"><h4>🏆 {{ evento.nome }}</h4><p><strong>⏰ Inizio:</strong> {{ evento.data_inizio.strftime('%d/%m/%Y %H:%M') }}</p><p><strong>📍 Luogo:</strong> {{ evento.luogo or 'Non specificato' }}</p><p><strong>👥 Steward:</strong> {{ evento.partecipazioni|length }} assegnati</p><div class="event-actions"><a href="/event/{{ evento.id }}/stewards" class="btn btn-success">👥 Gestisci Steward</a><a href="/event/{{ evento.id }}/whatsapp_sondaggio" class="btn btn-warning">📱 Sondaggio</a><a href="/event/{{ evento.id }}/whatsapp_presenze" class="btn btn-info">👥 Presenze</a></div></div>{% endif %}{% endfor %}{% else %}<p class="no-events">Nessun evento imminente.</p>{% endif %}</div>
    <div class="notification-section"><h3>ℹ️ Eventi Senza Steward - {{ eventi_senza_steward|length }}</h3>{% if eventi_senza_steward %}{% for evento in eventi_senza_steward %}<div class="event-card info"><h4>🏆 {{ evento.nome }}</h4><p><strong>⏰ Inizio:</strong> {{ evento.data_inizio.strftime('%d/%m/%Y %H:%M') }}</p><p><strong>📍 Luogo:</strong> {{ evento.luogo or 'Non specificato' }}</p><p><strong>⚠️ Nessuno steward assegnato!</strong></p><div class="event-actions"><a href="/event/{{ evento.id }}/stewards" class="btn btn-success">👥 Assegna Steward</a><a href="/event/{{ evento.id }}/edit" class="btn btn-info">✏️ Modifica</a></div></div>{% endfor %}{% else %}<p class="no-events">Tutti gli eventi hanno steward assegnati.</p>{% endif %}</div></div></body></html>
    ''', eventi_urgenti=eventi_urgenti, eventi_imminenti=eventi_imminenti, eventi_senza_steward=eventi_senza_steward, eventi_pagamenti_sospesi=eventi_pagamenti_sospesi)


  
# 7. ESECUZIONE
@app.route('/event/<int:evento_id>/genera_pagamenti', methods=['GET', 'POST'])
def genera_pagamenti(evento_id):
    evento = Evento.query.get_or_404(evento_id)
    partecipazioni = PartecipazioneEvento.query.filter_by(evento_id=evento_id).join(Steward).order_by(PartecipazioneEvento.numero_casacca, Steward.nome, Steward.cognome).all()
    presenti = [p for p in partecipazioni if p.presente]
    if request.method == 'POST':
        pagati = 0
        for p in presenti:
            # checkbox: pagare_{p.id}, importo: importo_{p.id}, anticipo: anticipo_{p.id}
            if request.form.get(f'pagare_{p.id}'):
                try:
                    importo = float(request.form.get(f'importo_{p.id}', '0').replace(',', '.'))
                except:
                    importo = 0
                metodo_pagamento = request.form.get(f'metodo_{p.id}', 'Contanti')
                pagamento_anticipato = request.form.get(f'anticipo_{p.id}') == 'on'
                descrizione = f"Pagamento evento {evento.nome} - {p.steward.nome} {p.steward.cognome} (casacca #{p.numero_casacca})"
                mov = MovimentoFinanziario(
                    steward_id=p.steward.id,
                    data=datetime.date.today(),
                    descrizione=descrizione,
                    importo=importo,
                    tipo='uscita',
                    note=p.note or '',
                    metodo_pagamento=metodo_pagamento,
                    pagamento_anticipato=pagamento_anticipato,
                    evento_id=evento.id
                )
                db.session.add(mov)
                pagati += 1
        db.session.commit()
        flash(f'Pagamenti generati per {pagati} steward selezionati.', 'success')
        return redirect(url_for('finanze'))
    return render_template_string('''
    <!DOCTYPE html><html><head><title>Genera Pagamenti</title><meta name="viewport" content="width=device-width, initial-scale=1.0"><style>body{font-family:Arial,sans-serif;margin:0;background:#f4f4f9}.container{padding:30px;max-width:900px;margin:auto;background:white;border-radius:10px;box-shadow:0 5px 15px rgba(0,0,0,0.1)}h2{color:#667eea;text-align:center}.btn{background:#28a745;color:white;padding:10px 20px;border:none;border-radius:5px;text-decoration:none;cursor:pointer;margin:10px 0;display:inline-block}.btn-cancel{background:#aaa}.pay-table{width:100%;border-collapse:collapse;margin-top:20px}th,td{padding:10px;border:1px solid #ddd;text-align:left}th{background:#667eea;color:white}tr:nth-child(even){background:#f9f9f9}.anticipo-row{background:#fff3cd !important;}.form-row{display:flex;gap:10px;margin-bottom:15px;align-items:center}label{font-weight:bold}</style></head><body><div class="container"><h2>Genera Pagamenti per Evento: {{ evento.nome }}</h2><form method="POST"><table class="pay-table"><tr><th>Pagare</th><th>Casacca</th><th>Nome</th><th>Ruolo</th><th>Importo</th><th>Metodo</th><th>Anticipo</th></tr>{% for p in presenti %}<tr class="{% if request.method=='POST' and request.form.get('anticipo_' ~ p.id) %}anticipo-row{% endif %}"><td style="text-align:center;"><input type="checkbox" name="pagare_{{p.id}}"></td><td>{{p.numero_casacca or ''}}</td><td>{{p.steward.nome}} {{p.steward.cognome}}</td><td>{{p.ruolo}}</td><td><input type="number" name="importo_{{p.id}}" step="0.01" min="0" required style="width:90px;"></td><td><select name="metodo_{{p.id}}"><option value="Contanti">Contanti</option><option value="Bonifico">Bonifico</option><option value="Anticipato">Anticipato</option><option value="Altro">Altro</option></select></td><td style="text-align:center;"><input type="checkbox" name="anticipo_{{p.id}}"></td></tr>{% endfor %}</table><div class="form-row"><button type="submit" class="btn">💶 Genera Pagamenti</button><a href="/event/{{ evento.id }}/presenze" class="btn btn-cancel">Annulla</a></div></form><div style="margin-top:30px;"><h3>Legenda:</h3><ul><li><b>Anticipo</b>: evidenziato in giallo</li><li>Seleziona solo chi deve essere pagato</li><li>Importo e metodo possono essere diversi per ciascuno</li></ul></div></div></body></html>
    ''', evento=evento, presenti=presenti)

@app.route('/event/<int:evento_id>/pagamenti', methods=['GET', 'POST'])
def pagamenti_evento(evento_id):
    evento = Evento.query.get_or_404(evento_id)
    # Pagamenti in sospeso per questo evento
    pagamenti = MovimentoFinanziario.query.filter_by(evento_id=evento_id, tipo='uscita', pagato=False).join(Steward).order_by(MovimentoFinanziario.data.desc()).all()
    if request.method == 'POST':
        # Segna come pagato
        pagato_ids = request.form.getlist('pagato_id')
        for pid in pagato_ids:
            mov = MovimentoFinanziario.query.get(int(pid))
            if mov and mov.evento_id == evento_id:
                mov.pagato = True
        db.session.commit()
        flash(f"{len(pagato_ids)} pagamento/i segnato/i come pagato!", 'success')
        return redirect(url_for('pagamenti_evento', evento_id=evento_id))
    return render_template_string('''
    <!DOCTYPE html><html><head><title>Pagamenti in Sospeso</title><meta name="viewport" content="width=device-width, initial-scale=1.0"><style>body{font-family:Arial,sans-serif;margin:0;background:#f4f4f9}.container{padding:30px;max-width:900px;margin:auto;background:white;border-radius:10px;box-shadow:0 5px 15px rgba(0,0,0,0.1)}h2{color:#dc3545;text-align:center}.btn{background:#28a745;color:white;padding:10px 20px;border:none;border-radius:5px;text-decoration:none;cursor:pointer;margin:10px 0;display:inline-block}.btn-back{background:#aaa}.pay-table{width:100%;border-collapse:collapse;margin-top:20px}th,td{padding:10px;border:1px solid #ddd;text-align:left}th{background:#dc3545;color:white}tr:nth-child(even){background:#f9f9f9}.anticipo-row{background:#fff3cd !important;}</style></head><body><div class="container"><h2>Pagamenti in Sospeso per Evento: {{ evento.nome }}</h2>{% if pagamenti %}<form method="POST"><table class="pay-table"><tr><th>Pagato</th><th>Data</th><th>Steward</th><th>Importo</th><th>Metodo</th><th>Anticipo</th><th>Descrizione</th></tr>{% for m in pagamenti %}<tr class="{% if m.pagamento_anticipato %}anticipo-row{% endif %}"><td style="text-align:center;"><input type="checkbox" name="pagato_id" value="{{m.id}}"></td><td>{{m.data.strftime('%d-%m-%Y')}}</td><td>{{m.steward.nome}} {{m.steward.cognome}}</td><td>{{"%.2f"|format(m.importo)}} €</td><td>{{m.metodo_pagamento}}</td><td style="text-align:center;">{% if m.pagamento_anticipato %}SI{% else %}-{% endif %}</td><td>{{m.descrizione}}</td></tr>{% endfor %}</table><button type="submit" class="btn">Segna come Pagato</button></form>{% else %}<p style="color:#28a745;font-weight:bold;">Nessun pagamento in sospeso per questo evento!</p>{% endif %}<a href="/event/{{ evento.id }}/stewards" class="btn btn-back">← Torna a Gestione Steward</a></div></body></html>
    ''', evento=evento, pagamenti=pagamenti)

@app.route('/report_finanze')
def report_finanze():
    # Report generale
    movimenti = MovimentoFinanziario.query.order_by(MovimentoFinanziario.data.asc()).all()
    totale_entrate = sum(m.importo for m in movimenti if m.tipo == 'entrata')
    totale_uscite = sum(m.importo for m in movimenti if m.tipo == 'uscita')
    saldo = totale_entrate - totale_uscite
    # Report per evento
    eventi = Evento.query.order_by(Evento.data_inizio.asc()).all()
    report_eventi = []
    for evento in eventi:
        movs = MovimentoFinanziario.query.filter_by(evento_id=evento.id).all()
        entrate = sum(m.importo for m in movs if m.tipo == 'entrata')
        uscite = sum(m.importo for m in movs if m.tipo == 'uscita')
        saldo_evento = entrate - uscite
        report_eventi.append({
            'evento': evento,
            'entrate': entrate,
            'uscite': uscite,
            'saldo': saldo_evento,
            'movimenti': movs
        })
    return render_template_string('''
    <!DOCTYPE html><html><head><title>Report Finanziario</title><meta name="viewport" content="width=device-width, initial-scale=1.0"><style>body{font-family:Arial,sans-serif;margin:0;background:#f4f4f9}.header{background:#667eea;color:white;padding:15px 30px;text-align:center;font-size:1.5em}.container{padding:30px;max-width:1200px;margin:auto;background:white;border-radius:10px;box-shadow:0 5px 15px rgba(0,0,0,0.1)}h2{color:#667eea}.summary{margin-bottom:30px}.event-report{margin-bottom:40px;border-bottom:1px solid #ddd;padding-bottom:20px}.event-title{color:#dc3545;font-size:1.2em;margin-bottom:5px}.saldo-pos{color:#28a745;font-weight:bold}.saldo-neg{color:#dc3545;font-weight:bold}.table{width:100%;border-collapse:collapse;margin-top:10px}th,td{padding:8px;border:1px solid #ddd;text-align:left}th{background:#667eea;color:white}tr:nth-child(even){background:#f9f9f9}.btn{background:#667eea;color:white;padding:8px 15px;border:none;border-radius:5px;text-decoration:none;cursor:pointer;margin:2px}.btn-back{background:#aaa}</style></head><body><div class="header">Report Finanziario</div><div class="container"><a href="/dashboard" class="btn btn-back">← Torna alla Dashboard</a><h2>Riepilogo Generale</h2><div class="summary"><b>Totale Entrate:</b> {{ "%.2f"|format(totale_entrate) }} €<br><b>Totale Uscite:</b> {{ "%.2f"|format(totale_uscite) }} €<br><b>Saldo:</b> <span class="{{ 'saldo-pos' if saldo >= 0 else 'saldo-neg' }}">{{ "%.2f"|format(saldo) }} €</span></div><h2>Report per Evento</h2>{% for r in report_eventi %}<div class="event-report"><div class="event-title">🏆 {{ r.evento.nome }} <span style="font-size:0.9em;color:#666;">({{ r.evento.data_inizio.strftime('%d/%m/%Y') }})</span></div><b>Entrate:</b> {{ "%.2f"|format(r.entrate) }} €<br><b>Uscite:</b> {{ "%.2f"|format(r.uscite) }} €<br><b>Saldo:</b> <span class="{{ 'saldo-pos' if r.saldo >= 0 else 'saldo-neg' }}">{{ "%.2f"|format(r.saldo) }} €</span><details style="margin-top:10px;"><summary>Dettaglio movimenti</summary><table class="table"><tr><th>Data</th><th>Tipo</th><th>Importo</th><th>Descrizione</th></tr>{% for m in r.movimenti %}<tr><td>{{ m.data.strftime('%d-%m-%Y') }}</td><td>{{ m.tipo.title() }}</td><td>{{ "%.2f"|format(m.importo) }} €</td><td>{{ m.descrizione }}</td></tr>{% endfor %}</table></details></div>{% endfor %}</div></body></html>
    ''', totale_entrate=totale_entrate, totale_uscite=totale_uscite, saldo=saldo, report_eventi=report_eventi)

@app.route('/calendario_eventi')
def calendario_eventi():
    eventi = Evento.query.order_by(Evento.data_inizio.asc()).all()
    # Preparo i dati per il calendario
    events_json = [
        {
            'id': e.id,
            'title': e.nome,
            'start': e.data_inizio.strftime('%Y-%m-%dT%H:%M'),
            'end': e.data_fine.strftime('%Y-%m-%dT%H:%M'),
            'url': f'/event/{e.id}/stewards',
            'color': '#28a745' if e.stato == 'completato' else '#17a2b8' if e.stato == 'pianificato' else '#dc3545' if e.stato == 'cancellato' else '#ffc107'
        }
        for e in eventi
    ]
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Calendario Eventi</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <link href="https://cdn.jsdelivr.net/npm/fullcalendar@6.1.8/index.global.min.css" rel="stylesheet">
        <script src="https://cdn.jsdelivr.net/npm/fullcalendar@6.1.8/index.global.min.js"></script>
        <style>
            body { font-family: Arial,sans-serif; margin:0; background:#f4f4f9; }
            .header { background:#667eea; color:white; padding:15px 30px; text-align:center; font-size:1.5em; }
            .container { padding:30px; max-width:1100px; margin:auto; background:white; border-radius:10px; box-shadow:0 5px 15px rgba(0,0,0,0.1); }
            .btn { background:#667eea; color:white; padding:10px 20px; border:none; border-radius:5px; text-decoration:none; cursor:pointer; margin-bottom:20px; display:inline-block; }
        </style>
    </head>
    <body>
        <div class="header">Calendario Eventi</div>
        <div class="container">
            <a href="/dashboard" class="btn">← Torna alla Dashboard</a>
            <div id="calendar"></div>
        </div>
        <script>
            document.addEventListener('DOMContentLoaded', function() {
                var calendarEl = document.getElementById('calendar');
                var calendar = new FullCalendar.Calendar(calendarEl, {
                    initialView: 'dayGridMonth',
                    locale: 'it',
                    height: 700,
                    events: {{ events_json|tojson }},
                    eventClick: function(info) {
                        if(info.event.url) {
                            window.open(info.event.url, '_blank');
                            info.jsEvent.preventDefault();
                        }
                    }
                });
                calendar.render();
            });
        </script>
    </body>
    </html>
    ''', events_json=events_json)

@app.route('/event/<int:evento_id>/duplica', methods=['GET', 'POST'])
def duplica_evento(evento_id):
    evento = Evento.query.get_or_404(evento_id)
    if request.method == 'POST':
        data_inizio_str = request.form.get('data_inizio')
        data_fine_str = request.form.get('data_fine')
        if not data_inizio_str or not data_fine_str:
            flash('⚠️ Data inizio e data fine sono obbligatorie!', 'warning')
            return redirect(url_for('duplica_evento', evento_id=evento_id))
        try:
            data_inizio = datetime.datetime.strptime(data_inizio_str, '%Y-%m-%dT%H:%M')
            data_fine = datetime.datetime.strptime(data_fine_str, '%Y-%m-%dT%H:%M')
        except Exception:
            flash('⚠️ Formato data non valido!', 'warning')
            return redirect(url_for('duplica_evento', evento_id=evento_id))
        budget_str = request.form.get('budget')
        try:
            budget = float(budget_str) if budget_str else None
        except Exception:
            budget = None
        nuovo_evento = Evento(
            nome=request.form.get('nome'),
            descrizione=request.form.get('descrizione'),
            data_inizio=data_inizio,
            data_fine=data_fine,
            luogo=request.form.get('luogo'),
            tipo_evento=request.form.get('tipo_evento'),
            stato=request.form.get('stato', 'pianificato'),
            budget=budget,
            note=request.form.get('note')
        )
        db.session.add(nuovo_evento)
        db.session.commit()
        # Duplica anche le partecipazioni
        partecipazioni = PartecipazioneEvento.query.filter_by(evento_id=evento.id).all()
        for p in partecipazioni:
            nuova_partecipazione = PartecipazioneEvento(
                evento_id=nuovo_evento.id,
                steward_id=p.steward_id,
                ruolo=p.ruolo,
                numero_casacca=p.numero_casacca,
                stato='assegnato',
                note=p.note
            )
            db.session.add(nuova_partecipazione)
        db.session.commit()
        flash(f'✅ Evento duplicato con successo: {nuovo_evento.nome} (con partecipazioni)', 'success')
        return redirect(url_for('events'))
    # Precompila il form con i dati dell'evento originale
    return render_template_string('''
    <!DOCTYPE html><html><head><title>Duplica Evento</title><meta name="viewport" content="width=device-width, initial-scale=1.0"><style>body{font-family:Arial,sans-serif;margin:0;background:#f4f4f9}.container{max-width:600px;margin:30px auto;background:white;padding:30px;border-radius:10px;box-shadow:0 5px 15px rgba(0,0,0,0.1)}h2{color:#667eea;text-align:center}.form-row{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:20px}.form-row input,.form-row select,.form-row textarea{padding:8px;border-radius:5px;border:1px solid #ccc;width:100%}.btn{background:#28a745;color:white;padding:10px 20px;border:none;border-radius:5px;text-decoration:none;cursor:pointer;margin-top:10px}.btn-cancel{background:#aaa}</style></head><body><div class="container"><h2>Duplica Evento</h2><form method="POST"><div class="form-row"><input type="text" name="nome" placeholder="Nome Evento *" required value="{{ evento.nome }} (Copia)"><input type="text" name="luogo" placeholder="Luogo" value="{{ evento.luogo or '' }}"><select name="tipo_evento"><option value="">Tipo Evento</option><option value="Sportivo" {% if evento.tipo_evento=='Sportivo' %}selected{% endif %}>Sportivo</option><option value="Culturale" {% if evento.tipo_evento=='Culturale' %}selected{% endif %}>Culturale</option><option value="Musicale" {% if evento.tipo_evento=='Musicale' %}selected{% endif %}>Musicale</option><option value="Religioso" {% if evento.tipo_evento=='Religioso' %}selected{% endif %}>Religioso</option><option value="Altro" {% if evento.tipo_evento=='Altro' %}selected{% endif %}>Altro</option></select><select name="stato"><option value="pianificato" {% if evento.stato=='pianificato' %}selected{% endif %}>Pianificato</option><option value="in_corso" {% if evento.stato=='in_corso' %}selected{% endif %}>In Corso</option><option value="completato" {% if evento.stato=='completato' %}selected{% endif %}>Completato</option><option value="cancellato" {% if evento.stato=='cancellato' %}selected{% endif %}>Cancellato</option></select></div><div class="form-row"><input type="datetime-local" name="data_inizio" required value="{{ evento.data_inizio.strftime('%Y-%m-%dT%H:%M') }}"><input type="datetime-local" name="data_fine" required value="{{ evento.data_fine.strftime('%Y-%m-%dT%H:%M') }}"><input type="number" name="budget" placeholder="Budget (€)" step="0.01" value="{{ evento.budget or '' }}"></div><div class="form-row"><textarea name="descrizione" placeholder="Descrizione Evento">{{ evento.descrizione or '' }}</textarea><textarea name="note" placeholder="Note">{{ evento.note or '' }}</textarea></div><button type="submit" class="btn">➕ Duplica Evento</button><a href="/events" class="btn btn-cancel">Annulla</a></form></div></body></html>
    ''', evento=evento)

@app.route('/stampa_eventi')
def stampa_eventi():
    from datetime import datetime
    filtro = request.args.get('filtro', 'annuale')
    eventi = Evento.query.order_by(Evento.data_inizio.asc()).all()
    titolo = "Elenco Eventi"
    if filtro == 'annuale':
        anno = datetime.now().year
        eventi = [e for e in eventi if e.data_inizio.year == anno]
        titolo = f"Elenco Eventi {anno}"
    elif filtro == 'mensile':
        mese = request.args.get('mese')
        if mese:
            anno, mese_num = map(int, mese.split('-'))
            eventi = [e for e in eventi if e.data_inizio.year == anno and e.data_inizio.month == mese_num]
            titolo = f"Elenco Eventi {mese_num:02d}/{anno}"
    elif filtro == 'singolo':
        evento_id = request.args.get('evento_id')
        if evento_id:
            eventi = [e for e in eventi if str(e.id) == str(evento_id)]
            if eventi:
                titolo = f"Evento: {eventi[0].nome} ({eventi[0].data_inizio.strftime('%d/%m/%Y')})"
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>{{ titolo }}</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body { font-family: Arial,sans-serif; margin:0; background:#fff; }
            .container { max-width: 1100px; margin: 30px auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 5px 15px rgba(0,0,0,0.1); }
            h2 { color: #667eea; text-align: center; }
            table { width: 100%; border-collapse: collapse; margin-top: 20px; }
            th, td { padding: 10px; border: 1px solid #ddd; text-align: left; }
            th { background: #667eea; color: white; }
            tr:nth-child(even) { background: #f9f9f9; }
            .btn-print { background: #28a745; color: white; padding: 10px 20px; border: none; border-radius: 5px; text-decoration: none; cursor: pointer; margin-bottom: 20px; display: inline-block; font-size: 1.1em; }
            @media print {
                .btn-print, .btn-back { display: none !important; }
                .container { box-shadow: none; border-radius: 0; }
            }
            .btn-back { background: #aaa; color: white; padding: 10px 20px; border: none; border-radius: 5px; text-decoration: none; cursor: pointer; margin-bottom: 20px; display: inline-block; font-size: 1.1em; }
        </style>
    </head>
    <body>
        <div class="container">
            <a href="/dashboard" class="btn-back">← Torna alla Dashboard</a>
            <button class="btn-print" onclick="window.print()">🖨️ Stampa</button>
            <h2>{{ titolo }}</h2>
            <table>
                <tr>
                    <th>Nome</th>
                    <th>Data Inizio</th>
                    <th>Data Fine</th>
                    <th>Luogo</th>
                    <th>Tipo</th>
                    <th>Stato</th>
                    <th>Budget</th>
                    <th>Note</th>
                </tr>
                {% for e in eventi %}
                <tr>
                    <td>{{ e.nome }}</td>
                    <td>{{ e.data_inizio.strftime('%d/%m/%Y %H:%M') }}</td>
                    <td>{{ e.data_fine.strftime('%d/%m/%Y %H:%M') }}</td>
                    <td>{{ e.luogo or '' }}</td>
                    <td>{{ e.tipo_evento or '' }}</td>
                    <td>{{ e.stato|title }}</td>
                    <td>{{ '%.2f'|format(e.budget) if e.budget else '' }} €</td>
                    <td>{{ e.note or '' }}</td>
                </tr>
                {% endfor %}
            </table>
        </div>
    </body>
    </html>
    ''', eventi=eventi, titolo=titolo)

@app.route('/stampa_presenze')
def stampa_presenze():
    eventi = Evento.query.order_by(Evento.data_inizio.asc()).all()
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Stampa Presenze Eventi</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body { font-family: Arial,sans-serif; margin:0; background:#fff; }
            .container { max-width: 1100px; margin: 30px auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 5px 15px rgba(0,0,0,0.1); }
            h2 { color: #667eea; text-align: center; }
            h3 { color: #dc3545; margin-top: 30px; }
            table { width: 100%; border-collapse: collapse; margin-top: 10px; margin-bottom: 30px; }
            th, td { padding: 8px; border: 1px solid #ddd; text-align: left; }
            th { background: #667eea; color: white; }
            tr:nth-child(even) { background: #f9f9f9; }
            .btn-print { background: #28a745; color: white; padding: 10px 20px; border: none; border-radius: 5px; text-decoration: none; cursor: pointer; margin-bottom: 20px; display: inline-block; font-size: 1.1em; }
            @media print {
                .btn-print, .btn-back { display: none !important; }
                .container { box-shadow: none; border-radius: 0; }
            }
            .btn-back { background: #aaa; color: white; padding: 10px 20px; border: none; border-radius: 5px; text-decoration: none; cursor: pointer; margin-bottom: 20px; display: inline-block; font-size: 1.1em; }
        </style>
    </head>
    <body>
        <div class="container">
            <a href="/dashboard" class="btn-back">← Torna alla Dashboard</a>
            <button class="btn-print" onclick="window.print()">🖨️ Stampa</button>
            <h2>Presenze per Tutti gli Eventi</h2>
            {% for evento in eventi %}
                <h3>{{ evento.nome }} <span style="font-size:0.9em;color:#666;">({{ evento.data_inizio.strftime('%d/%m/%Y') }})</span></h3>
                <table>
                    <tr>
                        <th>Casacca</th>
                        <th>Nome</th>
                        <th>Cognome</th>
                        <th>Ruolo</th>
                        <th>Presente</th>
                        <th>Note</th>
                    </tr>
                    {% for p in evento.partecipazioni %}
                    <tr>
                        <td>{{ p.numero_casacca or '' }}</td>
                        <td>{{ p.steward.nome }}</td>
                        <td>{{ p.steward.cognome }}</td>
                        <td>{{ p.ruolo }}</td>
                        <td>{{ 'SI' if p.presente else 'NO' }}</td>
                        <td>{{ p.note or '' }}</td>
                    </tr>
                    {% endfor %}
                </table>
            {% endfor %}
        </div>
    </body>
    </html>
    ''', eventi=eventi)

@app.route('/event/<int:evento_id>/aggiungi_nota_spese', methods=['GET', 'POST'])
def aggiungi_nota_spese(evento_id):
    evento = Evento.query.get_or_404(evento_id)
    stewards = Steward.query.order_by(Steward.nome, Steward.cognome).all()
    if request.method == 'POST':
        steward_id = request.form.get('steward_id')
        tipo = request.form.get('tipo')
        importo = request.form.get('importo')
        descrizione = request.form.get('descrizione')
        allegato = request.files.get('allegato')
        if not steward_id or not importo or not tipo:
            flash('Tutti i campi obbligatori!', 'warning')
            return redirect(url_for('aggiungi_nota_spese', evento_id=evento_id))
        try:
            importo = float(importo)
        except:
            flash('Importo non valido!', 'warning')
            return redirect(url_for('aggiungi_nota_spese', evento_id=evento_id))
        upload_folder = os.path.join(os.getcwd(), 'uploads')
        os.makedirs(upload_folder, exist_ok=True)
        allegato_path = ''
        if allegato and allegato.filename:
            filename = f"nota_spese_{evento_id}_{steward_id}_{allegato.filename}"
            allegato_path = os.path.join(upload_folder, filename)
            allegato.save(allegato_path)
        nota = NotaSpese(
            steward_id=steward_id,
            evento_id=evento_id,
            data=datetime.date.today(),
            importo=importo,
            descrizione=f"{tipo}: {descrizione}",
            allegato_path=allegato_path,
            stato='in_attesa'
        )
        db.session.add(nota)
        db.session.commit()
        flash('Nota spese inserita! In attesa di approvazione.', 'success')
        return redirect(url_for('event_stewards', evento_id=evento_id))
    return render_template_string('''
    <!DOCTYPE html><html><head><title>Aggiungi Nota Spese</title><meta name="viewport" content="width=device-width, initial-scale=1.0"><style>body{font-family:Arial,sans-serif;margin:0;background:#f4f4f9}.container{max-width:600px;margin:30px auto;background:white;padding:30px;border-radius:10px;box-shadow:0 5px 15px rgba(0,0,0,0.1)}h2{color:#667eea;text-align:center}.form-row{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:20px}.form-row input,.form-row select,.form-row textarea{padding:8px;border-radius:5px;border:1px solid #ccc;width:100%}.btn{background:#28a745;color:white;padding:10px 20px;border:none;border-radius:5px;text-decoration:none;cursor:pointer;margin-top:10px}.btn-cancel{background:#aaa}</style></head><body><div class="container"><h2>Aggiungi Nota Spese per {{ evento.nome }}</h2><form method="POST" enctype="multipart/form-data"><div class="form-row"><label>Steward</label><select name="steward_id" required><option value="">Seleziona Steward</option>{% for s in stewards %}<option value="{{ s.id }}">{{ s.nome }} {{ s.cognome }}</option>{% endfor %}</select></div><div class="form-row"><label>Tipo Spesa</label><select name="tipo" required><option value="">Seleziona Tipo</option><option value="Noleggio Macchina">Noleggio Macchina</option><option value="Carburante">Carburante</option></select></div><div class="form-row"><label>Importo (€)</label><input type="number" name="importo" step="0.01" min="0" required></div><div class="form-row"><label>Descrizione</label><textarea name="descrizione" placeholder="Dettagli spesa" required></textarea></div><div class="form-row"><label>Allegato (opzionale, JPG/PDF)</label><input type="file" name="allegato" accept=".jpg,.jpeg,.pdf"></div><button type="submit" class="btn">Aggiungi Nota Spese</button><a href="/event/{{ evento.id }}/stewards" class="btn btn-cancel">Annulla</a></form></div></body></html>
    ''', evento=evento, stewards=stewards)

@app.route('/gestione_note_spese', methods=['GET', 'POST'])
def gestione_note_spese():
    if request.method == 'POST':
        action = request.form.get('action')
        nota_id = request.form.get('nota_id')
        nota = NotaSpese.query.get(nota_id)
        if nota and action in ['approva', 'rifiuta']:
            nota.stato = 'approvata' if action == 'approva' else 'rifiutata'
            db.session.commit()
            flash(f"Nota spese {'approvata' if action == 'approva' else 'rifiutata'}.", 'success')
        return redirect(url_for('gestione_note_spese'))
    note = NotaSpese.query.order_by(NotaSpese.data.desc()).all()
    return render_template_string('''
    <!DOCTYPE html><html><head><title>Gestione Note Spese</title><meta name="viewport" content="width=device-width, initial-scale=1.0"><style>body{font-family:Arial,sans-serif;margin:0;background:#f4f4f9}.container{max-width:1200px;margin:30px auto;background:white;padding:30px;border-radius:10px;box-shadow:0 5px 15px rgba(0,0,0,0.1)}h2{color:#667eea;text-align:center}.btn{background:#28a745;color:white;padding:8px 15px;border:none;border-radius:5px;text-decoration:none;cursor:pointer;margin:2px}.btn-danger{background:#dc3545}.btn-warning{background:#ffc107;color:#333}.btn-back{background:#aaa}.stato-badge{padding:4px 8px;border-radius:12px;color:white;font-size:0.9em;font-weight:bold}.stato-in_attesa{background:#ffc107;color:#333}.stato-approvata{background:#28a745}.stato-rifiutata{background:#dc3545}table{width:100%;border-collapse:collapse;margin-top:20px}th,td{padding:10px;border:1px solid #ddd;text-align:left}th{background:#667eea;color:white}tr:nth-child(even){background:#f9f9f9}</style></head><body><div class="container"><a href="/dashboard" class="btn btn-back">← Torna alla Dashboard</a><h2>Gestione Note Spese / Rimborsi</h2><table><tr><th>Data</th><th>Evento</th><th>Steward</th><th>Tipo</th><th>Importo</th><th>Descrizione</th><th>Allegato</th><th>Stato</th><th>Azioni</th></tr>{% for n in note %}<tr><td>{{ n.data.strftime('%d/%m/%Y') }}</td><td>{{ n.evento.nome }}</td><td>{{ n.steward.nome }} {{ n.steward.cognome }}</td><td>{% if 'Noleggio' in n.descrizione %}Noleggio Macchina{% elif 'Carburante' in n.descrizione %}Carburante{% else %}-{% endif %}</td><td>{{ '%.2f'|format(n.importo) }} €</td><td>{{ n.descrizione }}</td><td>{% if n.allegato_path %}<a href="/download_allegato_nota_spese/{{ n.id }}" target="_blank">Scarica</a>{% endif %}</td><td><span class="stato-badge stato-{{ n.stato }}">{{ n.stato.replace('_',' ').title() }}</span></td><td>{% if n.stato == 'in_attesa' %}<form method="POST" style="display:inline;"><input type="hidden" name="nota_id" value="{{ n.id }}"><button name="action" value="approva" class="btn">Approva</button><button name="action" value="rifiuta" class="btn btn-danger">Rifiuta</button></form>{% else %}-{% endif %}</td></tr>{% endfor %}</table></div></body></html>
    ''', note=note)

@app.route('/download_allegato_nota_spese/<int:nota_id>')
def download_allegato_nota_spese(nota_id):
    nota = NotaSpese.query.get_or_404(nota_id)
    if nota.allegato_path and os.path.exists(nota.allegato_path):
        return send_file(nota.allegato_path, as_attachment=True)
    flash('Allegato non trovato.', 'error')
    return redirect(url_for('gestione_note_spese'))

@app.route('/autocomplete_citta')
def autocomplete_citta():
    query = request.args.get('q', '')
    if not query:
        return jsonify([])
    try:
        url = f"https://nominatim.openstreetmap.org/search?format=json&q={query}&limit=5"
        resp = requests.get(url, headers={"User-Agent": "StewardApp/1.0"}, timeout=5)
        data = resp.json()
        results = [d['display_name'] for d in data]
        return jsonify(results)
    except Exception as e:
        return jsonify([])

@app.route('/events', methods=['GET', 'POST'])
def events():
    if request.method == 'POST':
        # Creazione nuovo evento
        data_inizio_str = request.form.get('data_inizio')
        data_fine_str = request.form.get('data_fine')
        if not data_inizio_str or not data_fine_str:
            flash('⚠️ Data inizio e fine obbligatorie!', 'warning')
            return redirect(url_for('events'))
        try:
            data_inizio = datetime.datetime.strptime(data_inizio_str, '%Y-%m-%dT%H:%M')
            data_fine = datetime.datetime.strptime(data_fine_str, '%Y-%m-%dT%H:%M')
        except Exception:
            flash('⚠️ Formato data non valido!', 'warning')
            return redirect(url_for('events'))
        if data_fine < data_inizio:
            flash('⚠️ La data di fine deve essere successiva o uguale alla data di inizio!', 'warning')
            return redirect(url_for('events'))
        budget = request.form.get('budget')
        try:
            budget = float(budget) if budget else None
        except Exception:
            budget = None
        nuovo_evento = Evento(
            nome=request.form.get('nome'),
            descrizione=request.form.get('descrizione'),
            data_inizio=data_inizio,
            data_fine=data_fine,
            luogo=request.form.get('luogo'),
            tipo_evento=request.form.get('tipo_evento'),
            stato=request.form.get('stato', 'pianificato'),
            budget=budget,
            note=request.form.get('note')
        )
        db.session.add(nuovo_evento)
        db.session.commit()
        flash(f'✅ Evento "{nuovo_evento.nome}" creato con successo!', 'success')
        return redirect(url_for('events'))
    # Filtri di ricerca
    search_query = request.args.get('search', '').strip().lower()
    eventi_query = Evento.query
    if search_query:
        eventi_query = eventi_query.filter(
            db.or_(
                Evento.nome.ilike(f'%{search_query}%'),
                Evento.descrizione.ilike(f'%{search_query}%'),
                Evento.luogo.ilike(f'%{search_query}%')
            )
        )
    eventi = eventi_query.order_by(Evento.data_inizio.asc()).all()
    # Prepara i dati per la tabella
    eventi_data = []
    for e in eventi:
        eventi_data.append({
            'id': e.id,
            'nome': e.nome,
            'data_inizio': e.data_inizio.strftime('%d/%m/%Y %H:%M'),
            'data_fine': e.data_fine.strftime('%d/%m/%Y %H:%M'),
            'luogo': e.luogo or '',
            'tipo_evento': e.tipo_evento or '',
            'stato': e.stato,
        })
    return render_template('events.html', eventi=eventi_data)

@app.route('/stewards/export_pdf')
def export_stewards_pdf():
    from io import BytesIO
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from reportlab.lib import colors
    from reportlab.platypus import Table, TableStyle
    from datetime import datetime, timedelta
    scadenza_limite = (datetime.now() + timedelta(days=30)).date()
    stewards_list = Steward.query.order_by(Steward.nome, Steward.cognome).all()
    data = [["Nome", "Cognome", "Email", "Documenti Mancanti", "Documenti in Scadenza"]]
    for s in stewards_list:
        missing_docs = []
        if not s.carta_identita_path:
            missing_docs.append("Carta d'Identità")
        if not s.codice_fiscale_path:
            missing_docs.append("Codice Fiscale")
        if not s.attestato_path:
            missing_docs.append("Attestato")
        if not s.autocertificazione_path:
            missing_docs.append("Autocertificazione")
        if not s.patente_path:
            missing_docs.append("Patente")
        is_expiring = s.document_expiry and s.document_expiry <= scadenza_limite
        data.append([
            s.nome,
            s.cognome,
            s.email or '',
            ', '.join(missing_docs) if missing_docs else '-',
            'SI' if is_expiring else '-'
        ])
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    c.setFont("Helvetica-Bold", 16)
    c.drawString(40, height - 40, "Stato Documenti Stewards")
    c.setFont("Helvetica", 10)
    table = Table(data, colWidths=[80, 80, 120, 120, 80])
    style = TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.lightblue),
        ('TEXTCOLOR', (0,0), (-1,0), colors.black),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 9),
        ('BOTTOMPADDING', (0,0), (-1,0), 8),
        ('BACKGROUND', (0,1), (-1,-1), colors.whitesmoke),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
    ])
    table.setStyle(style)
    table.wrapOn(c, width, height)
    table_height = 20 * len(data)
    table.drawOn(c, 40, height - 80 - table_height)
    c.showPage()
    c.save()
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name="stewards_documenti.pdf", mimetype='application/pdf')

@app.route('/stewards/upload', methods=['POST'])
def upload_steward_documents():
    from werkzeug.utils import secure_filename
    import os
    allowed_ext = {'.jpg', '.jpeg', '.pdf'}
    steward_id = request.form.get('steward_id')
    files = request.files.getlist('files')
    if not steward_id or not files:
        flash('Seleziona uno steward e almeno un file.', 'warning')
        return redirect(url_for('stewards'))
    if len(files) > 10:
        flash('Puoi caricare al massimo 10 file alla volta.', 'warning')
        return redirect(url_for('stewards'))
    steward = Steward.query.get(steward_id)
    if not steward:
        flash('Steward non trovato.', 'danger')
        return redirect(url_for('stewards'))
    upload_folder = os.path.join(os.getcwd(), 'uploads')
    os.makedirs(upload_folder, exist_ok=True)
    updated = False
    for file in files:
        if not file or not getattr(file, 'filename', None) or not isinstance(file.filename, str) or file.filename.strip() == '':
            continue
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in allowed_ext:
            flash(f"Tipo file non consentito: {file.filename}", 'warning')
            continue
        filename = secure_filename(f"{steward.id}_{file.filename}")
        file_path = os.path.join(upload_folder, filename)
        file.save(file_path)
        # Associa file al campo giusto se riconoscibile dal nome
        fname = file.filename.lower()
        if 'identita' in fname:
            steward.carta_identita_path = file_path
            updated = True
        elif 'fiscale' in fname:
            steward.codice_fiscale_path = file_path
            updated = True
        elif 'attestato' in fname:
            steward.attestato_path = file_path
            updated = True
        elif 'autocert' in fname:
            steward.autocertificazione_path = file_path
            updated = True
        elif 'patente' in fname:
            steward.patente_path = file_path
            updated = True
    if updated:
        db.session.commit()
        flash('Documenti caricati e associati correttamente!', 'success')
    else:
        flash('File caricati, ma nessun documento associato automaticamente. Rinomina i file per includere il tipo (identita, fiscale, attestato, autocert, patente).', 'info')
    return redirect(url_for('stewards'))

@app.route('/import_stewards', methods=['POST'])
def import_stewards():
    import pandas as pd
    from flask import request, redirect, url_for, flash
    if 'file' not in request.files:
        flash('⚠️ Nessun file selezionato!', 'warning')
        return redirect(url_for('stewards'))
    file = request.files['file']
    if file.filename == '':
        flash('⚠️ Nessun file selezionato!', 'warning')
        return redirect(url_for('stewards'))
    if file.filename and not file.filename.lower().endswith(('.xlsx', '.xls')):
        flash('⚠️ Il file deve essere in formato Excel (.xlsx o .xls)!', 'warning')
        return redirect(url_for('stewards'))
    try:
        df = pd.read_excel(file)
        col_map = {
            'nome': 'nome',
            'cognome': 'cognome',
            'email': 'email',
            'telefono': 'phone',
            'indirizzo': 'address',
            'codice fiscale': 'tax_code',
            'iban': 'iban',
            'tipo documento': 'document_type',
            'numero documento': 'document_number',
            'scadenza': 'document_expiry',
            'esperienza': 'experience'
        }
        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
        required_columns = ['nome', 'cognome']
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            flash(f'⚠️ Colonne mancanti nel file Excel: {", ".join(missing_columns)}', 'warning')
            return redirect(url_for('stewards'))
        success_count = 0
        error_count = 0
        for index, row in df.iterrows():
            try:
                existing_steward = None
                if 'email' in df.columns and row.get('email') is not None and str(row.get('email')).strip():
                    existing_steward = Steward.query.filter_by(email=row['email']).first()
                elif 'tax_code' in df.columns and row.get('tax_code') is not None and str(row.get('tax_code')).strip():
                    existing_steward = Steward.query.filter_by(tax_code=row['tax_code']).first()
                if existing_steward:
                    error_count += 1
                    continue
                new_steward = Steward(
                    nome=str(row['nome']).strip(),
                    cognome=str(row['cognome']).strip(),
                    email=str(row.get('email', '')).strip() if row.get('email') is not None and str(row.get('email')).strip() else None,
                    phone=str(row.get('phone', '')).strip() if row.get('phone') is not None and str(row.get('phone')).strip() else None,
                    address=str(row.get('address', '')).strip() if row.get('address') is not None and str(row.get('address')).strip() else None,
                    tax_code=str(row.get('tax_code', '')).strip() if row.get('tax_code') is not None and str(row.get('tax_code')).strip() else None,
                    iban=str(row.get('iban', '')).strip() if row.get('iban') is not None and str(row.get('iban')).strip() else None,
                    document_type=str(row.get('document_type', '')).strip() if row.get('document_type') is not None and str(row.get('document_type')).strip() else None,
                    document_number=str(row.get('document_number', '')).strip() if row.get('document_number') is not None and str(row.get('document_number')).strip() else None,
                    experience=str(row.get('experience', '')).strip() if row.get('experience') is not None and str(row.get('experience')).strip() else None,
                    carta_identita_path='',
                    codice_fiscale_path='',
                    attestato_path='',
                    autocertificazione_path='',
                    patente_path=''
                )
                db.session.add(new_steward)
                success_count += 1
            except Exception as e:
                error_count += 1
                continue
        db.session.commit()
        if success_count > 0:
            flash(f'✅ Importazione completata! {success_count} steward importati con successo.', 'success')
        if error_count > 0:
            flash(f'⚠️ {error_count} record non importati (duplicati o errori).', 'warning')
    except Exception as e:
        flash(f'❌ Errore durante l\'importazione: {str(e)}', 'error')
    return redirect(url_for('stewards'))

@app.route('/stewards/add', methods=['GET', 'POST'])
def add_steward():
    print('DEBUG: Entrato in /stewards/add, metodo:', request.method)
    import os
    from werkzeug.utils import secure_filename
    from datetime import datetime
    if request.method == 'POST':
        nome = request.form.get('nome')
        cognome = request.form.get('cognome')
        email = request.form.get('email')
        phone = request.form.get('phone')
        address = request.form.get('address')
        tax_code = request.form.get('tax_code')
        iban = request.form.get('iban')
        document_type = request.form.get('document_type')
        document_number = request.form.get('document_number')
        expiry_date_str = request.form.get('document_expiry')
        experience = request.form.get('experience')
        document_expiry = datetime.strptime(expiry_date_str, '%Y-%m-%d').date() if expiry_date_str else None

        # Upload documenti
        upload_folder = os.path.join(os.getcwd(), 'uploads')
        os.makedirs(upload_folder, exist_ok=True)
        def save_file(field_name):
            file = request.files.get(field_name)
            if not file or file.filename == '':
                return ''
            filename_str = file.filename or ''
            ext = os.path.splitext(filename_str)[1].lower()
            if ext not in ['.jpg', '.jpeg', '.pdf']:
                flash(f"Il file per {field_name.replace('_', ' ').title()} deve essere JPG o PDF", 'warning')
                return ''
            filename = secure_filename(f"{field_name}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}")
            file_path = os.path.join(upload_folder, filename)
            file.save(file_path)
            return file_path
        carta_identita_path = save_file('carta_identita')
        codice_fiscale_path = save_file('codice_fiscale')
        attestato_path = save_file('attestato')
        autocertificazione_path = save_file('autocertificazione')
        patente_path = save_file('patente')

        # Controllo duplicati
        if email and Steward.query.filter_by(email=email).first():
            flash('Esiste già uno steward con questa email.', 'danger')
            return redirect(url_for('add_steward'))
        if tax_code and Steward.query.filter_by(tax_code=tax_code).first():
            flash('Esiste già uno steward con questo codice fiscale.', 'danger')
            return redirect(url_for('add_steward'))
        if not nome or not cognome:
            flash('Nome e cognome sono obbligatori.', 'warning')
            return redirect(url_for('add_steward'))

        new_steward = Steward(
            nome=nome,
            cognome=cognome,
            email=email,
            phone=phone,
            address=address,
            tax_code=tax_code,
            iban=iban,
            document_type=document_type,
            document_number=document_number,
            document_expiry=document_expiry,
            experience=experience,
            carta_identita_path=carta_identita_path,
            codice_fiscale_path=codice_fiscale_path,
            attestato_path=attestato_path,
            autocertificazione_path=autocertificazione_path,
            patente_path=patente_path
        )
        db.session.add(new_steward)
        db.session.commit()
        flash('Steward aggiunto con successo!', 'success')
        return redirect(url_for('stewards'))
    return render_template('add_steward.html')

@app.route('/export_stewards')
def export_stewards():
    import pandas as pd
    import io
    from flask import send_file, flash
    from datetime import datetime
    try:
        stewards = Steward.query.all()
        data = []
        for steward in stewards:
            data.append({
                'Nome': steward.nome,
                'Cognome': steward.cognome,
                'Email': steward.email or '',
                'Telefono': steward.phone or '',
                'Indirizzo': steward.address or '',
                'Codice Fiscale': steward.tax_code or '',
                'IBAN': steward.iban or '',
                'Tipo Documento': steward.document_type or '',
                'Numero Documento': steward.document_number or '',
                'Scadenza': steward.document_expiry.strftime('%d/%m/%Y') if steward.document_expiry else '',
                'Esperienza': steward.experience or ''
            })
        df = pd.DataFrame(data)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter', engine_kwargs={}) as writer:
            df.to_excel(writer, sheet_name='Steward', index=False)
        output.seek(0)
        flash('✅ Esportazione completata con successo!', 'success')
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'steward_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
        )
    except Exception as e:
        flash(f'❌ Errore durante l\'esportazione: {str(e)}', 'error')
        return redirect(url_for('stewards'))

@app.route('/reset_admin')
def reset_admin():
    from werkzeug.security import generate_password_hash
    admin = User.query.filter_by(username='admin').first()
    if not admin:
        admin = User(username='admin', email='admin@admin.com', nome='Admin', cognome='Admin', ruolo='admin')
        db.session.add(admin)
    admin.password_hash = generate_password_hash('admin123')
    db.session.commit()
    return 'Password admin resettata! Username: admin, Password: admin123'

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/esporta_eventi')
def esporta_eventi():
    from datetime import datetime
    import io
    import pandas as pd
    from flask import send_file
    filtro = request.args.get('filtro', 'annuale')
    formato = request.args.get('formato', 'pdf')
    eventi = Evento.query.order_by(Evento.data_inizio.asc()).all()
    titolo = "Elenco Eventi"
    if filtro == 'annuale':
        anno = datetime.now().year
        eventi = [e for e in eventi if e.data_inizio.year == anno]
        titolo = f"Elenco Eventi {anno}"
    elif filtro == 'mensile':
        mese = request.args.get('mese')
        if mese:
            anno, mese_num = map(int, mese.split('-'))
            eventi = [e for e in eventi if e.data_inizio.year == anno and e.data_inizio.month == mese_num]
            titolo = f"Elenco Eventi {mese_num:02d}/{anno}"
    elif filtro == 'singolo':
        evento_id = request.args.get('evento_id')
        if evento_id:
            eventi = [e for e in eventi if str(e.id) == str(evento_id)]
            if eventi:
                titolo = f"Evento: {eventi[0].nome} ({eventi[0].data_inizio.strftime('%d/%m/%Y')})"
    # Preparo dati per tabella
    rows = []
    for e in eventi:
        partecipanti = ', '.join([f"{p.steward.nome} {p.steward.cognome}" for p in e.partecipazioni])
        rows.append({
            'Nome': e.nome,
            'Data Inizio': e.data_inizio.strftime('%d/%m/%Y %H:%M'),
            'Data Fine': e.data_fine.strftime('%d/%m/%Y %H:%M'),
            'Luogo': e.luogo or '',
            'Tipo': e.tipo_evento or '',
            'Stato': e.stato,
            'Budget': f'{e.budget:.2f} €' if e.budget else '',
            'Note': e.note or '',
            'Partecipanti': partecipanti
        })
    df = pd.DataFrame(rows)
    if formato == 'excel':
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter', engine_kwargs={}) as writer:
            df.to_excel(writer, index=False, sheet_name='Eventi')
        output.seek(0)
        return send_file(output, download_name='elenco_eventi.xlsx', as_attachment=True)
    else:  # PDF
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        from reportlab.lib.units import cm
        output = io.BytesIO()
        c = canvas.Canvas(output, pagesize=A4)
        width, height = A4
        c.setFont('Helvetica-Bold', 16)
        c.drawString(2*cm, height-2*cm, titolo)
        c.setFont('Helvetica', 10)
        y = height-3*cm
        for row in rows:
            text = f"{row['Nome']} | {row['Data Inizio']} - {row['Data Fine']} | {row['Luogo']} | {row['Tipo']} | {row['Stato']} | {row['Budget']} | {row['Note']}"
            c.drawString(2*cm, y, text)
            y -= 0.7*cm
            c.setFont('Helvetica-Oblique', 9)
            c.drawString(2.5*cm, y, f"Partecipanti: {row['Partecipanti']}")
            y -= 1*cm
            c.setFont('Helvetica', 10)
            if y < 3*cm:
                c.showPage()
                y = height-2*cm
                c.setFont('Helvetica', 10)
        c.save()
        output.seek(0)
        return send_file(output, download_name='elenco_eventi.pdf', as_attachment=True, mimetype='application/pdf')

@app.route('/event/<int:evento_id>/edit', methods=['GET', 'POST'])
def edit_event(evento_id):
    evento = Evento.query.get_or_404(evento_id)
    if request.method == 'POST':
        data_inizio_str = request.form.get('data_inizio')
        data_fine_str = request.form.get('data_fine')
        if not data_inizio_str or not data_fine_str:
            flash('⚠️ Data inizio e fine obbligatorie!', 'warning')
            return redirect(url_for('edit_event', evento_id=evento_id))
        try:
            data_inizio = datetime.datetime.strptime(data_inizio_str, '%Y-%m-%dT%H:%M')
            data_fine = datetime.datetime.strptime(data_fine_str, '%Y-%m-%dT%H:%M')
        except Exception:
            flash('⚠️ Formato data non valido!', 'warning')
            return redirect(url_for('edit_event', evento_id=evento_id))
        if data_fine < data_inizio:
            flash('⚠️ La data di fine deve essere successiva o uguale alla data di inizio!', 'warning')
            return redirect(url_for('edit_event', evento_id=evento_id))
        budget = request.form.get('budget')
        try:
            budget = float(budget) if budget else None
        except Exception:
            budget = None
        evento.nome = request.form.get('nome')
        evento.descrizione = request.form.get('descrizione')
        evento.data_inizio = data_inizio
        evento.data_fine = data_fine
        evento.luogo = request.form.get('luogo')
        evento.tipo_evento = request.form.get('tipo_evento')
        evento.stato = request.form.get('stato', 'pianificato')
        evento.budget = budget
        evento.note = request.form.get('note')
        db.session.commit()
        flash(f'✅ Evento "{evento.nome}" modificato con successo!', 'success')
        return redirect(url_for('events'))
    return render_template('edit_event.html', evento=evento)

@app.route('/event/<int:evento_id>/delete')
def delete_event(evento_id):
    evento = Evento.query.get_or_404(evento_id)
    nome_evento = evento.nome
    db.session.delete(evento)
    db.session.commit()
    flash(f'✅ Evento "{nome_evento}" eliminato con successo!', 'success')
    return redirect(url_for('events'))

@app.route('/events/export')
def export_events():
    import pandas as pd
    import io
    from flask import send_file
    from datetime import datetime
    try:
        eventi = Evento.query.order_by(Evento.data_inizio.asc()).all()
        data = []
        for evento in eventi:
            data.append({
                'Nome': evento.nome,
                'Descrizione': evento.descrizione or '',
                'Data Inizio': evento.data_inizio.strftime('%d/%m/%Y %H:%M'),
                'Data Fine': evento.data_fine.strftime('%d/%m/%Y %H:%M'),
                'Luogo': evento.luogo or '',
                'Tipo Evento': evento.tipo_evento or '',
                'Stato': evento.stato,
                'Budget': f'{evento.budget:.2f} €' if evento.budget else '',
                'Note': evento.note or '',
                'Creato il': evento.created_at.strftime('%d/%m/%Y %H:%M'),
                'Aggiornato il': evento.updated_at.strftime('%d/%m/%Y %H:%M')
            })
        df = pd.DataFrame(data)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter', engine_kwargs={}) as writer:
            df.to_excel(writer, sheet_name='Eventi', index=False)
        output.seek(0)
        flash('✅ Esportazione eventi completata con successo!', 'success')
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'eventi_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
        )
    except Exception as e:
        flash(f'❌ Errore durante l\'esportazione: {str(e)}', 'error')
        return redirect(url_for('events'))

if __name__ == '__main__':
    print('ROUTES:')
    for rule in app.url_map.iter_rules():
        print(rule)
    app.run(debug=True)

# NON CI DEVE ESSERE ALTRO CODICE DOPO QUESTA RIGA
