from app import app, db, MovimentoFinanziario, Steward, Evento

with app.app_context():
    movimenti = MovimentoFinanziario.query.all()
    print(f"Totale movimenti trovati: {len(movimenti)}")
    for m in movimenti:
        steward = Steward.query.get(m.steward_id)
        evento = Evento.query.get(m.evento_id) if m.evento_id else None
        print(f"ID: {m.id} | Data: {m.data} | Importo: {m.importo} | Tipo: {m.tipo} | Steward: {steward.nome if steward else 'N/A'} {steward.cognome if steward else ''} | Evento: {evento.nome if evento else 'N/A'} (ID: {m.evento_id}) | Descrizione: {m.descrizione} | Pagato: {m.pagato}") 