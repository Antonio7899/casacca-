import random
from faker import Faker
from app import app, db, Steward, Evento, PartecipazioneEvento, User, MovimentoFinanziario
from datetime import datetime, timedelta

fake = Faker('it_IT')

def create_dummy_data():
    with app.app_context():
        # Pulisci i dati esistenti
        db.session.query(PartecipazioneEvento).delete()
        db.session.query(Evento).delete()
        db.session.query(Steward).delete()
        db.session.query(MovimentoFinanziario).delete()
        db.session.commit()

        # Crea 10 steward
        stewards = []
        for i in range(10):
            steward = Steward(
                nome=fake.first_name(),
                cognome=fake.last_name(),
                email=fake.unique.email(),
                phone=fake.phone_number(),
                address=fake.address(),
                tax_code=fake.unique.ssn(),
                iban=fake.iban(),
                document_type='Carta d\'Identità',
                document_number=fake.random_number(digits=9, fix_len=True),
                document_expiry=fake.date_between(start_date='+1y', end_date='+5y'),
                experience='Nessuna',
                carta_identita_path='uploads/placeholder.pdf',
                codice_fiscale_path='uploads/placeholder.pdf',
                attestato_path='uploads/placeholder.pdf',
                autocertificazione_path='uploads/placeholder.pdf',
                patente_path='uploads/placeholder.pdf'
            )
            stewards.append(steward)
            db.session.add(steward)
        
        db.session.commit()

        # Crea un evento di calcio
        soccer_event = Evento(
            nome="Partita di Calcio: Squadra A vs Squadra B",
            descrizione="Finale di coppa.",
            data_inizio=datetime.now() + timedelta(days=7),
            data_fine=datetime.now() + timedelta(days=7, hours=3),
            luogo="Stadio Comunale",
            tipo_evento="Sportivo",
            stato="Pianificato",
            budget=5000.00,
            note="Richiesti 10 steward per controllo accessi."
        )
        db.session.add(soccer_event)
        db.session.commit()

        # Assegna gli steward all'evento
        for steward in stewards:
            partecipazione = PartecipazioneEvento(
                evento_id=soccer_event.id,
                steward_id=steward.id,
                ruolo="Controllo Accessi",
                stato="Invitato"
            )
            db.session.add(partecipazione)
            
        db.session.commit()
        print("Dati di simulazione creati con successo: 10 steward e 1 evento di calcio.")

        # Crea evento di esempio solo se non esiste già
        if Evento.query.count() == 0:
            evento = Evento(
                nome='Concerto di prova',
                descrizione='Evento di esempio generato automaticamente',
                data_inizio=datetime.now() + timedelta(days=2),
                data_fine=datetime.now() + timedelta(days=2, hours=4),
                luogo='Piazza Centrale',
                tipo_evento='Musicale',
                stato='pianificato',
                budget=1000.0,
                note='Evento di test'
            )
            db.session.add(evento)
            db.session.commit()
            print('Evento di esempio creato!')
        else:
            print('Eventi già presenti, nessun evento creato.')

        # Aggiungi movimenti solo se non esistono già
        if MovimentoFinanziario.query.count() < 5:
            steward = Steward.query.first()
            if not steward:
                steward = Steward(
                    nome='Mario', cognome='Rossi', email='mario.rossi@example.com', phone='1234567890',
                    address='Via Roma 1', tax_code='RSSMRA80A01H501U', iban='IT60X0542811101000000123456',
                    document_type='Carta d\'Identità', document_number='AB1234567',
                    document_expiry=datetime.now().date(), experience='Nessuna',
                    carta_identita_path='', codice_fiscale_path='', attestato_path='', autocertificazione_path='', patente_path=''
                )
                db.session.add(steward)
                db.session.commit()
            today = datetime.now().date()
            movs = [
                MovimentoFinanziario(
                    steward_id=steward.id,
                    data=today - timedelta(days=30),
                    descrizione='Contributo Comune',
                    importo=500.0,
                    tipo='entrata',
                    note='Esempio di entrata'
                ),
                MovimentoFinanziario(
                    steward_id=steward.id,
                    data=today - timedelta(days=20),
                    descrizione='Pagamento steward',
                    importo=100.0,
                    tipo='uscita',
                    note='Esempio di uscita'
                ),
                MovimentoFinanziario(
                    steward_id=steward.id,
                    data=today - timedelta(days=10),
                    descrizione='Sponsorizzazione',
                    importo=300.0,
                    tipo='entrata',
                    note='Sponsor locale'
                ),
                MovimentoFinanziario(
                    steward_id=steward.id,
                    data=today - timedelta(days=5),
                    descrizione='Acquisto materiale',
                    importo=50.0,
                    tipo='uscita',
                    note='Materiale evento'
                ),
                MovimentoFinanziario(
                    steward_id=steward.id,
                    data=today,
                    descrizione='Donazione',
                    importo=200.0,
                    tipo='entrata',
                    note='Donazione privata'
                ),
            ]
            for m in movs:
                db.session.add(m)
            db.session.commit()
            print('Movimenti di esempio creati!')
        else:
            print('Movimenti già presenti, nessun movimento creato.')

if __name__ == '__main__':
    create_dummy_data() 