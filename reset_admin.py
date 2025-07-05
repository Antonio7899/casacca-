from app import app, db, User
from werkzeug.security import generate_password_hash

with app.app_context():
    # Elimina eventuali utenti admin duplicati
    for u in User.query.filter_by(username='admin').all():
        db.session.delete(u)
    db.session.commit()

    # Crea nuovo utente admin
    admin = User(username='admin', password_hash=generate_password_hash('admin123'))
    db.session.add(admin)
    db.session.commit()
    print('Admin creato/reset con successo. Username: admin, Password: admin123') 