from flask import Flask, request, redirect, url_for, flash, get_flashed_messages, send_file, render_template_string, render_template, send_from_directory, session
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
from sqlalchemy import extract, func
try:
    import holidays
except ImportError:
    holidays = None
import tempfile

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
    evento = db.relationship('Evento', backref=db.backref('partecipazioni', lazy=True))
    steward = db.relationship('Steward', backref=db.backref('partecipazioni_eventi', lazy=True))

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
    except Exception as e:
        print(f"⚠️ Errore durante la migrazione: {e}")
        # Se c'è un errore, ricrea il database
        try:
            db.drop_all()
            db.create_all()
            print("✅ Database ricreato con successo")
        except Exception as e2:
            print(f"❌ Errore nella ricreazione del database: {e2}")


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
            return redirect(url_for('dashboard'))
        else:
            flash('⚠️ Username o password non validi!', 'warning')
    
    messages_html = ''.join(f'<div class="flash-message flash-{c}"><span style="font-size:1.2em;">{"✅" if c == "success" else "❌" if c == "error" else "⚠️"}</span><span>{m}</span></div>' for c, m in get_flashed_messages(with_categories=True))
    form_html = '''
        <div class="form-group"><label for="username">Username</label><input type="text" id="username" name="username" required></div>
        <div class="form-group"><label for="password">Password</label><input type="password" id="password" name="password" required></div>
    '''
    link_html = '<p>Non hai un account? <a href="/register">Registrati qui</a></p>'
    return render_form_page('Login', form_html, link_html, messages_html)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
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

    messages_html = ''.join(f'<div class="flash-message flash-{c}"><span style="font-size:1.2em;">{"✅" if c == "success" else "❌" if c == "error" else "⚠️"}</span><span>{m}</span></div>' for c, m in get_flashed_messages(with_categories=True))
    form_html = '''
        <div class="form-group"><label for="username">Username</label><input type="text" id="username" name="username" required></div>
        <div class="form-group"><label for="password">Password</label><input type="password" id="password" name="password" required></div>
    '''
    link_html = '<p>Hai già un account? <a href="/login">Accedi qui</a></p>'
    return render_form_page('Registrati', form_html, link_html, messages_html)

@app.route('/dashboard')
def dashboard():
    num_stewards = Steward.query.count()
    num_eventi = Evento.query.count()
    saldo = db.session.query(db.func.sum(MovimentoFinanziario.importo)).scalar() or 0

    now = datetime.datetime.now()
    eventi_imminenti = Evento.query.filter(Evento.data_inizio >= now, Evento.data_inizio <= now + datetime.timedelta(days=7)).count()
    ultimi_eventi = Evento.query.order_by(Evento.data_inizio.desc()).limit(5).all()

    # Grafico eventi per tipo
    tipo_counts = db.session.query(Evento.tipo_evento, func.count(Evento.id)).group_by(Evento.tipo_evento).all()
    tipo_labels = [t[0] for t in tipo_counts]
    tipo_data = [t[1] for t in tipo_counts]

    # Grafico eventi per stato
    stato_counts = db.session.query(Evento.stato, func.count(Evento.id)).group_by(Evento.stato).all()
    stato_labels = [s[0] for s in stato_counts]
    stato_data = [s[1] for s in stato_counts]

    # Saldo per mese (ultimi 12 mesi)
    saldi_mensili = []
    mesi_ordinati = []
    for i in range(11, -1, -1):
        mese = (now - datetime.timedelta(days=30*i)).replace(day=1)
        mese_str = mese.strftime('%b %Y')
        mesi_ordinati.append(mese_str)
        saldo_mese = db.session.query(func.sum(MovimentoFinanziario.importo)).filter(
            extract('year', MovimentoFinanziario.data) == mese.year,
            extract('month', MovimentoFinanziario.data) == mese.month
        ).scalar() or 0
        saldi_mensili.append(round(saldo_mese, 2))

    # Eventi per calendario
    eventi_cal = []
    for ev in Evento.query.all():
        eventi_cal.append({
            "id": ev.id,
            "title": ev.nome,
            "start": ev.data_inizio.strftime('%Y-%m-%d'),
            "end": ev.data_fine.strftime('%Y-%m-%d'),
            "color": "#17a2b8",
            "descrizione": ev.descrizione or ""
        })

    # Festività italiane (libreria holidays)
    holidays_list = []
    if holidays:
        try:
            it_holidays = holidays.country_holidays('IT', years=now.year)
            for date, label in it_holidays.items():
                holidays_list.append({"date": str(date), "label": label})
        except Exception:
            holidays_list = [
                {"date": "2025-01-01", "label": "Capodanno"},
                {"date": "2025-12-25", "label": "Natale"},
            ]
    else:
        holidays_list = [
            {"date": "2025-01-01", "label": "Capodanno"},
            {"date": "2025-12-25", "label": "Natale"},
        ]

    # Domeniche (ultimi 12 mesi)
    sundays = []
    for i in range(365):
        d = now - datetime.timedelta(days=i)
        if d.weekday() == 6:
            sundays.append(d.strftime('%Y-%m-%d'))

    # Meteo prossimo evento (demo statica)
    prossimo_evento = Evento.query.filter(Evento.data_inizio >= now).order_by(Evento.data_inizio).first()
    meteo_info_dashboard = None
    if prossimo_evento:
        meteo_info_dashboard = {
            "evento": prossimo_evento,
            "icon": "☀️",
            "desc": "Soleggiato",
            "tmin": 18,
            "tmax": 28,
            "rain": 0
        }

    return render_template('dashboard.html',
        num_stewards=num_stewards,
        num_eventi=num_eventi,
        saldo=saldo,
        eventi_imminenti=eventi_imminenti,
        ultimi_eventi=ultimi_eventi,
        tipo_labels=tipo_labels,
        tipo_data=tipo_data,
        stato_labels=stato_labels,
        stato_data=stato_data,
        mesi_ordinati=mesi_ordinati,
        saldi_mensili=saldi_mensili,
        eventi_cal=eventi_cal,
        holidays_list=holidays_list,
        sundays=sundays,
        meteo_info_dashboard=meteo_info_dashboard
    )
    
