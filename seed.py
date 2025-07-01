import random
from faker import Faker
from app import app, db, Steward, Evento, PartecipazioneEvento, User
from datetime import datetime, timedelta

fake = Faker('it_IT')

def create_dummy_data():
    with app.app_context():
        # Pulisci i dati esistenti
        db.session.query(PartecipazioneEvento).delete()
        db.session.query(Evento).delete()
        db.session.query(Steward).delete()
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

if __name__ == '__main__':
    create_dummy_data() 