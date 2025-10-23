from werkzeug.security import generate_password_hash

# Genera gli hash per ogni utente
admin_hash = generate_password_hash('japlab', method='pbkdf2:sha256')
autista_hash = generate_password_hash('driverpass', method='pbkdf2:sha256')
boxer_hash = generate_password_hash('boxer', method='pbkdf2:sha256')
expert_hash = generate_password_hash('expert', method='pbkdf2:sha256')
preparatore_hash = generate_password_hash('pickerpass', method='pbkdf2:sha256')

# Stampa i risultati
print(f"Admin: {admin_hash}")
print(f"Autista (generico): {autista_hash}")
print(f"Boxer: {boxer_hash}")
print(f"Expert: {expert_hash}")
print(f"Preparatore: {preparatore_hash}")