# 4. PAGINA ANAGRAFICA STEWARD
@app.route('/stewards', methods=['GET', 'POST'])
def stewards():
    if request.method == 'POST':
        expiry_date_str = request.form.get('document_expiry')
        expiry_date = datetime.datetime.strptime(expiry_date_str, '%Y-%m-%d').date() if expiry_date_str else None

        # Gestione upload file obbligatori con validazione JPG
        upload_folder = os.path.join(os.getcwd(), 'uploads')
        os.makedirs(upload_folder, exist_ok=True)
        
        def save_file(field_name):
            file = request.files.get(field_name)
            if not file or file.filename == '':
                return ''  # Non obbligatorio, restituisco stringa vuota
            if file.filename and not file.filename.lower().endswith(('.jpg', '.jpeg')):
                flash(f"⚠️ Il file '{field_name.replace('_', ' ').title()}' deve essere in formato JPG/JPEG!", 'warning')
                return ''
            filename = f"{field_name}_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}"
            file_path = os.path.join(upload_folder, filename)
            file.save(file_path)
            return file_path

        carta_identita_path = save_file('carta_identita')
        codice_fiscale_path = save_file('codice_fiscale')
        attestato_path = save_file('attestato')
        autocertificazione_path = save_file('autocertificazione')
        patente_path = save_file('patente')

        # Controllo duplicati su email e codice fiscale
        email = request.form.get('email')
        tax_code = request.form.get('tax_code')
        if email and Steward.query.filter_by(email=email).first():
            flash('❌ Esiste già uno steward con questa email.', 'error')
            return redirect(url_for('stewards'))
        if tax_code and Steward.query.filter_by(tax_code=tax_code).first():
            flash('❌ Esiste già uno steward con questo codice fiscale.', 'error')
            return redirect(url_for('stewards'))

        new_steward = Steward(
            nome=request.form.get('nome'),
            cognome=request.form.get('cognome'),
            email=request.form.get('email'),
            phone=request.form.get('phone'),
            address=request.form.get('address'),
            tax_code=request.form.get('tax_code'),
            iban=request.form.get('iban'),
            document_type=request.form.get('document_type'),
            document_number=request.form.get('document_number'),
            document_expiry=expiry_date,
            experience=request.form.get('experience'),
            carta_identita_path=carta_identita_path,
            codice_fiscale_path=codice_fiscale_path,
            attestato_path=attestato_path,
            autocertificazione_path=autocertificazione_path,
            patente_path=patente_path
        )
        if not new_steward.nome or not new_steward.cognome:
            flash('⚠️ Il nome e il cognome sono campi obbligatori.', 'warning')
        else:
            db.session.add(new_steward)
            db.session.commit()
            flash(f'✅ Steward "{new_steward.nome} {new_steward.cognome}" aggiunto con successo!', 'success')
        return redirect(url_for('stewards'))

    # --- FILTRI E RICERCA ---
    search_query = request.args.get('search', '').strip().lower()
    filter_missing_docs = request.args.get('missing_docs', '') == '1'
    filter_expiring = request.args.get('expiring', '') == '1'

    stewards_list = Steward.query.order_by(Steward.nome, Steward.cognome).all()
    filtered_stewards = []
    today = date.today()
    for s in stewards_list:
        # Ricerca
        if search_query:
            if not (
                search_query in (s.nome or '').lower() or
                search_query in (s.cognome or '').lower() or
                search_query in (s.email or '').lower() or
                search_query in (s.tax_code or '').lower()
            ):
                continue
        # Filtro documenti mancanti
        missing_docs = []
        if not s.carta_identita_path:
            missing_docs.append('Carta d\'Identità')
        if not s.codice_fiscale_path:
            missing_docs.append('Codice Fiscale')
        if not s.attestato_path:
            missing_docs.append('Attestato')
        if not s.autocertificazione_path:
            missing_docs.append('Autocertificazione')
        if not s.patente_path:
            missing_docs.append('Patente')
        if filter_missing_docs and not missing_docs:
            continue
        # Filtro documenti in scadenza (entro 30 giorni)
        is_expiring = False
        if s.document_expiry and s.document_expiry <= today + timedelta(days=30):
            is_expiring = True
        if filter_expiring and not is_expiring:
            continue
        filtered_stewards.append((s, missing_docs, is_expiring))

    # --- FORM DI RICERCA E FILTRI ---
    search_html = render_template_string('''
    <form method="get" style="margin-bottom:20px;display:flex;flex-wrap:wrap;gap:10px;align-items:center;">
        <input type="text" name="search" placeholder="Cerca nome, cognome, email, codice fiscale" value="{{ search_value }}" style="padding:8px;border-radius:5px;border:1px solid #ccc;min-width:220px;">
        <label style="display:flex;align-items:center;gap:5px;font-size:0.95em;">
            <input type="checkbox" name="missing_docs" value="1" {{ 'checked' if filter_missing_docs else '' }}> Solo con documenti mancanti
        </label>
        <label style="display:flex;align-items:center;gap:5px;font-size:0.95em;">
            <input type="checkbox" name="expiring" value="1" {{ 'checked' if filter_expiring else '' }}> Solo con documenti in scadenza
        </label>
        <button type="submit" class="btn" style="background:#17a2b8;">🔍 Cerca/Filtra</button>
        <a href="/stewards" class="btn" style="background:#aaa;">Azzera</a>
    </form>
    ''', search_value=request.args.get('search',''), filter_missing_docs=filter_missing_docs, filter_expiring=filter_expiring)

    table_rows = ""
    for s, missing_docs, is_expiring in filtered_stewards:
        expiry_str = s.document_expiry.strftime('%d-%m-%Y') if s.document_expiry else ''
        # Evidenziazione documenti mancanti
        evidenzia = 'background-color:#fff3cd;color:#856404;font-weight:bold;' if missing_docs else ''
        segnalazione = f'<span style="color:#856404;font-size:1.2em;">⚠️</span> <span style="color:#856404;">Documenti mancanti: {", ".join(missing_docs)}</span>' if missing_docs else ''
        # Evidenziazione scadenza
        if is_expiring:
            evidenzia = 'background-color:#ffd6d6;color:#a94442;font-weight:bold;'
            segnalazione += '<br><span style="color:#a94442;font-size:1.2em;">⏰</span> <span style="color:#a94442;">Documento in scadenza!</span>'
        # Download documenti
        doc_links = []
        if s.carta_identita_path:
            doc_links.append(f'<a href="/download/{s.id}/carta_identita" target="_blank">Carta d\'Identità</a>')
        if s.codice_fiscale_path:
            doc_links.append(f'<a href="/download/{s.id}/codice_fiscale" target="_blank">Codice Fiscale</a>')
        if s.attestato_path:
            doc_links.append(f'<a href="/download/{s.id}/attestato" target="_blank">Attestato</a>')
        if s.autocertificazione_path:
            doc_links.append(f'<a href="/download/{s.id}/autocertificazione" target="_blank">Autocertificazione</a>')
        if s.patente_path:
            doc_links.append(f'<a href="/download/{s.id}/patente" target="_blank">Patente</a>')
        doc_links_html = '<br>'.join(doc_links)
        table_rows += f'''
            <tr style="{evidenzia}">
                <td>{s.nome}</td>
                <td>{s.cognome}</td>
                <td>{s.address or ''}</td>
                <td>{s.tax_code or ''}</td>
                <td>{s.iban or ''}</td>
                <td>{f"{s.document_type or ''} N. {s.document_number or ''}"}<br>{doc_links_html}</td>
                <td>{expiry_str}</td>
                <td><a href="/steward/{s.id}/edit" class="btn" style="background:#28a745;">Modifica</a> <a href="/export_steward_pdf/{s.id}" class="btn" style="background:#e74c3c;margin-left:5px;">PDF</a><br>{segnalazione}</td>
            </tr>'''
    
    # Aggiungo i pulsanti per import/export Excel
    excel_buttons = '''
    <div style="margin-bottom: 20px; text-align: center;">
        <form method="POST" action="/import_stewards" enctype="multipart/form-data" style="display: inline-block; margin-right: 10px;">
            <input type="file" name="file" accept=".xlsx,.xls" required style="margin-right: 10px;">
            <button type="submit" class="btn" style="background: #17a2b8;">📥 Importa Excel</button>
        </form>
        <a href="/export_stewards" class="btn" style="background: #28a745;">📄 Esporta Excel</a>
        <a href="/export_stewards_pdf" class="btn" style="background: #e74c3c;">📄 Esporta PDF</a>
    </div>
    '''
    
    messages_html = ''.join(f'<div class="flash-message flash-{c}"><span style="font-size:1.2em;">{"✅" if c == "success" else "❌" if c == "error" else "⚠️"}</span><span>{m}</span></div>' for c, m in get_flashed_messages(with_categories=True))
    
    table_html = render_template_string('''
    <!DOCTYPE html><html><head><title>Gestione Steward</title><meta name="viewport" content="width=device-width, initial-scale=1.0"><style>body{font-family:Arial,sans-serif;margin:0;background:#f4f4f9}.header{background:#667eea;color:white;padding:15px 30px;text-align:center;font-size:1.5em}.container{padding:30px;max-width:1200px;margin:auto}table{width:100%;border-collapse:collapse;margin-top:20px}th,td{padding:10px;border:1px solid #ddd;text-align:left}th{background:#667eea;color:white}tr:nth-child(even){background:#f9f9f9}.btn{background:#667eea;color:white;padding:8px 15px;border:none;border-radius:5px;text-decoration:none;cursor:pointer;margin:2px}.btn:hover{background:#5a6fd8}.btn-danger{background:#dc3545}.btn-success{background:#28a745}.btn-warning{background:#ffc107;color:#212529}.btn-info{background:#17a2b8}.flash-message{padding:10px;margin-bottom:10px;border-radius:6px;text-align:center;display:flex;align-items:center;gap:10px;font-weight:bold}.flash-success{background-color:#d4edda;color:#155724;border:1px solid #c3e6cb}.flash-error{background-color:#f8d7da;color:#721c24;border:1px solid #f5c6cb}.flash-warning{background-color:#fff3cd;color:#856404;border:1px solid #ffeeba}.form-row{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:20px}.form-row input,.form-row select,.form-row textarea{padding:8px;border-radius:5px;border:1px solid #ccc}.form-row textarea{resize:vertical;min-height:80px}.header-buttons{position:absolute;top:15px;right:30px}.header-buttons .btn{background:rgba(255,255,255,0.2);border:1px solid rgba(255,255,255,0.3)}.stato-badge{padding:4px 8px;border-radius:12px;color:white;font-size:0.8em;font-weight:bold}.event-actions{display:flex;flex-wrap:wrap;gap:5px}.event-actions .btn{font-size:0.8em;padding:4px 8px}</style></head><body><div class="header">Gestione Steward<div class="header-buttons"><a href="/dashboard" class="btn">🏠 Dashboard</a></div></div><div class="container">{{ messages_html|safe }}{{ search_html|safe }}<form method="POST" enctype="multipart/form-data"><div class="form-row"><input type="text" name="nome" placeholder="Nome *" required><input type="text" name="cognome" placeholder="Cognome *" required><input type="email" name="email" placeholder="Email"><input type="tel" name="phone" placeholder="Telefono"><input type="text" name="address" placeholder="Indirizzo"><input type="text" name="tax_code" placeholder="Codice Fiscale"><input type="text" name="iban" placeholder="IBAN"><input type="text" name="document_type" placeholder="Tipo Documento"><input type="text" name="document_number" placeholder="Numero Documento"><input type="date" name="document_expiry" placeholder="Scadenza Documento"><input type="text" name="experience" placeholder="Esperienza"></div><div class="form-row"><label>Documenti (JPG/JPEG):</label><input type="file" name="carta_identita" accept=".jpg,.jpeg" placeholder="Carta d'Identità"><input type="file" name="codice_fiscale" accept=".jpg,.jpeg" placeholder="Codice Fiscale"><input type="file" name="attestato" accept=".jpg,.jpeg" placeholder="Attestato"><input type="file" name="autocertificazione" accept=".jpg,.jpeg" placeholder="Autocertificazione"><input type="file" name="patente" accept=".jpg,.jpeg" placeholder="Patente"></div><button type="submit" class="btn">Aggiungi Steward</button></form><div style="margin:20px 0;"><a href="/import_stewards" class="btn btn-success">📥 Importa Excel</a> <a href="/export_stewards" class="btn btn-warning">📤 Esporta Excel</a> <a href="/export_stewards_pdf" class="btn btn-danger">📄 Esporta PDF</a></div><table><tr><th>Nome</th><th>Cognome</th><th>Email</th><th>Telefono</th><th>Codice Fiscale</th><th>Scadenza</th><th>Documenti</th><th>Azioni</th></tr>{{ table_rows|safe }}</table></div></body></html>
    ''', messages_html=messages_html, search_html=search_html, table_rows=table_rows)
    return table_html

# 5. FUNZIONI IMPORT/EXPORT EXCEL
@app.route('/import_stewards', methods=['POST'])
def import_stewards():
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
        # Leggi il file Excel con intestazioni in italiano
        df = pd.read_excel(file)
        # Mappatura colonne italiane -> inglese
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

@app.route('/export_stewards')
def export_stewards():
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
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as tmp:
            with pd.ExcelWriter(tmp.name, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='Steward', index=False)
            tmp.seek(0)
            output = io.BytesIO(tmp.read())
        output.seek(0)
        flash('✅ Esportazione completata con successo!', 'success')
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'steward_export_{datetime.datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
        )
    except Exception as e:
        flash(f'❌ Errore durante l\'esportazione: {str(e)}', 'error')
        return redirect(url_for('stewards'))

@app.route('/export_stewards_pdf')
def export_stewards_pdf():
    try:
        stewards = Steward.query.all()
        buffer = io.BytesIO()
        p = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4
        y = height - 40
        p.setFont("Helvetica-Bold", 16)
        p.drawString(40, y, "Elenco Steward")
        y -= 30
        p.setFont("Helvetica", 10)
        for s in stewards:
            line = f"{s.nome} {s.cognome} | Email: {s.email or ''} | Tel: {s.phone or ''} | Cod. Fiscale: {s.tax_code or ''} | Scadenza: {s.document_expiry.strftime('%d/%m/%Y') if s.document_expiry else ''}"
            p.drawString(40, y, line)
            y -= 18
            if y < 50:
                p.showPage()
                y = height - 40
        p.save()
        buffer.seek(0)
        return send_file(buffer, as_attachment=True, download_name=f'steward_export_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf', mimetype='application/pdf')
    except Exception as e:
        flash(f'❌ Errore durante l\'esportazione PDF: {str(e)}', 'error')
        return redirect(url_for('stewards'))

@app.route('/export_steward_pdf/<int:steward_id>', methods=['GET', 'POST'])
def export_steward_pdf(steward_id):
    import os
    from flask import request
    steward = Steward.query.get_or_404(steward_id)
    fields = [
        ('nome', 'Nome'),
        ('cognome', 'Cognome'),
        ('email', 'Email'),
        ('phone', 'Telefono'),
        ('address', 'Indirizzo'),
        ('tax_code', 'Codice Fiscale'),
        ('iban', 'IBAN'),
        ('document_type', 'Tipo Documento'),
        ('document_number', 'Numero Documento'),
        ('document_expiry', 'Scadenza Documento'),
        ('experience', 'Esperienza'),
    ]
    preselected = {'nome', 'cognome', 'email', 'tax_code'}
    if request.method == 'POST':
        selected = request.form.getlist('fields')
        if not selected:
            return 'Seleziona almeno un campo', 400
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        pdf_filename = f'steward_{steward.id}_{steward.nome}_{steward.cognome}.pdf'
        pdf_path = os.path.join('uploads', pdf_filename)
        buffer = open(pdf_path, 'wb')
        p = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4
        y = height - 40
        p.setFont("Helvetica-Bold", 16)
        p.drawString(40, y, f"Dati Steward: {steward.nome} {steward.cognome}")
        y -= 30
        p.setFont("Helvetica", 10)
        for key, label in fields:
            if key in selected:
                value = getattr(steward, key, '')
                if value is None:
                    value = ''
                if key == 'document_expiry' and value:
                    if isinstance(value, datetime.date):
                        value = value.strftime('%d/%m/%Y')
                p.drawString(40, y, f"{label}: {value}")
                y -= 18
        p.save()
        buffer.close()
        
        # Link pubblico
        pdf_url = f"/uploads/{pdf_filename}"
        full_pdf_url = f"{request.host_url.strip('/')}{pdf_url}"
        
        # Messaggio per WhatsApp
        whatsapp_msg = f"PDF dello steward {steward.nome} {steward.cognome}: {full_pdf_url}"
        whatsapp_url = f"https://wa.me/?text={whatsapp_msg.replace(' ', '%20').replace(':', '%3A').replace('/', '%2F')}"
        
        # Email
        email_subject = f"PDF Steward {steward.nome} {steward.cognome}"
        email_body = f"Ecco il PDF dello steward {steward.nome} {steward.cognome}:\n\n{full_pdf_url}"
        mailto_url = f"mailto:?subject={email_subject.replace(' ', '%20')}&body={email_body.replace(' ', '%20').replace('\n', '%0A')}"
        
        return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>PDF Generato</title>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                body { font-family: Arial, sans-serif; margin: 0; background: #f4f4f9; }
                .container { max-width: 800px; margin: 20px auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 5px 15px rgba(0,0,0,0.1); }
                .header { background: #667eea; color: white; padding: 15px 30px; text-align: center; font-size: 1.5em; }
                .btn { display: inline-block; padding: 12px 24px; margin: 10px 5px; background: #667eea; color: white; text-decoration: none; border-radius: 5px; font-weight: bold; }
                .btn-whatsapp { background: #25d366; }
                .btn-email { background: #0072c6; }
                .btn-download { background: #28a745; }
                .btn-back { background: #6c757d; }
                .link-box { background: #f8f9fa; padding: 15px; border-radius: 5px; margin: 20px 0; border: 1px solid #dee2e6; }
                .link-input { width: 100%; padding: 10px; border: 1px solid #ccc; border-radius: 4px; font-family: monospace; }
                .instructions { background: #e7f3ff; padding: 15px; border-radius: 5px; margin: 20px 0; border-left: 4px solid #0072c6; }
                .warning { background: #fff3cd; padding: 15px; border-radius: 5px; margin: 20px 0; border-left: 4px solid #ffc107; }
            </style>
            <script>
            function copyToClipboard(el) {
                if (navigator.clipboard) {
                    navigator.clipboard.writeText(el.value).then(function() {
                        alert('Copiato negli appunti!');
                    }, function() {
                        el.select();
                        document.execCommand('copy');
                        alert('Copiato negli appunti!');
                    });
                } else {
                    el.select();
                    document.execCommand('copy');
                    alert('Copiato negli appunti!');
                }
            }
            </script>
        </head>
        <body>
            <div class="container">
                <div class="header">PDF Generato con Successo</div>
                
                <h2>PDF per {{ steward.nome }} {{ steward.cognome }}</h2>
                
                <div class="instructions">
                    <strong>📋 Istruzioni per la condivisione:</strong><br>
                    1. Scarica il PDF cliccando su "Scarica PDF"<br>
                    2. Per WhatsApp: clicca su "Condividi su WhatsApp" o copia il link manualmente<br>
                    3. Per Email: clicca su "Invia via Email" o copia il link nel messaggio
                </div>
                
                <div class="warning">
                    <strong>⚠️ Nota importante:</strong><br>
                    WhatsApp Web non può inviare file direttamente. Il link aprirà WhatsApp con un messaggio contenente il link al PDF. 
                    Il destinatario dovrà cliccare sul link per scaricare il PDF.
                </div>
                
                <a href="{{ pdf_url }}" class="btn btn-download" target="_blank">📥 Scarica PDF</a>
                <a href="{{ whatsapp_url }}" class="btn btn-whatsapp" target="_blank">📱 Condividi su WhatsApp</a>
                <a href="{{ mailto_url }}" class="btn btn-email" target="_blank">📧 Invia via Email</a>
                <a href="/stewards" class="btn btn-back">← Torna alla gestione steward</a>
                
                <div class="link-box">
                    <strong>🔗 Link diretto al PDF:</strong><br>
                    <input type="text" value="{{ full_pdf_url }}" class="link-input" readonly onclick="copyToClipboard(this)" title="Clicca per copiare">
                    <br><small>Clicca sul link per copiarlo negli appunti</small>
                </div>
                
                <div class="link-box">
                    <strong>📱 Messaggio per WhatsApp:</strong><br>
                    <textarea class="link-input" rows="3" readonly onclick="copyToClipboard(this)" title="Clicca per copiare">{{ whatsapp_msg }}</textarea>
                    <br><small>Clicca sul testo per copiarlo negli appunti</small>
                </div>
            </div>
        </body>
        </html>
        ''', steward=steward, pdf_url=pdf_url, full_pdf_url=full_pdf_url, whatsapp_url=whatsapp_url, mailto_url=mailto_url, whatsapp_msg=whatsapp_msg)
    
    # GET: mostra il form di selezione campi
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Esporta PDF Steward</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body { font-family: Arial, sans-serif; margin: 0; background: #f4f4f9; }
            .container { max-width: 600px; margin: 20px auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 5px 15px rgba(0,0,0,0.1); }
            .header { background: #667eea; color: white; padding: 15px 30px; text-align: center; font-size: 1.5em; margin: -30px -30px 30px -30px; border-radius: 10px 10px 0 0; }
            .form-group { margin-bottom: 15px; }
            .form-group label { display: block; margin-bottom: 5px; font-weight: bold; }
            .checkbox-group { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 10px; margin: 20px 0; }
            .checkbox-item { display: flex; align-items: center; gap: 8px; }
            .btn { padding: 12px 24px; background: #667eea; color: white; border: none; border-radius: 5px; cursor: pointer; text-decoration: none; display: inline-block; margin: 5px; }
            .btn-secondary { background: #6c757d; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">Esporta PDF Steward</div>
            
            <h2>{{ steward.nome }} {{ steward.cognome }}</h2>
            
            <form method="post">
                <div class="form-group">
                    <label>Seleziona i campi da includere nel PDF:</label>
                    <div class="checkbox-group">
                        {% for key, label in fields %}
                            <div class="checkbox-item">
                                <input type="checkbox" name="fields" value="{{ key }}" id="{{ key }}" {% if key in preselected %}checked{% endif %}>
                                <label for="{{ key }}">{{ label }}</label>
                            </div>
                        {% endfor %}
                    </div>
                </div>
                
                <button type="submit" class="btn">📄 Genera PDF</button>
                <a href="/stewards" class="btn btn-secondary">❌ Annulla</a>
            </form>
        </div>
    </body>
    </html>
    ''', steward=steward, fields=fields, preselected=preselected)

# 6. PAGINE SEGNAPOSTO
@app.route('/events', methods=['GET', 'POST'])
def events():
    if request.method == 'POST':
        # Creazione nuovo evento
        data_inizio_str = request.form.get('data_inizio')
        data_fine_str = request.form.get('data_fine')
        
        try:
            data_inizio = datetime.datetime.strptime(data_inizio_str, '%Y-%m-%dT%H:%M') if data_inizio_str else None
            data_fine = datetime.datetime.strptime(data_fine_str, '%Y-%m-%dT%H:%M') if data_fine_str else None
        except:
            flash('⚠️ Formato data non valido!', 'warning')
            return redirect(url_for('events'))
        
        if data_inizio and data_fine and data_fine < data_inizio:
            flash('⚠️ La data di fine deve essere successiva o uguale alla data di inizio!', 'warning')
            return redirect(url_for('events'))
        
        budget = request.form.get('budget')
        try:
            budget = float(budget) if budget else None
        except:
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
    
    # Eliminazione evento
    delete_id = request.args.get('delete')
    if delete_id and delete_id.isdigit():
        evento = Evento.query.get(int(delete_id))
        if evento:
            # Elimina anche le partecipazioni associate
            PartecipazioneEvento.query.filter_by(evento_id=evento.id).delete()
            db.session.delete(evento)
            db.session.commit()
            flash(f'🗑️ Evento "{evento.nome}" eliminato.', 'success')
            return redirect(url_for('events'))
    
    # Filtri
    search_query = request.args.get('search', '').strip().lower()
    stato_filter = request.args.get('stato', '')
    tipo_filter = request.args.get('tipo', '')
    data_da = request.args.get('data_da', '')
    data_a = request.args.get('data_a', '')
    
    # Query eventi con filtri
    eventi_query = Evento.query
    
    if search_query:
        eventi_query = eventi_query.filter(
            db.or_(
                Evento.nome.ilike(f'%{search_query}%'),
                Evento.descrizione.ilike(f'%{search_query}%'),
                Evento.luogo.ilike(f'%{search_query}%')
            )
        )
    
    if stato_filter:
        eventi_query = eventi_query.filter(Evento.stato == stato_filter)
    
    if tipo_filter:
        eventi_query = eventi_query.filter(Evento.tipo_evento == tipo_filter)
    
    if data_da:
        try:
            data_da_obj = datetime.datetime.strptime(data_da, '%Y-%m-%d') if data_da else None
            if data_da_obj:
                eventi_query = eventi_query.filter(Evento.data_inizio >= data_da_obj)
        except: pass
    
    if data_a:
        try:
            data_a_obj = datetime.datetime.strptime(data_a, '%Y-%m-%d') if data_a else None
            if data_a_obj:
                eventi_query = eventi_query.filter(Evento.data_fine <= data_a_obj)
        except: pass
    
    eventi = eventi_query.order_by(Evento.data_inizio.asc()).all()
    
    # Prepara i dati per la tabella
    eventi_data = []
    for e in eventi:
        # Conta partecipanti
        num_partecipanti = PartecipazioneEvento.query.filter_by(evento_id=e.id).count()
        
        # Determina colore stato
        stato_colors = {
            'pianificato': '#17a2b8',
            'in_corso': '#28a745', 
            'completato': '#6c757d',
            'cancellato': '#dc3545'
        }
        stato_color = stato_colors.get(e.stato, '#6c757d')
        
        eventi_data.append({
            'id': e.id,
            'nome': e.nome,
            'descrizione': e.descrizione,
            'data_inizio': e.data_inizio.strftime('%d/%m/%Y %H:%M'),
            'data_fine': e.data_fine.strftime('%d/%m/%Y %H:%M'),
            'luogo': e.luogo or '',
            'tipo_evento': e.tipo_evento or '',
            'stato': e.stato,
            'stato_color': stato_color,
            'budget': f'{e.budget:.2f} €' if e.budget else '',
            'num_partecipanti': num_partecipanti,
            'note': e.note or ''
        })
    
    # Prepara i messaggi flash
    flash_messages = []
    for c, m in get_flashed_messages(with_categories=True):
        icon = "✅" if c == "success" else "❌" if c == "error" else "⚠️"
        flash_messages.append({'category': c, 'message': m, 'icon': icon})
    
    # Form di ricerca e filtri
    search_html = render_template_string('''
    <form method="get" style="margin-bottom:20px;display:flex;flex-wrap:wrap;gap:10px;align-items:center;">
        <input type="text" name="search" placeholder="Cerca nome, descrizione, luogo" value="{{ search_value }}" style="padding:8px;border-radius:5px;border:1px solid #ccc;min-width:200px;">
        <select name="stato" style="padding:8px;border-radius:5px;border:1px solid #ccc;">
            <option value="">Tutti gli stati</option>
            <option value="pianificato" {{ 'selected' if stato_filter == 'pianificato' else '' }}>Pianificato</option>
            <option value="in_corso" {{ 'selected' if stato_filter == 'in_corso' else '' }}>In Corso</option>
            <option value="completato" {{ 'selected' if stato_filter == 'completato' else '' }}>Completato</option>
            <option value="cancellato" {{ 'selected' if stato_filter == 'cancellato' else '' }}>Cancellato</option>
        </select>
        <select name="tipo" style="padding:8px;border-radius:5px;border:1px solid #ccc;">
            <option value="">Tutti i tipi</option>
            <option value="Sportivo" {{ 'selected' if tipo_filter == 'Sportivo' else '' }}>Sportivo</option>
            <option value="Culturale" {{ 'selected' if tipo_filter == 'Culturale' else '' }}>Culturale</option>
            <option value="Musicale" {{ 'selected' if tipo_filter == 'Musicale' else '' }}>Musicale</option>
            <option value="Religioso" {{ 'selected' if tipo_filter == 'Religioso' else '' }}>Religioso</option>
            <option value="Altro" {{ 'selected' if tipo_filter == 'Altro' else '' }}>Altro</option>
        </select>
        <input type="date" name="data_da" placeholder="Data da" value="{{ data_da }}" style="padding:8px;border-radius:5px;border:1px solid #ccc;">
        <input type="date" name="data_a" placeholder="Data a" value="{{ data_a }}" style="padding:8px;border-radius:5px;border:1px solid #ccc;">
        <button type="submit" class="btn" style="background:#17a2b8;">🔍 Cerca/Filtra</button>
        <a href="/events" class="btn" style="background:#aaa;">Azzera</a>
    </form>
    ''', search_value=request.args.get('search',''), stato_filter=stato_filter, tipo_filter=tipo_filter, data_da=data_da, data_a=data_a)
    
    return render_template_string('''
    <!DOCTYPE html><html><head><title>Gestione Eventi</title><meta name="viewport" content="width=device-width, initial-scale=1.0"><style>body{font-family:Arial,sans-serif;margin:0;background:#f4f4f9}.header{background:#667eea;color:white;padding:15px 30px;text-align:center;font-size:1.5em;position:relative}.container{padding:30px;max-width:1400px;margin:auto}table{width:100%;border-collapse:collapse;margin-top:20px}th,td{padding:10px;border:1px solid #ddd;text-align:left}th{background:#667eea;color:white}tr:nth-child(even){background:#f9f9f9}.btn{background:#667eea;color:white;padding:8px 15px;border:none;border-radius:5px;text-decoration:none;cursor:pointer;margin:2px}.btn:hover{background:#5a6fd8}.btn-danger{background:#dc3545}.btn-success{background:#28a745}.btn-warning{background:#ffc107;color:#212529}.btn-info{background:#17a2b8}.flash-message{padding:10px;margin-bottom:10px;border-radius:6px;text-align:center;display:flex;align-items:center;gap:10px;font-weight:bold}.flash-success{background-color:#d4edda;color:#155724;border:1px solid #c3e6cb}.flash-error{background-color:#f8d7da;color:#721c24;border:1px solid #f5c6cb}.flash-warning{background-color:#fff3cd;color:#856404;border:1px solid #ffeeba}.form-row{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:20px}.form-row input,.form-row select,.form-row textarea{padding:8px;border-radius:5px;border:1px solid #ccc}.form-row textarea{resize:vertical;min-height:80px}.header-buttons{position:absolute;top:15px;right:30px}.header-buttons .btn{background:rgba(255,255,255,0.2);border:1px solid rgba(255,255,255,0.3)}.stato-badge{padding:4px 8px;border-radius:12px;color:white;font-size:0.8em;font-weight:bold}.event-actions{display:flex;flex-wrap:wrap;gap:5px}.event-actions .btn{font-size:0.8em;padding:4px 8px}</style></head><body><div class="header">Gestione Eventi<div class="header-buttons"><a href="/dashboard" class="btn">🏠 Dashboard</a></div></div><div class="container">{{ messages_html|safe }}{{ search_html|safe }}<form method="POST"><div class="form-row"><input type="text" name="nome" placeholder="Nome Evento *" required style="flex:2;"><input type="text" name="luogo" placeholder="Luogo" style="flex:1;"><select name="tipo_evento" style="flex:1;"><option value="">Tipo Evento</option><option value="Sportivo">Sportivo</option><option value="Culturale">Culturale</option><option value="Musicale">Musicale</option><option value="Religioso">Religioso</option><option value="Altro">Altro</option></select><select name="stato" style="flex:1;"><option value="pianificato">Pianificato</option><option value="in_corso">In Corso</option><option value="completato">Completato</option><option value="cancellato">Cancellato</option></select></div><div class="form-row"><input type="datetime-local" name="data_inizio" placeholder="Data Inizio *" required style="flex:1;"><input type="datetime-local" name="data_fine" placeholder="Data Fine *" required style="flex:1;"><input type="number" name="budget" placeholder="Budget (€)" step="0.01" style="flex:1;"></div><div class="form-row"><textarea name="descrizione" placeholder="Descrizione Evento" style="flex:2;"></textarea><textarea name="note" placeholder="Note" style="flex:1;"></textarea></div><button type="submit" class="btn">➕ Crea Evento</button></form><table><tr><th>Nome</th><th>Data Inizio</th><th>Data Fine</th><th>Luogo</th><th>Tipo</th><th>Stato</th><th>Budget</th><th>Partecipanti</th><th>Azioni</th></tr>{% for evento in eventi_data %}<tr><td><strong>{{ evento.nome }}</strong><br><small>{{ evento.descrizione[:50] }}{% if evento.descrizione|length > 50 %}...{% endif %}</small></td><td>{{ evento.data_inizio }}</td><td>{{ evento.data_fine }}</td><td>{{ evento.luogo }}</td><td>{{ evento.tipo_evento }}</td><td><span class="stato-badge" style="background-color:{{ evento.stato_color }};">{{ evento.stato|title }}</span></td><td>{{ evento.budget }}</td><td><span class="btn btn-info" style="background:#17a2b8;">{{ evento.num_partecipanti }}</span></td><td style="padding:8px;">
                    <div style="display:flex;gap:5px;flex-wrap:wrap;">
                        <a href="/event/{{ evento.id }}/edit" class="btn btn-info" style="font-size:0.7em;padding:4px 6px;">✏️</a>
                        <a href="/event/{{ evento.id }}/stewards" class="btn btn-success" style="font-size:0.7em;padding:4px 6px;">👥</a>
                        <a href="/event/{{ evento.id }}/delete" class="btn btn-danger" style="font-size:0.7em;padding:4px 6px;" onclick="return confirm('Eliminare questo evento?')">🗑️</a>
                    </div>
                </td></tr>{% endfor %}</table></div></body></html>
    ''', messages_html=''.join(f'<div class="flash-message flash-{m["category"]}"><span style="font-size:1.2em;">{m["icon"]}</span><span>{m["message"]}</span></div>' for m in flash_messages), search_html=search_html, eventi_data=eventi_data)

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
    # Simulazione autenticazione: username da sessione o query (da integrare con login reale)
    username = request.args.get('username', None)
    user = User.query.filter_by(username=username).first() if username else None
    is_admin = username == 'admin'  # Sostituire con logica reale

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
        movimenti = movimenti.all()

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
    username = request.args.get('username', None)
    user = User.query.filter_by(username=username).first() if username else None
    is_admin = username == 'admin'
    if is_admin:
        movimenti = MovimentoFinanziario.query.order_by(MovimentoFinanziario.data.asc()).all()
    else:
        steward = Steward.query.filter_by(email=username).first() if user else None
        movimenti = MovimentoFinanziario.query.filter_by(steward_id=steward.id).order_by(MovimentoFinanziario.data.asc()).all() if steward else []
    from collections import defaultdict
    saldo = 0
    saldo_per_data = []
    entrate_per_mese = defaultdict(float)
    uscite_per_mese = defaultdict(float)
    tipo_count = defaultdict(int)
    mesi_set = set()
    for m in movimenti:
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
    
    # Converti i dizionari in liste per Jinja2
    tipo_labels = list(tipo_count.keys())
    tipo_data = list(tipo_count.values())
    
    return render_template_string("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Dashboard Finanziaria</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
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
    
    if request.method == 'POST':
        steward_id = request.form.get('steward_id')
        ruolo = request.form.get('ruolo')
        numero_casacca = request.form.get('numero_casacca')
        
        if not steward_id or not ruolo:
            flash('⚠️ Seleziona uno steward e un ruolo!', 'warning')
            return redirect(url_for('event_stewards', evento_id=evento_id))
        
        # Controlla se lo steward è già assegnato
        existing = PartecipazioneEvento.query.filter_by(evento_id=evento_id, steward_id=steward_id).first()
        if existing:
            flash('⚠️ Questo steward è già assegnato a questo evento!', 'warning')
            return redirect(url_for('event_stewards', evento_id=evento_id))
        
        # Controlla se il numero di casacca è già assegnato
        if numero_casacca:
            existing_casacca = PartecipazioneEvento.query.filter_by(evento_id=evento_id, numero_casacca=numero_casacca).first()
            if existing_casacca:
                flash(f'⚠️ Il numero di casacca {numero_casacca} è già assegnato!', 'warning')
                return redirect(url_for('event_stewards', evento_id=evento_id))
        
        nuova_partecipazione = PartecipazioneEvento(
            evento_id=evento_id,
            steward_id=steward_id,
            ruolo=ruolo,
            numero_casacca=int(numero_casacca) if numero_casacca else None,
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
    <!DOCTYPE html><html><head><title>Gestione Steward Evento</title><meta name="viewport" content="width=device-width, initial-scale=1.0"><style>body{font-family:Arial,sans-serif;margin:0;background:#f4f4f9}.header{background:#667eea;color:white;padding:15px 30px;text-align:center;font-size:1.5em;position:relative}.container{padding:30px;max-width:1400px;margin:auto}.btn{background:#667eea;color:white;padding:8px 15px;border:none;border-radius:5px;text-decoration:none;cursor:pointer;margin:2px}.btn:hover{background:#5a6fd8}.btn-danger{background:#dc3545}.btn-success{background:#28a745}.btn-warning{background:#ffc107;color:#212529}.btn-info{background:#17a2b8}.flash-message{padding:10px;margin-bottom:10px;border-radius:6px;text-align:center;display:flex;align-items:center;gap:10px;font-weight:bold}.flash-success{background-color:#d4edda;color:#155724;border:1px solid #c3e6cb}.flash-error{background-color:#f8d7da;color:#721c24;border:1px solid #f5c6cb}.flash-warning{background-color:#fff3cd;color:#856404;border:1px solid #ffeeba}.form-row{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:20px}.form-row input,.form-row select,.form-row textarea{padding:8px;border-radius:5px;border:1px solid #ccc}.form-row textarea{resize:vertical;min-height:60px}.header-buttons{position:absolute;top:15px;right:30px}.header-buttons .btn{background:rgba(255,255,255,0.2);border:1px solid rgba(255,255,255,0.3)}.stato-badge{padding:4px 8px;border-radius:12px;color:white;font-size:0.8em;font-weight:bold}.event-info{background:#e9ecef;padding:15px;border-radius:8px;margin-bottom:20px}.event-info h3{margin-top:0}.two-columns{display:grid;grid-template-columns:1fr 1fr;gap:20px}@media (max-width:768px){.two-columns{grid-template-columns:1fr}}.export-buttons{margin:20px 0;text-align:center}.casacca-number{background:#007bff;color:white;padding:2px 6px;border-radius:10px;font-size:0.8em;font-weight:bold;margin-right:5px}.info-box{background:#e3f2fd;border-left:4px solid #2196f3;padding:10px;margin:10px 0;border-radius:5px}</style></head><body><div class="header">Gestione Steward - {{ evento.nome }}<div class="header-buttons"><a href="/events" class="btn">📋 Eventi</a><a href="/dashboard" class="btn">🏠 Dashboard</a></div></div><div class="container">{{ messages_html|safe }}{% if total_stewards == 0 %}<div class="info-box"><strong>ℹ️ Informazione:</strong> Non ci sono steward nel database. <a href="/stewards" style="color:#2196f3;text-decoration:underline;">Aggiungi prima alcuni steward</a> per poterli assegnare agli eventi.</div>{% else %}<div class="info-box"><strong>ℹ️ Informazione:</strong> {{ steward_disponibili|length }} steward disponibili su {{ total_stewards }} totali nel database.</div>{% endif %}<div class="event-info"><h3>📅 Informazioni Evento</h3><p><strong>Data:</strong> {{ evento.data_inizio.strftime('%d/%m/%Y %H:%M') }} - {{ evento.data_fine.strftime('%d/%m/%Y %H:%M') }}</p><p><strong>Luogo:</strong> {{ evento.luogo or 'Non specificato' }}</p><p><strong>Tipo:</strong> {{ evento.tipo_evento or 'Non specificato' }}</p><p><strong>Stato:</strong> <span class="stato-badge" style="background-color:{{ {'pianificato': '#17a2b8', 'in_corso': '#28a745', 'completato': '#6c757d', 'cancellato': '#dc3545'}[evento.stato] }};">{{ evento.stato|title }}</span></p></div><div class="export-buttons"><a href="/event/{{ evento.id }}/export_excel" class="btn btn-success">📊 Esporta Excel</a><a href="/event/{{ evento.id }}/whatsapp_sondaggio" class="btn btn-warning">📱 Messaggio Sondaggio</a><a href="/event/{{ evento.id }}/whatsapp_presenze" class="btn btn-info">👥 Messaggio Presenze</a></div><div class="two-columns"><div><h3>➕ Assegna Nuovo Steward</h3>{% if steward_disponibili %}<form method="POST"><div class="form-row"><select name="steward_id" required style="flex:2;"><option value="">Seleziona Steward</option>{% for steward in steward_disponibili %}<option value="{{ steward.id }}">{{ steward.nome }} {{ steward.cognome }} ({{ steward.email }})</option>{% endfor %}</select><select name="ruolo" required style="flex:1;"><option value="">Ruolo</option><option value="Capo Steward">Capo Steward</option><option value="Steward">Steward</option><option value="Supporto">Supporto</option><option value="Supervisore">Supervisore</option></select><input type="number" name="numero_casacca" placeholder="N° Casacca" min="1" style="flex:1;"></div><div class="form-row"><textarea name="note" placeholder="Note (opzionale)"></textarea></div><button type="submit" class="btn">➕ Assegna Steward</button></form>{% else %}<p style="color:#666;font-style:italic;">Tutti gli steward sono già assegnati a questo evento o non ci sono steward disponibili.</p>{% endif %}</div><div><h3>👥 Steward Assegnati ({{ partecipazioni|length }})</h3>{% if partecipazioni %}<table style="width:100%;border-collapse:collapse;margin-top:10px;"><tr style="background:#667eea;color:white;"><th style="padding:8px;text-align:left;">Casacca</th><th style="padding:8px;text-align:left;">Steward</th><th style="padding:8px;text-align:left;">Ruolo</th><th style="padding:8px;text-align:left;">Stato</th><th style="padding:8px;text-align:left;">Azioni</th></tr>{% for p in partecipazioni %}<tr style="border-bottom:1px solid #ddd;"><td style="padding:8px;">{% if p.numero_casacca %}<span class="casacca-number">{{ p.numero_casacca }}</span>{% else %}-{% endif %}</td><td style="padding:8px;">{{ p.steward.nome }} {{ p.steward.cognome }}<br><small>{{ p.steward.email }}</small></td><td style="padding:8px;">{{ p.ruolo }}</td><td style="padding:8px;"><span class="stato-badge" style="background-color:{{ {'assegnato': '#17a2b8', 'confermato': '#28a745', 'rifiutato': '#dc3545', 'completato': '#6c757d'}[p.stato] }};">{{ p.stato|title }}</span></td><td style="padding:8px;"><div style="display:flex;gap:5px;flex-wrap:wrap;">{% if p.stato == 'assegnato' %}<a href="/event/{{ evento.id }}/stewards?update={{ p.id }}&status=confermato" class="btn btn-success" style="font-size:0.7em;padding:4px 6px;">✅</a><a href="/event/{{ evento.id }}/stewards?update={{ p.id }}&status=rifiutato" class="btn btn-danger" style="font-size:0.7em;padding:4px 6px;">❌</a>{% elif p.stato == 'confermato' %}<a href="/event/{{ evento.id }}/stewards?update={{ p.id }}&status=completato" class="btn btn-info" style="font-size:0.7em;padding:4px 6px;">✅</a>{% endif %}<a href="/event/{{ evento.id }}/stewards?remove={{ p.id }}" class="btn btn-danger" style="font-size:0.7em;padding:4px 6px;" onclick="return confirm('Rimuovere questo steward?')">🗑️</a></div></td></tr>{% endfor %}</table>{% else %}<p style="color:#666;font-style:italic;">Nessuno steward assegnato.</p>{% endif %}</div></div></div></body></html>
    ''', messages_html=''.join(f'<div class="flash-message flash-{m["category"]}"><span style="font-size:1.2em;">{m["icon"]}</span><span>{m["message"]}</span></div>' for m in flash_messages), evento=evento, steward_disponibili=steward_disponibili, partecipazioni=partecipazioni, total_stewards=total_stewards)

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
    os.makedirs(uploads_dir, exist_ok=True)
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
    
    # Prepara il messaggio per le presenze
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
        casacca = f" #{p.numero_casacca}" if p.numero_casacca else ""
        stato_emoji = {"assegnato": "⏳", "confermato": "✅", "rifiutato": "❌", "completato": "🏁"}
        messaggio += f"{stato_emoji.get(p.stato, '❓')} {p.steward.nome} {p.steward.cognome}{casacca} - {p.ruolo}\n"
    
    messaggio += f"""

📊 *Riepilogo:*
• Totale assegnati: {len(partecipazioni)}
• Confermati: {len([p for p in partecipazioni if p.stato == 'confermato'])}
• Rifiutati: {len([p for p in partecipazioni if p.stato == 'rifiutato'])}
• Completati: {len([p for p in partecipazioni if p.stato == 'completato'])}

📱 *Link per aggiornamenti:* [Clicca qui per aggiornare presenze]

---
*Messaggio generato automaticamente da StewardApp*"""
    
    # Codifica il messaggio per WhatsApp
    import urllib.parse
    encoded_message = urllib.parse.quote(messaggio)
    whatsapp_url = f"https://wa.me/?text={encoded_message}"
    
    return render_template_string('''
    <!DOCTYPE html><html><head><title>Messaggio Presenze WhatsApp</title><meta name="viewport" content="width=device-width, initial-scale=1.0"><style>body{font-family:Arial,sans-serif;margin:0;background:#f4f4f9}.header{background:#25d366;color:white;padding:15px 30px;text-align:center;font-size:1.5em}.container{padding:30px;max-width:800px;margin:auto}.btn{background:#25d366;color:white;padding:15px 30px;border:none;border-radius:8px;text-decoration:none;cursor:pointer;font-size:1.1em;margin:10px;display:inline-block}.btn:hover{background:#128c7e}.message-preview{background:white;padding:20px;border-radius:8px;margin:20px 0;border-left:4px solid #25d366;white-space:pre-wrap;font-family:monospace;max-height:400px;overflow-y:auto}.copy-btn{background:#667eea;color:white;padding:8px 15px;border:none;border-radius:5px;cursor:pointer;margin-left:10px}.copy-btn:hover{background:#5a6fd8}.back-btn{background:#6c757d;color:white;padding:10px 20px;border:none;border-radius:5px;text-decoration:none;display:inline-block;margin-top:20px}</style></head><body><div class="header">👥 Messaggio Presenze WhatsApp</div><div class="container"><h2>Lista Presenze per {{ evento.nome }}</h2><div class="message-preview">{{ messaggio }}</div><div style="text-align:center;margin:30px 0;"><a href="{{ whatsapp_url }}" target="_blank" class="btn">📱 Apri WhatsApp</a><button onclick="copyToClipboard('{{ messaggio }}')" class="copy-btn">📋 Copia Messaggio</button></div><a href="/event/{{ evento.id }}/stewards" class="back-btn">← Torna alla Gestione Steward</a></div><script>function copyToClipboard(text) {navigator.clipboard.writeText(text).then(function() {alert('Messaggio copiato negli appunti!');}).catch(function(err) {console.error('Errore nella copia: ', err);});}</script></body></html>
    ''', evento=evento, messaggio=messaggio, whatsapp_url=whatsapp_url)

# 7. SISTEMA DI NOTIFICHE AUTOMATICHE PER EVENTI IMMINENTI
@app.route('/notifiche_eventi')
def notifiche_eventi():
    # Eventi che iniziano nelle prossime 24 ore
    ora_attuale = datetime.datetime.now()
    domani = ora_attuale + datetime.timedelta(days=1)
    
    eventi_imminenti = Evento.query.filter(
        Evento.data_inizio >= ora_attuale,
        Evento.data_inizio <= domani,
        Evento.stato == 'pianificato'
    ).all()
    
    # Eventi che iniziano nelle prossime ore (entro 6 ore)
    prossime_ore = ora_attuale + datetime.timedelta(hours=6)
    eventi_urgenti = Evento.query.filter(
        Evento.data_inizio >= ora_attuale,
        Evento.data_inizio <= prossime_ore,
        Evento.stato == 'pianificato'
    ).all()
    
    # Eventi senza steward assegnati
    eventi_senza_steward = []
    for evento in Evento.query.filter_by(stato='pianificato').all():
        if not evento.partecipazioni:
            eventi_senza_steward.append(evento)
    
    return render_template_string('''
    <!DOCTYPE html><html><head><title>Notifiche Eventi</title><meta name="viewport" content="width=device-width, initial-scale=1.0"><style>body{font-family:Arial,sans-serif;margin:0;background:#f4f4f9}.header{background:#dc3545;color:white;padding:15px 30px;text-align:center;font-size:1.5em;position:relative}.container{padding:30px;max-width:1200px;margin:auto}.btn{background:#667eea;color:white;padding:8px 15px;border:none;border-radius:5px;text-decoration:none;cursor:pointer;margin:2px}.btn:hover{background:#5a6fd8}.btn-danger{background:#dc3545}.btn-success{background:#28a745}.btn-warning{background:#ffc107;color:#212529}.btn-info{background:#17a2b8}.header-buttons{position:absolute;top:15px;right:30px}.header-buttons .btn{background:rgba(255,255,255,0.2);border:1px solid rgba(255,255,255,0.3)}.notification-section{margin-bottom:30px;background:white;border-radius:8px;padding:20px;box-shadow:0 2px 4px rgba(0,0,0,0.1)}.notification-section h3{margin-top:0;color:#333}.event-card{background:#f8f9fa;border-left:4px solid #dc3545;padding:15px;margin:10px 0;border-radius:5px}.event-card.urgent{border-left-color:#dc3545;background:#fff5f5}.event-card.warning{border-left-color:#ffc107;background:#fffbf0}.event-card.info{border-left-color:#17a2b8;background:#f0f8ff}.event-card h4{margin:0 0 10px 0;color:#333}.event-card p{margin:5px 0;color:#666}.event-actions{display:flex;gap:5px;margin-top:10px;flex-wrap:wrap}.event-actions .btn{font-size:0.8em;padding:4px 8px}.no-events{color:#666;font-style:italic;text-align:center;padding:20px}</style></head><body><div class="header">🚨 Notifiche Eventi<div class="header-buttons"><a href="/dashboard" class="btn">🏠 Dashboard</a><a href="/events" class="btn">📋 Eventi</a></div></div><div class="container"><div class="notification-section"><h3>🚨 Eventi Urgenti (entro 6 ore) - {{ eventi_urgenti|length }}</h3>{% if eventi_urgenti %}{% for evento in eventi_urgenti %}<div class="event-card urgent"><h4>🏆 {{ evento.nome }}</h4><p><strong>⏰ Inizio:</strong> {{ evento.data_inizio.strftime('%d/%m/%Y %H:%M') }}</p><p><strong>📍 Luogo:</strong> {{ evento.luogo or 'Non specificato' }}</p><p><strong>👥 Steward:</strong> {{ evento.partecipazioni|length }} assegnati</p><div class="event-actions"><a href="/event/{{ evento.id }}/stewards" class="btn btn-success">👥 Gestisci Steward</a><a href="/event/{{ evento.id }}/whatsapp_sondaggio" class="btn btn-warning">📱 Sondaggio</a><a href="/event/{{ evento.id }}/whatsapp_presenze" class="btn btn-info">👥 Presenze</a></div></div>{% endfor %}{% else %}<p class="no-events">Nessun evento urgente.</p>{% endif %}</div><div class="notification-section"><h3>⚠️ Eventi Imminenti (entro 24 ore) - {{ eventi_imminenti|length }}</h3>{% if eventi_imminenti %}{% for evento in eventi_imminenti %}{% if evento not in eventi_urgenti %}<div class="event-card warning"><h4>🏆 {{ evento.nome }}</h4><p><strong>⏰ Inizio:</strong> {{ evento.data_inizio.strftime('%d/%m/%Y %H:%M') }}</p><p><strong>📍 Luogo:</strong> {{ evento.luogo or 'Non specificato' }}</p><p><strong>👥 Steward:</strong> {{ evento.partecipazioni|length }} assegnati</p><div class="event-actions"><a href="/event/{{ evento.id }}/stewards" class="btn btn-success">👥 Gestisci Steward</a><a href="/event/{{ evento.id }}/whatsapp_sondaggio" class="btn btn-warning">📱 Sondaggio</a><a href="/event/{{ evento.id }}/whatsapp_presenze" class="btn btn-info">👥 Presenze</a></div></div>{% endif %}{% endfor %}{% else %}<p class="no-events">Nessun evento imminente.</p>{% endif %}</div><div class="notification-section"><h3>ℹ️ Eventi Senza Steward - {{ eventi_senza_steward|length }}</h3>{% if eventi_senza_steward %}{% for evento in eventi_senza_steward %}<div class="event-card info"><h4>🏆 {{ evento.nome }}</h4><p><strong>⏰ Inizio:</strong> {{ evento.data_inizio.strftime('%d/%m/%Y %H:%M') }}</p><p><strong>📍 Luogo:</strong> {{ evento.luogo or 'Non specificato' }}</p><p><strong>⚠️ Nessuno steward assegnato!</strong></p><div class="event-actions"><a href="/event/{{ evento.id }}/stewards" class="btn btn-success">👥 Assegna Steward</a><a href="/event/{{ evento.id }}/edit" class="btn btn-info">✏️ Modifica</a></div></div>{% endfor %}{% else %}<p class="no-events">Tutti gli eventi hanno steward assegnati.</p>{% endif %}</div></div></body></html>
    ''', eventi_urgenti=eventi_urgenti, eventi_imminenti=eventi_imminenti, eventi_senza_steward=eventi_senza_steward)

@app.route('/event/<int:evento_id>/edit', methods=['GET', 'POST'])
def edit_event(evento_id):
    evento = Evento.query.get_or_404(evento_id)
    
    if request.method == 'POST':
        # Aggiorna i dati dell'evento
        data_inizio_str = request.form.get('data_inizio')
        data_fine_str = request.form.get('data_fine')
        
        try:
            data_inizio = datetime.datetime.strptime(data_inizio_str, '%Y-%m-%dT%H:%M') if data_inizio_str else None
            data_fine = datetime.datetime.strptime(data_fine_str, '%Y-%m-%dT%H:%M') if data_fine_str else None
        except:
            flash('⚠️ Formato data non valido!', 'warning')
            return redirect(url_for('edit_event', evento_id=evento_id))
        
        if data_inizio and data_fine and data_fine < data_inizio:
            flash('⚠️ La data di fine deve essere successiva o uguale alla data di inizio!', 'warning')
            return redirect(url_for('edit_event', evento_id=evento_id))
        
        budget = request.form.get('budget')
        try:
            budget = float(budget) if budget else None
        except:
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
        evento.updated_at = datetime.datetime.utcnow()
        
        db.session.commit()
        flash(f'✅ Evento "{evento.nome}" aggiornato con successo!', 'success')
        return redirect(url_for('events'))
    
    # Form di modifica
    form_html = f'''
        <form method="POST">
            <div class="form-row">
                <input type="text" name="nome" placeholder="Nome Evento *" value="{evento.nome}" required style="flex:2;">
                <input type="text" name="luogo" placeholder="Luogo" value="{evento.luogo or ''}" style="flex:1;">
                <select name="tipo_evento" style="flex:1;">
                    <option value="">Tipo Evento</option>
                    <option value="Sportivo" {'selected' if evento.tipo_evento == 'Sportivo' else ''}>Sportivo</option>
                    <option value="Culturale" {'selected' if evento.tipo_evento == 'Culturale' else ''}>Culturale</option>
                    <option value="Musicale" {'selected' if evento.tipo_evento == 'Musicale' else ''}>Musicale</option>
                    <option value="Religioso" {'selected' if evento.tipo_evento == 'Religioso' else ''}>Religioso</option>
                    <option value="Altro" {'selected' if evento.tipo_evento == 'Altro' else ''}>Altro</option>
                </select>
                <select name="stato" style="flex:1;">
                    <option value="pianificato" {'selected' if evento.stato == 'pianificato' else ''}>Pianificato</option>
                    <option value="in_corso" {'selected' if evento.stato == 'in_corso' else ''}>In Corso</option>
                    <option value="completato" {'selected' if evento.stato == 'completato' else ''}>Completato</option>
                    <option value="cancellato" {'selected' if evento.stato == 'cancellato' else ''}>Cancellato</option>
                </select>
            </div>
            <div class="form-row">
                <input type="datetime-local" name="data_inizio" placeholder="Data Inizio *" value="{evento.data_inizio.strftime('%Y-%m-%dT%H:%M')}" required style="flex:1;">
                <input type="datetime-local" name="data_fine" placeholder="Data Fine *" value="{evento.data_fine.strftime('%Y-%m-%dT%H:%M')}" required style="flex:1;">
                <input type="number" name="budget" placeholder="Budget (€)" step="0.01" value="{evento.budget or ''}" style="flex:1;">
            </div>
            <div class="form-row">
                <textarea name="descrizione" placeholder="Descrizione Evento" style="flex:2;">{evento.descrizione or ''}</textarea>
                <textarea name="note" placeholder="Note" style="flex:1;">{evento.note or ''}</textarea>
            </div>
            <button type="submit" class="btn">💾 Salva Modifiche</button>
        </form>
    '''
    
    messages_html = ''.join(f'<div class="flash-message flash-{c}"><span style="font-size:1.2em;">{"✅" if c == "success" else "❌" if c == "error" else "⚠️"}</span><span>{m}</span></div>' for c, m in get_flashed_messages(with_categories=True))
    
    return render_template('edit_event.html', evento=evento)

@app.route('/event/<int:evento_id>/delete')
def delete_event(evento_id):
    evento = Evento.query.get_or_404(evento_id)
    # Elimina anche le partecipazioni associate
    PartecipazioneEvento.query.filter_by(evento_id=evento.id).delete()
    db.session.delete(evento)
    db.session.commit()
    flash(f'🗑️ Evento "{evento.nome}" eliminato.', 'success')
    return redirect(url_for('events'))

@app.route('/logout')
def logout():
    session.clear()
    flash('Logout effettuato con successo!', 'success')
    return redirect(url_for('login'))

@app.route('/esporta_eventi')
def esporta_eventi():
    formato = request.args.get('formato', 'pdf')
    filtro = request.args.get('filtro', 'annuale')
    mese = request.args.get('mese')
    evento_id = request.args.get('evento_id')

    # Filtra eventi in base ai parametri (qui esempio base: tutti gli eventi)
    eventi = Evento.query.order_by(Evento.data_inizio.asc()).all()

    if formato == 'excel':
        import pandas as pd
        import tempfile
        data = []
        for e in eventi:
            data.append({
                'Nome': e.nome,
                'Data Inizio': e.data_inizio.strftime('%d/%m/%Y %H:%M'),
                'Data Fine': e.data_fine.strftime('%d/%m/%Y %H:%M'),
                'Luogo': e.luogo,
                'Tipo': e.tipo_evento,
                'Stato': e.stato,
            })
        df = pd.DataFrame(data)
        with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as tmp:
            with pd.ExcelWriter(tmp.name, engine='openpyxl') as writer:
                df.to_excel(writer, index=False)
            tmp.seek(0)
            output = io.BytesIO(tmp.read())
        output.seek(0)
        return send_file(output, as_attachment=True, download_name='elenco_eventi.xlsx', mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

    elif formato == 'pdf':
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        buffer = io.BytesIO()
        p = canvas.Canvas(buffer, pagesize=A4)
        y = 800
        p.setFont("Helvetica-Bold", 14)
        p.drawString(40, y, "Elenco Eventi")
        y -= 30
        p.setFont("Helvetica", 10)
        for e in eventi:
            line = f"{e.nome} | {e.data_inizio.strftime('%d/%m/%Y %H:%M')} - {e.data_fine.strftime('%d/%m/%Y %H:%M')} | {e.luogo} | {e.tipo_evento} | {e.stato}"
            p.drawString(40, y, line)
            y -= 18
            if y < 50:
                p.showPage()
                y = 800
        p.save()
        buffer.seek(0)
        return send_file(buffer, as_attachment=True, download_name='elenco_eventi.pdf', mimetype='application/pdf')

    else:
        return "Formato non supportato", 400

# 8. ESECUZIONE
if __name__ == '__main__':
    app.run(debug=True, port=5001)