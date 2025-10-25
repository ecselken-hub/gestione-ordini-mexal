from flask import Flask, render_template, request, redirect, url_for, flash, Response, jsonify, send_from_directory
from mexal_api import ( # Importa funzioni specifiche
    mx_call_api, get_vettori, get_shipping_address, get_dati_aggiuntivi,
    get_payment_methods, search_articles, get_article_price, find_article_code_by_alt_code, 
    search_articles_by_code, get_article_details, update_article_alt_code, get_all_clients,
    get_all_shipping_addresses
)
import time
import os
from dotenv import load_dotenv # Importa per caricare .env
import googlemaps
from datetime import datetime, timedelta
from collections import OrderedDict, defaultdict
import math
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired
from werkzeug.security import generate_password_hash, check_password_hash
import json
from flask_sqlalchemy import SQLAlchemy
from pywebpush import webpush, WebPushException
import threading 

# Carica variabili d'ambiente da .env (se esiste)
load_dotenv()

app = Flask(__name__)

# --- CORREZIONE 7: Raccomandazione per SECRET_KEY ---
# NOTA: Per produzione, sposta SECRET_KEY in una variabile d'ambiente!
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', 'uqwyeuiqyieqwwquye') # Usa env var se presente, altrimenti default

# Configurazione Database SQLAlchemy (OK)
render_disk_path = os.environ.get('RENDER_DISK_PATH')
if render_disk_path:
    db_path = os.path.join(render_disk_path, 'notifications.db')
    print(f"Ambiente Render. Percorso DB: {db_path}")
else:
    instance_path = app.instance_path
    db_path = os.path.join(instance_path, 'local.db')
    try:
        os.makedirs(instance_path, exist_ok=True)
        print(f"Ambiente Locale. Percorso DB: {db_path}")
    except OSError as e:
        print(f"Errore creando la cartella instance: {e}")
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False # Disabilita warning
db = SQLAlchemy(app)

# Configurazione Notifiche Push (OK, ma assicurati che le chiavi env siano impostate)
VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY")
VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY")
VAPID_CLAIM_EMAIL = os.getenv("VAPID_CLAIM_EMAIL", "mailto:ecsel.ken@gmail.com") # Default se non impostato

# Configurazione Flask-Login (OK)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = "Effettua il login per accedere a questa pagina."
login_manager.login_message_category = "info"

# --- Database Utenti Semplificato (OK per ora) ---
# NOTA: Genera hash sicuri per le password reali! Esempio:
# from werkzeug.security import generate_password_hash
# print(generate_password_hash('tua_password_sicura', method='pbkdf2:sha256'))
users_db = {
    # SOSTITUISCI QUESTI HASH CON QUELLI GENERATI PER LE TUE PASSWORD REALI
    "admin": {"password_hash": "pbkdf2:sha256:1000000$qBPEiQk6vnH5HOvC$d122ce9a1504f922597b344551d3686bbceea7399df5bfed87ff99a4e708e855", "roles": ["admin"]}, # Esempio: password 'adminpass'
    "autista": {"password_hash": "pbkdf2:sha256:1000000$y7INoNA89V5aXVqX$21863e95fd82ea2b73defb775f4b987e7a9b66ea4e536185b1504813a83", "roles": ["autista"]}, # Esempio: password 'driverpass'
    "boxer": {"password_hash": "pbkdf2:sha256:1000000$x6OFUZcMP7Qp77f4$1b0a9c69a97acaecab99359ac4566f0c2dcd3eeb1d115d870fb2975f3810272", "roles": ["autista"], "nome_autista": "BOXER"}, # Esempio: password 'boxerpass'
    "expert": {"password_hash": "pbkdf2:sha256:1000000$kheELNvGyCnYdLL8$ec03d3ba28ef3db220844a5da0d3b71b48b5b2b9c312125e07c90d7fc5470451", "roles": ["autista"], "nome_autista": "EXPERT"}, # Esempio: password 'expertpass'
    "preparatore": {"password_hash": "pbkdf2:sha256:1000000$aMf8iIqOtKzKxwWu$223306f4b9f72d534fe1928eaaec69c0bae6ca2c19836cdb54a8e115e7565ddf", "roles": ["preparatore"]}, # Esempio: password 'pickerpass'
    "antonio": {"password_hash": "pbkdf2:sha256:1000000$cnsUw4MBXg3htnhw$66d5ea591c79f0985ddc17c62bbb4b27ecd1a63a72ab5ed4f9b6d996bf46be3a", "roles": ["admin"]} # Esempio hash per 'antoniopass'
}

class User(UserMixin):
    """Classe utente per Flask-Login."""
    def __init__(self, id, roles, nome_autista=None):
        self.id = id
        self.roles = roles if isinstance(roles, list) else [] # Assicura sia una lista
        self.nome_autista = nome_autista

    def has_role(self, role):
        return role in self.roles

@login_manager.user_loader
def load_user(user_id):
    """Carica utente dalla 'sessione' (qui dal dizionario users_db)."""
    user_data = users_db.get(user_id)
    if user_data:
        return User(id=user_id, roles=user_data.get('roles', []), nome_autista=user_data.get('nome_autista'))
    return None

class LoginForm(FlaskForm):
    """Form di login."""
    username = StringField('Username', validators=[DataRequired("L'username è obbligatorio.")])
    password = PasswordField('Password', validators=[DataRequired("La password è obbligatoria.")])
    submit = SubmitField('Accedi')

# --- Rotte Login/Logout (OK) ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('todo_list'))
    form = LoginForm()
    if form.validate_on_submit():
        user_data = users_db.get(form.username.data)
        if user_data and check_password_hash(user_data.get('password_hash', ''), form.password.data):
            user_obj = User(id=form.username.data, roles=user_data.get('roles', []), nome_autista=user_data.get('nome_autista'))
            login_user(user_obj) # Registra l'utente come loggato
            flash('Login effettuato con successo.', 'success')
            next_page = request.args.get('next')
            # Semplice controllo per evitare redirect a siti esterni
            if next_page and next_page.startswith('/'):
                 return redirect(next_page)
            else:
                 return redirect(url_for('todo_list'))
        else:
            flash('Username o password non validi.', 'danger')
    return render_template('login.html', form=form)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logout effettuato con successo.', 'success')
    return redirect(url_for('login'))

class TodoItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    # user_id = db.Column(db.String(80), nullable=False, index=True) # ASSICURATI SIA RIMOSSO O COMMENTATO
    created_by = db.Column(db.String(80), nullable=True, index=True) # DEVE ESSERE PRESENTE
    description = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    is_completed = db.Column(db.Boolean, default=False, nullable=False)
    completed_at = db.Column(db.DateTime, nullable=True)
    completed_by = db.Column(db.String(80), nullable=True) # DEVE ESSERE PRESENTE

    def __repr__(self):
        status = "Completato" if self.is_completed else "Da fare"
        creator = self.created_by or "Sconosciuto"
        return f'<Todo {self.id} [{status}] - By: {creator}>'

# --- Modello DB PushSubscription (OK) ---
class PushSubscription(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(50), nullable=False, index=True) # Aggiunto index
    subscription_json = db.Column(db.Text, nullable=False)
    # Potresti aggiungere un timestamp di creazione/aggiornamento
    # created_at = db.Column(db.DateTime, default=datetime.utcnow)

# --- Rotte Service Worker & VAPID Key (OK) ---
@app.route('/sw.js')
def service_worker():
    # Assicurati che 'static/sw.js' esista
    return send_from_directory('static', 'sw.js', mimetype='application/javascript')

@app.route('/vapid-public-key')
@login_required
def get_vapid_public_key():
    if not VAPID_PUBLIC_KEY:
         print("Errore: VAPID_PUBLIC_KEY non configurato sul server.")
         flash("Errore di configurazione notifiche sul server.", "danger")
         return jsonify({'error': 'VAPID public key not configured'}), 500
    return jsonify({'public_key': VAPID_PUBLIC_KEY})

# --- Salvataggio Sottoscrizione Push (OK) ---
@app.route('/save-subscription', methods=['POST'])
@login_required
def save_subscription():
    subscription_data = request.json
    if not subscription_data or not isinstance(subscription_data, dict):
        print(f"Errore save_subscription: Dati non validi ricevuti da {current_user.id}")
        return jsonify({'error': 'Invalid or missing subscription data'}), 400

    user_id = current_user.id
    try:
        # Normalizza/Ordina le chiavi per confronto univoco
        subscription_json_str = json.dumps(subscription_data, sort_keys=True)
    except TypeError:
        print(f"Errore save_subscription: Impossibile serializzare dati da {current_user.id}")
        return jsonify({'error': 'Cannot serialize subscription data'}), 400

    try:
        existing_sub = PushSubscription.query.filter_by(
            user_id=user_id,
            subscription_json=subscription_json_str
        ).first()

        if not existing_sub:
            new_sub = PushSubscription(
                user_id=user_id,
                subscription_json=subscription_json_str
            )
            db.session.add(new_sub)
            db.session.commit()
            print(f"Nuova sottoscrizione push salvata per l'utente {user_id}")
        else:
            print(f"Sottoscrizione push già esistente per l'utente {user_id}")
        return jsonify({'success': True})

    except Exception as e:
        db.session.rollback()
        print(f"Errore DB durante salvataggio sottoscrizione per {user_id}: {e}")
        return jsonify({'error': 'Database error occurred'}), 500

# --- Invio Notifiche Push (OK) ---
def send_push_notification(user_id, title, body):
    """Invia notifiche push a un utente specifico."""
    if not VAPID_PRIVATE_KEY or not VAPID_PUBLIC_KEY:
        print(f"Errore Invio Notifica: Chiavi VAPID non configurate per {user_id}")
        return

    # Recupera sottoscrizioni valide dal DB
    try:
        subscriptions = PushSubscription.query.filter_by(user_id=user_id).all()
    except Exception as e:
        print(f"Errore DB leggendo sottoscrizioni per {user_id}: {e}")
        return

    if not subscriptions:
        print(f"Nessuna sottoscrizione push trovata per l'utente {user_id}")
        return

    payload = json.dumps({"title": title, "body": body})
    vapid_claims = {"sub": VAPID_CLAIM_EMAIL}

    print(f"Tentativo invio {len(subscriptions)} notifiche a {user_id}...")
    success_count = 0
    failure_count = 0

    for sub in subscriptions:
        try:
            subscription_info = json.loads(sub.subscription_json)
            webpush(
                subscription_info=subscription_info,
                data=payload,
                vapid_private_key=VAPID_PRIVATE_KEY,
                vapid_claims=vapid_claims
            )
            success_count += 1
        except WebPushException as ex:
            failure_count += 1
            print(f"Errore WebPush per {user_id}: {ex}")
            # Se la sottoscrizione non è più valida (Gone o NotFound), rimuovila dal DB
            if ex.response and ex.response.status_code in [404, 410]:
                print(f"Rimozione sottoscrizione scaduta (status {ex.response.status_code}) per {user_id}")
                try:
                    db.session.delete(sub)
                    db.session.commit()
                except Exception as db_err:
                     db.session.rollback()
                     print(f"Errore DB durante rimozione sottoscrizione per {user_id}: {db_err}")
            # Altri errori potrebbero essere temporanei (es. 429 Too Many Requests)
        except json.JSONDecodeError:
            failure_count += 1
            print(f"Errore: Sottoscrizione corrotta nel DB per {user_id} (ID: {sub.id}). Rimuovere manualmente?")
        except Exception as e:
            failure_count += 1
            print(f"Errore inaspettato inviando notifica a {user_id}: {e}")

    print(f"Invio notifiche completato per {user_id}: {success_count} successi, {failure_count} fallimenti.")

# --- CORREZIONE 1: Stato Globale Protetto da Lock ---
# NOTA: Questa è una soluzione TEMPORANEA e non ideale per produzione.
# Un database per 'statuses', 'logistics', 'delivery_events', 'calculated_routes', 'driver_notes'
# sarebbe più robusto e scalabile.
app_data_store_lock = threading.Lock()
app_data_store = {
    "orders": {}, # Cache degli ordini da API
    "statuses": {}, # Stato locale (Da Lavorare, In Picking, etc.) - Chiave: numero ordine (str)
    "logistics": {}, # Assegnazione vettore - Chiave: order_key (str), Valore: dict {codice, nome}
    "delivery_events": {}, # Orari start/end consegna - Chiave: order_key (str)
    "calculated_routes": {}, # Percorsi calcolati - Chiave: nome_autista (str)
    "driver_notes": {}, # Note per autista - Chiave: order_key (str)
    "last_load_time": None # Timestamp ultimo caricamento da API
}
def get_initial_status():
    """Restituisce lo stato iniziale per un nuovo ordine."""
    return {'status': 'Da Lavorare', 'picked_items': {}, 'colli_totali_operatore': 0}

# --- Funzione Caricamento Dati (con Lock e Error Handling) ---
# --- CORREZIONE 4: Aggiunto commento su scalabilità ---
def load_all_data():
    """
    Carica (o ricarica) dati da API Mexal, dando priorità
    all'indirizzo di spedizione specifico dell'ordine. CORRETTO
    """
    # Rimuoviamo l'invalidazione forzata della cache
    # with app_data_store_lock:
    #    if "orders" in app_data_store:
    #        print("DEBUG: Invalidazione forzata cache ordini...")
    #        app_data_store["orders"] = {}

    with app_data_store_lock:
        if app_data_store.get("orders"):
            print("Dati già presenti in cache.")
            return list(app_data_store["orders"].values())
        else:
            print("Cache ordini vuota, procedo al caricamento dall'API...")

    print("--- Inizio caricamento di massa dei dati dall'API (con priorità indirizzi spedizione) ---")

    # ... (Caricamento clienti, pagamenti, ordini, righe - INVARIATO) ...
    # 1. Carica Clienti
    clients_response = mx_call_api('risorse/clienti/ricerca', method='POST', data={'filtri': []})
    if not clients_response or not isinstance(clients_response.get('dati'), list): print("Errore CRITICO: Impossibile caricare i dati clienti."); flash("Errore nel recupero dei dati clienti.", "danger"); return None
    client_map = {client['codice']: client for client in clients_response['dati'] if 'codice' in client}
    print(f"Caricati {len(client_map)} clienti.")
    # 2. Carica Metodi Pagamento
    payment_map = get_payment_methods()
    if not payment_map: flash("Attenzione: Non è stato possibile caricare i metodi di pagamento.", "warning"); payment_map = {}
    print(f"Caricati {len(payment_map)} metodi di pagamento.")
    # 3. Carica Testate Ordini
    orders_response = mx_call_api('risorse/documenti/ordini-clienti/ricerca', method='POST', data={'filtri': []})
    if not orders_response or not isinstance(orders_response.get('dati'), list): print("Errore CRITICO: Impossibile caricare gli ordini."); flash("Errore nel recupero degli ordini.", "danger"); return None
    orders = orders_response['dati']
    print(f"Caricate {len(orders)} testate ordini.")
    # 4. Carica Righe Ordini
    rows_response = mx_call_api('risorse/documenti/ordini-clienti/righe/ricerca', method='POST', data={'filtri': []})
    rows_map = defaultdict(list)
    if rows_response and isinstance(rows_response.get('dati'), list):
        row_count = 0
        for row in rows_response['dati']:
            sigla = row.get('sigla', '?'); serie = row.get('serie', '?'); numero = row.get('numero', '?')
            if sigla != '?' and serie != '?' and numero != '?': rows_map[f"{sigla}:{serie}:{numero}"].append(row); row_count += 1
        print(f"Caricate {row_count} righe ordini.")
    else: print("Attenzione: Non è stato possibile caricare le righe degli ordini."); flash("Attenzione: Errore caricamento righe.", "warning")


    # 5. Assembla i dati
    new_orders_data = {}
    new_statuses_data = {} # Mantiene stati esistenti se l'ordine c'era già
    print("Inizio assemblaggio dati ordini con priorità indirizzi spedizione...")
    processed_count = 0
    address_fetch_errors = 0
    specific_address_used_count = 0

    for order in orders:
        sigla = order.get('sigla', '?'); serie = order.get('serie', '?'); numero = order.get('numero', '?')
        order_key = f"{sigla}:{serie}:{numero}"
        order_id_str = str(numero) if numero != '?' else None
        if not order_id_str: continue

        client_code = order.get('cod_conto')
        client_data = client_map.get(client_code, {})

        order['ragione_sociale'] = client_data.get('ragione_sociale', 'N/D')
        order['telefono'] = client_data.get('telefono', 'N/D')

        # --- LOGICA INDIRIZZO CON DEBUG AGGIUNTIVO ---
        shipping_address_id = order.get('cod_anag_sped')
        # Inizializza con valori anagrafica
        effective_address = client_data.get('indirizzo', 'N/D')
        effective_locality = client_data.get('localita', 'N/D')
        effective_cap = client_data.get('cap', '')
        effective_provincia = client_data.get('provincia', '')
        effective_telefono = order['telefono']
        shipping_details_source = "Anagrafica Cliente"

        # Stampa valori iniziali PRIMA del check indirizzo specifico
        print(f"--- Processing Ordine {order_key} (Cliente: {client_code}) ---")
        print(f"  Anagrafica Cliente -> Indirizzo: '{effective_address}', Località: '{effective_locality}'")
        print(f"  Ordine -> cod_anag_sped: {shipping_address_id}")

        if shipping_address_id:
            print(f"  Tentativo recupero indirizzo spedizione ID: {shipping_address_id}...")
            shipping_address_data = get_shipping_address(shipping_address_id) # Chiama API

            # Logga ESATTAMENTE cosa restituisce get_shipping_address
            print(f"  Risultato get_shipping_address({shipping_address_id}): {shipping_address_data}")

            if shipping_address_data and isinstance(shipping_address_data, dict):
                addr_sped = shipping_address_data.get('indirizzo') # Può essere None o ''
                loc_sped = shipping_address_data.get('localita') # Può essere None o ''

                # Logga i valori estratti dall'indirizzo specifico
                print(f"  Indirizzo Sped. Estratto -> Indirizzo: '{addr_sped}', Località: '{loc_sped}'")

                # CONTROLLO: Usa indirizzo specifico SE ENTRAMBI sono presenti e non vuoti
                if addr_sped and loc_sped: # Check if both are truthy (not None, not empty string)
                    print(f"  CONDIZIONE SODDISFATTA: Uso indirizzo specifico.")
                    effective_address = addr_sped
                    effective_locality = loc_sped
                    effective_cap = shipping_address_data.get('cap', effective_cap)
                    effective_provincia = shipping_address_data.get('provincia', effective_provincia)
                    effective_telefono = shipping_address_data.get('telefono1', effective_telefono)
                    shipping_details_source = f"Indirizzo Sped. ID: {shipping_address_id}"
                    specific_address_used_count += 1
                else:
                    print(f"  CONDIZIONE NON SODDISFATTA: Indirizzo specifico incompleto. Mantengo anagrafica.")
                    address_fetch_errors += 1 # Conta come errore se l'ID c'era ma i dati erano incompleti
            else:
                print(f"  Fallito recupero o formato non valido per indirizzo spedizione {shipping_address_id}. Mantengo anagrafica.")
                address_fetch_errors += 1
        else:
            print("  Nessun cod_anag_sped specificato. Uso anagrafica.")

        # Salva i valori EFFETTIVI finali
        order['indirizzo_effettivo'] = effective_address
        order['localita_effettiva'] = effective_locality
        order['cap_effettivo'] = effective_cap
        order['provincia_effettiva'] = effective_provincia
        order['telefono_effettivo'] = effective_telefono
        order['fonte_indirizzo'] = shipping_details_source

        # Logga i valori finali assegnati all'ordine
        print(f"  Valori FINALI assegnati all'ordine {order_key}:")
        print(f"    indirizzo_effettivo: '{order['indirizzo_effettivo']}'")
        print(f"    localita_effettiva: '{order['localita_effettiva']}'")
        print(f"    fonte_indirizzo: '{order['fonte_indirizzo']}'")
        print(f"--- Fine Processing Ordine {order_key} ---")
        # --- FINE LOGICA INDIRIZZO ---

        # ... (assemblaggio resto dati ordine: dati aggiuntivi, note, righe - INVARIATO) ...
        dati_aggiuntivi = get_dati_aggiuntivi(client_code); order['orario1_start'] = dati_aggiuntivi.get('orario1start'); order['orario1_end'] = dati_aggiuntivi.get('orario1end')
        order['nota'] = order.get('nota', ''); order['pagamento_desc'] = payment_map.get(order.get('id_pagamento'), 'N/D')
        order['righe'] = rows_map.get(order_key, [])

        new_orders_data[order_key] = order

        # Gestione stato (INVARIATO)
        with app_data_store_lock:
            if order_id_str not in app_data_store.get("statuses", {}): app_data_store.setdefault("statuses", {})[order_id_str] = get_initial_status()
            if order_id_str not in new_statuses_data: new_statuses_data[order_id_str] = app_data_store.get("statuses", {}).get(order_id_str, get_initial_status())
        processed_count += 1


    # Aggiorna store globale (INVARIATO)
    with app_data_store_lock:
        app_data_store["orders"] = new_orders_data
        # Assicurati stato per ogni ordine caricato
        for order_obj in new_orders_data.values():
            id_str = str(order_obj.get('numero'))
            if id_str and id_str not in app_data_store.get("statuses", {}):
                 app_data_store.setdefault("statuses", {})[id_str] = get_initial_status()

        app_data_store["last_load_time"] = datetime.now()
        print(f"--- Caricamento completato. {processed_count} ordini in cache. Usati {specific_address_used_count} indirizzi sped. specifici ({address_fetch_errors} errori). ---")
        if address_fetch_errors > 0:
             flash(f"Attenzione: Impossibile recuperare o validare {address_fetch_errors} indirizzi di spedizione. Usato indirizzo cliente.", "warning")
        return list(app_data_store["orders"].values())


# --- Rotte Principali (con Lock e Error Handling) ---

@app.route('/')
@login_required
def dashboard():
    """Reindirizza l'utente alla pagina appropriata in base al ruolo."""
    if current_user.has_role('admin'):
        return redirect(url_for('ordini_list'))
    elif current_user.has_role('preparatore'):
        return redirect(url_for('ordini_list'))
    elif current_user.has_role('autista'):
        # Se l'autista ha un nome specifico associato, va alla sua pagina consegne
        if current_user.nome_autista:
            return redirect(url_for('consegne_autista', autista_nome=current_user.nome_autista))
        else:
            # Altrimenti potrebbe andare a una pagina generica per autisti o dashboard
            flash("Profilo autista non completamente configurato (nome mancante).", "warning")
            return redirect(url_for('autisti')) # Pagina elenco autisti/giri
    else:
        # Ruolo non gestito o mancante
        flash("Ruolo utente non definito o non autorizzato.", "danger")
        logout_user() # Effettua il logout per sicurezza
        return redirect(url_for('login'))
    
@app.route('/ordini')
@login_required
def ordini_list():
    """Mostra l'elenco degli ordini, raggruppati per data."""
    if not (current_user.has_role('admin') or current_user.has_role('preparatore')):
        flash("Accesso non autorizzato alla lista ordini.", "danger")
        return redirect(url_for('dashboard'))

    orders_list_copy = load_all_data() # Ottiene una copia dei dati correnti (o None)

    if orders_list_copy is None:
        # Errore API critico, messaggio già mostrato da load_all_data
        return render_template('orders.html', ordini_per_data=OrderedDict(), giorno_selezionato=None, active_page='ordini', enable_polling=False)

    giorno_filtro = request.args.get('giorno_filtro')
    filtered_orders = []

    if giorno_filtro:
        try:
            # Formato atteso: YYYYMMDD, filtra per giorno finale
            giorno_da_cercare = giorno_filtro.strip().zfill(2)
            if not giorno_da_cercare.isdigit() or len(giorno_da_cercare) != 2:
                raise ValueError("Formato giorno non valido.")

            filtered_orders = [
                order for order in orders_list_copy
                if isinstance(order.get('data_documento'), str) and len(order['data_documento']) == 8 and order['data_documento'].endswith(giorno_da_cercare)
            ]
            if not filtered_orders:
                 flash(f"Nessun ordine trovato per il giorno '{giorno_filtro}'.", "info")

        except ValueError as e:
            flash(f"Filtro giorno non valido: {e}. Mostro tutti gli ordini.", "warning")
            filtered_orders = orders_list_copy
    else:
        filtered_orders = orders_list_copy

    # Ordina per data documento (stringa YYYYMMDD), decrescente
    filtered_orders.sort(key=lambda order: order.get('data_documento', '0'), reverse=True)

    ordini_per_data = OrderedDict()
    # Usa il lock SOLO per leggere lo stato corrente di ogni ordine
    with app_data_store_lock:
        statuses_copy = dict(app_data_store["statuses"]) # Copia stati sotto lock

    for order in filtered_orders:
        order_id = str(order.get('numero'))
        if not order_id: continue # Salta ordini senza numero

        # Leggi stato dalla copia
        order['local_status'] = statuses_copy.get(order_id, {}).get('status', 'Da Lavorare')

        # Formattazione data (YYYYMMDD -> DD/MM/YYYY)
        date_str = order.get('data_documento')
        data_formattata = "Data Sconosciuta"
        if isinstance(date_str, str) and len(date_str) == 8:
             try:
                data_formattata = f"{date_str[6:8]}/{date_str[4:6]}/{date_str[0:4]}"
             except IndexError: pass # Lascia "Data Sconosciuta"
        order['data_formattata'] = data_formattata

        ordini_per_data.setdefault(data_formattata, []).append(order)

    return render_template('orders.html', ordini_per_data=ordini_per_data, giorno_selezionato=giorno_filtro, active_page='ordini', enable_polling=True)


@app.route('/trasporto')
@login_required
def trasporto():
    """Pagina per l'assegnazione dei vettori agli ordini."""
    # ... (controllo permessi iniziale invariato) ...
    if not current_user.has_role('admin'):
        flash("Accesso non autorizzato.", "danger")
        return redirect(url_for('dashboard'))

    orders_list_copy = load_all_data() # Ora contiene indirizzo_effettivo, localita_effettiva
    if orders_list_copy is None:
        return render_template('trasporto.html', ordini_per_data=OrderedDict(), vettori=[], active_page='trasporto', enable_polling=False)

    vettori = get_vettori()
    if not vettori:
        flash("Attenzione: Errore nel caricamento dei vettori.", "warning")
        vettori = []
    vettori_map = {v['codice']: v.get('ragione_sociale') or v.get('descrizione', 'N/D') for v in vettori if 'codice' in v}

    ordini_per_data = OrderedDict()
    orders_list_copy.sort(key=lambda order: order.get('data_documento', '0'), reverse=True)

    with app_data_store_lock:
        logistics_copy = dict(app_data_store.get("logistics", {}))
        driver_notes_copy = dict(app_data_store.get("driver_notes", {}))
        # Assicura formato {codice, nome} in logistics (AGGIORNA SULLO STORE REALE)
        for key, value in logistics_copy.items():
            if isinstance(value, str):
                app_data_store["logistics"][key] = {'codice': value, 'nome': vettori_map.get(value, 'Sconosciuto')}
            elif not isinstance(value, dict) or 'codice' not in value or 'nome' not in value:
                 if key in app_data_store["logistics"]: del app_data_store["logistics"][key]
        logistics_copy = dict(app_data_store["logistics"]) # Rileggi aggiornato


    for order in orders_list_copy: # order ora ha indirizzo_effettivo
        order_key = f"{order.get('sigla','?')}:{order.get('serie','?')}:{order.get('numero','?')}"
        logistic_info = logistics_copy.get(order_key)
        order['vettore_assegnato_info'] = logistic_info
        order['nota_autista'] = driver_notes_copy.get(order_key, '')

        # Formattazione data (invariata)
        date_str = order.get('data_documento')
        data_formattata = "Data Sconosciuta"
        if isinstance(date_str, str) and len(date_str) == 8:
             try: data_formattata = f"{date_str[6:8]}/{date_str[4:6]}/{date_str[0:4]}"
             except IndexError: pass
        order['data_formattata'] = data_formattata

        ordini_per_data.setdefault(data_formattata, []).append(order)
        # NOTA: Assicurati che il template 'trasporto.html' mostri
        #       order.indirizzo_effettivo e order.localita_effettiva

    return render_template('trasporto.html', ordini_per_data=ordini_per_data, vettori=vettori, active_page='trasporto', enable_polling=True)


# --- Polling Route (con Lock e Error Handling) ---
# --- CORREZIONE 6: Aggiunto commento su polling ---
@app.route('/check-updates')
@login_required
def check_updates():
    """
    Controlla se ci sono state modifiche su Mexal dall'ultimo caricamento.
    Se rileva modifiche, invalida la cache locale forzando un ricaricamento.

    NOTA: Questo approccio invalida TUTTA la cache. Un'ottimizzazione
    sarebbe recuperare solo i dati modificati e aggiornare la cache
    in modo granulare (se l'API lo supporta).
    """
    with app_data_store_lock: # Leggi last_load_time in modo sicuro
        last_load = app_data_store.get("last_load_time")

    if not last_load or not isinstance(last_load, datetime):
        print("Polling: Dati mai caricati o timestamp non valido, forzo aggiornamento.")
        # Non serve invalidare, load_all_data lo farà
        return jsonify({'new_data': True})

    try:
        last_load_str = last_load.strftime('%Y%m%d %H%M%S')
    except Exception as e:
        print(f"Polling: Errore formattazione last_load_time ({last_load}): {e}. Forzo aggiornamento.")
        with app_data_store_lock: # Invalida cache in caso di errore timestamp
            app_data_store["orders"] = {}
            app_data_store["last_load_time"] = None
        return jsonify({'new_data': True})

    # Filtri API per data ultima modifica (usa 'filtri' minuscolo)
    search_data = {
        'filtri': [
            # NOTA: Assicurati che 'data_ult_mod' sia il campo corretto
            # e che l'operatore '>' funzioni come atteso nell'API Mexal.
            {'campo': 'data_ult_mod', 'condizione': '>', 'valore': last_load_str}
        ]
    }

    print(f"Polling: Verifico aggiornamenti da {last_load_str}...")
    updates_testate = mx_call_api('risorse/documenti/ordini-clienti/ricerca', method='POST', data=search_data)
    updates_righe = mx_call_api('risorse/documenti/ordini-clienti/righe/ricerca', method='POST', data=search_data)

    # Controlla se le chiamate API sono fallite
    if updates_testate is None or updates_righe is None:
         print("Polling: Errore durante la chiamata API per verifica aggiornamenti.")
         # Non invalidare la cache per errori API temporanei
         return jsonify({'new_data': False, 'error': 'API check failed'})

    # Controlla se ci sono dati ('dati' è una lista)
    if (isinstance(updates_testate.get('dati'), list) and updates_testate['dati']) or \
       (isinstance(updates_righe.get('dati'), list) and updates_righe['dati']):
        print("Polling: Rilevati aggiornamenti da Mexal. Invalido la cache locale.")
        with app_data_store_lock: # Invalida cache sotto lock
            app_data_store["orders"] = {}
            app_data_store["last_load_time"] = None
        return jsonify({'new_data': True})
    else:
        print(f"Polling: Nessun aggiornamento rilevato da Mexal dopo {last_load_str}.")
        return jsonify({'new_data': False})

# --- Salvataggio Assegnazioni (con Lock) ---
@app.route('/assign_all_vettori', methods=['POST'])
@login_required
def assign_all_vettori():
    """Salva le assegnazioni vettore e le note autista dal form /trasporto."""
    if not current_user.has_role('admin'):
        flash("Accesso non autorizzato.", "danger")
        return redirect(url_for('dashboard'))

    vettori = get_vettori() # Ricarica vettori per mappare codice a nome aggiornato
    if vettori is None: # Errore API vettori
        flash("Errore nel recupero dei vettori, impossibile salvare le assegnazioni.", "danger")
        return redirect(url_for('trasporto'))
    vettori_map = {v['codice']: v.get('ragione_sociale') or v.get('descrizione', 'Sconosciuto') for v in vettori if 'codice' in v}

    updated_logistics = 0
    updated_notes = 0
    # Modifica lo store sotto lock
    with app_data_store_lock:
        # Crea copie per confronto e pulizia
        current_logistics = dict(app_data_store.get("logistics", {}))
        current_notes = dict(app_data_store.get("driver_notes", {}))
        processed_orders = set() # Tiene traccia degli ordini nel form

        for key, value in request.form.items():
            if key.startswith('vettore_'):
                order_key = key.replace('vettore_', '')
                processed_orders.add(order_key)
                vettore_codice = value.strip()
                new_logistic_info = None
                if vettore_codice:
                    new_logistic_info = {
                        'codice': vettore_codice,
                        'nome': vettori_map.get(vettore_codice, 'Sconosciuto')
                    }

                # Aggiorna solo se cambiato o se prima non c'era
                if current_logistics.get(order_key) != new_logistic_info:
                    if new_logistic_info:
                        app_data_store["logistics"][order_key] = new_logistic_info
                        updated_logistics += 1
                    elif order_key in app_data_store["logistics"]: # Rimuovi se deselezionato
                        del app_data_store["logistics"][order_key]
                        updated_logistics += 1 # Conta anche le rimozioni

            elif key.startswith('nota_autista_'):
                order_key = key.replace('nota_autista_', '')
                processed_orders.add(order_key)
                nota_autista = value.strip()

                if current_notes.get(order_key, '') != nota_autista:
                    if nota_autista:
                        app_data_store["driver_notes"][order_key] = nota_autista
                        updated_notes += 1
                    elif order_key in app_data_store["driver_notes"]: # Rimuovi se vuota
                        del app_data_store["driver_notes"][order_key]
                        updated_notes += 1 # Conta rimozioni

        # Pulisci assegnazioni/note per ordini non più presenti nel form (potrebbe non essere necessario)
        # keys_to_remove_log = set(current_logistics.keys()) - processed_orders
        # for k in keys_to_remove_log: del app_data_store["logistics"][k]
        # keys_to_remove_notes = set(current_notes.keys()) - processed_orders
        # for k in keys_to_remove_notes: del app_data_store["driver_notes"][k]

    flash(f"Salvataggio completato. Aggiornate {updated_logistics} assegnazioni e {updated_notes} note.", "success")
    return redirect(url_for('trasporto'))


@app.route('/calcola-giri')
@login_required
def calcola_giri():
    """Calcola i percorsi ottimizzati usando l'indirizzo effettivo."""
    if not current_user.has_role('admin'):
        flash("Accesso non autorizzato.", "danger")
        return redirect(url_for('dashboard'))

    # --- AGGIUNTA LOG INIZIALE ---
    print("\n--- DEBUG: Avvio /calcola-giri ---")
    # --- FINE AGGIUNTA ---

    with app_data_store_lock:
        logistics_copy = dict(app_data_store.get("logistics", {}))
        orders_copy = dict(app_data_store.get("orders", {})) # Leggi cache ordini CORRENTE
        calculated_routes_temp = {}
        # Pulizia percorsi precedenti (importante)
        app_data_store["calculated_routes"] = {}
        print(f"DEBUG [calcola_giri]: Letti {len(orders_copy)} ordini dalla cache per il calcolo.")


    # 1. Raggruppa ordini per vettore
    giri_per_vettore = defaultdict(list)
    print("DEBUG [calcola_giri]: Raggruppamento ordini per vettore...")
    for order_key, logistic_info in logistics_copy.items():
        if isinstance(logistic_info, dict) and 'nome' in logistic_info:
            vettore_nome = logistic_info.get('nome', 'Sconosciuto')
            if vettore_nome != 'Sconosciuto':
                ordine_completo = orders_copy.get(order_key)
                if ordine_completo:
                    ordine_completo['_order_key'] = order_key # Aggiungi chiave per riferimento futuro
                    giri_per_vettore[vettore_nome].append(ordine_completo)
                    # --- AGGIUNTA LOG INDIRIZZO QUI ---
                    print(f"  + Ordine {order_key} assegnato a {vettore_nome}. Indirizzo effettivo letto: '{ordine_completo.get('indirizzo_effettivo')}', Località: '{ordine_completo.get('localita_effettiva')}', Fonte: '{ordine_completo.get('fonte_indirizzo')}'")
                    # --- FINE AGGIUNTA ---
                # else: print(f"WARN [calcola_giri]: Ordine {order_key} non trovato nella cache orders.")
        # else: print(f"WARN [calcola_giri]: Info logistiche non valide per {order_key}: {logistic_info}")

    if not giri_per_vettore:
        flash("Nessun ordine assegnato ai vettori.", "info")
        print("DEBUG [calcola_giri]: Nessun ordine da processare.")
        return redirect(url_for('autisti'))

    # 2. Inizializza Google Maps Client (invariato)
    google_api_key = os.getenv('GOOGLE_MAPS_API_KEY')
    # ... (controllo google_api_key e inizializzazione gmaps invariati) ...
    if not google_api_key:
        flash("Errore: Chiave API Google Maps non configurata.", "danger"); return redirect(url_for('autisti'))
    try: gmaps = googlemaps.Client(key=google_api_key)
    except Exception as e: flash(f"Errore inizializzazione Google Maps: {e}", "danger"); return redirect(url_for('autisti'))


    # 3. Calcola percorso per ogni vettore
    origin = os.getenv('GMAPS_ORIGIN', "Japlab, Via Ferraris, 3, 84018 Scafati SA")
    default_stop_time_min = int(os.getenv('DEFAULT_STOP_TIME_MIN', '10'))
    total_calculated = 0; total_errors = 0

    print("DEBUG [calcola_giri]: Inizio ciclo calcolo percorsi...")
    for vettore, ordini_assegnati in giri_per_vettore.items():
        if not ordini_assegnati: continue

        waypoints = []
        valid_orders_for_route = [] # Lista degli OGGETTI ordine validi per questo giro
        print(f"\nDEBUG [calcola_giri]: Preparo waypoints per {vettore}...")
        for o in ordini_assegnati:
            # Usa indirizzo_effettivo e localita_effettiva LETTI PRIMA
            addr = o.get('indirizzo_effettivo', '').strip()
            loc = o.get('localita_effettiva', '').strip()

            # --- LOG VERIFICA INDIRIZZO PRIMA DI AGGIUNGERE WAYPOINT ---
            print(f"  - Controllo Ordine #{o.get('numero')}: Indirizzo='{addr}', Località='{loc}', Fonte='{o.get('fonte_indirizzo')}'")
            # --- FINE LOG VERIFICA ---

            if addr and loc:
                waypoint_str = f"{addr}, {loc}"
                waypoints.append(waypoint_str)
                valid_orders_for_route.append(o) # Aggiungi l'OGGETTO ordine
                print(f"    -> Waypoint VALIDO aggiunto: '{waypoint_str}'")
            else:
                print(f"    -> Waypoint NON VALIDO. Ordine escluso.")
                flash(f"Ordine #{o.get('numero')} per {vettore} escluso dal calcolo: indirizzo/località mancante.", "warning")

        if not waypoints:
            print(f"WARN [calcola_giri]: Nessun waypoint valido trovato per {vettore}. Giro non calcolato.")
            continue

        partenza_prevista = datetime.now().replace(hour=8, minute=0, second=0, microsecond=0)

        try:
            print(f"DEBUG [calcola_giri]: Chiamata Google Maps API per {vettore}...")
            directions_result = gmaps.directions(
                origin=origin, destination=origin, waypoints=waypoints,
                optimize_waypoints=True, mode="driving",
            )
            # ... (Gestione risposta directions_result invariata) ...
            if not directions_result or not isinstance(directions_result, list) or not directions_result[0].get('legs'):
                raise ValueError("Risposta API Google Maps non valida o vuota.")

            route = directions_result[0]
            google_waypoint_order_indices = route.get('waypoint_order', [])
            # --- VERIFICA COSTRUZIONE tappe_ordinate_oggetti ---
            # Assicurati che valid_orders_for_route contenga gli oggetti ordine CORRETTI
            print(f"DEBUG [calcola_giri]: Ordine waypoint Google: {google_waypoint_order_indices}")
            print(f"DEBUG [calcola_giri]: Numero ordini validi per il giro: {len(valid_orders_for_route)}")
            tappe_ordinate_oggetti = []
            for index in google_waypoint_order_indices:
                 if 0 <= index < len(valid_orders_for_route):
                     tappa_obj = valid_orders_for_route[index]
                     # --- LOG INDIRIZZO SALVATO NELLA TAPPA ---
                     print(f"  -> Aggiungo Tappa (index {index}): Ordine #{tappa_obj.get('numero')}, Indirizzo Eff: '{tappa_obj.get('indirizzo_effettivo')}', Fonte: '{tappa_obj.get('fonte_indirizzo')}'")
                     # --- FINE LOG ---
                     tappe_ordinate_oggetti.append(tappa_obj) # Aggiungi l'oggetto ordine così com'è
                 else:
                     print(f"ERRORE [calcola_giri]: Indice waypoint {index} non valido!")
            # --- FINE VERIFICA ---

            # ... (Calcolo distanze, tempi, orari previsti - invariato) ...
            distanza_complessiva_m = sum(leg.get('distance', {}).get('value', 0) for leg in route['legs'])
            durata_guida_sec = sum(leg.get('duration', {}).get('value', 0) for leg in route['legs'])
            tempo_soste_sec = len(tappe_ordinate_oggetti) * default_stop_time_min * 60
            durata_totale_stimata_sec = durata_guida_sec + tempo_soste_sec
            rientro_previsto = partenza_prevista + timedelta(seconds=durata_totale_stimata_sec)

            orario_tappa_corrente = partenza_prevista
            for i, tappa_obj in enumerate(tappe_ordinate_oggetti): # Itera sugli oggetti ordine GIA' ORDINATI
                if i < len(route['legs']):
                    leg_duration_sec = route['legs'][i].get('duration', {}).get('value', 0)
                    orario_tappa_corrente += timedelta(seconds=leg_duration_sec)
                    tappa_obj['orario_previsto'] = orario_tappa_corrente.strftime('%H:%M') # AGGIUNGI orario all'oggetto ordine
                    orario_tappa_corrente += timedelta(minutes=default_stop_time_min)
                else:
                    tappa_obj['orario_previsto'] = "Rientro"


            # Salva il giro (usa la lista tappe_ordinate_oggetti che contiene gli oggetti ordine arricchiti)
            calculated_routes_temp[vettore] = {
                'data': datetime.now().strftime('%d/%m/%Y'),
                'partenza_stimata': partenza_prevista.strftime('%H:%M'),
                'num_consegne': len(tappe_ordinate_oggetti),
                'km_previsti': f"{distanza_complessiva_m / 1000:.1f} km",
                'tempo_guida_stimato': time.strftime("%Hh %Mm", time.gmtime(durata_guida_sec)),
                'tempo_soste_stimato': time.strftime("%Hh %Mm", time.gmtime(tempo_soste_sec)),
                'tempo_totale_stimato': time.strftime("%Hh %Mm", time.gmtime(durata_totale_stimata_sec)),
                'rientro_previsto': rientro_previsto.strftime('%H:%M'),
                'tappe': tappe_ordinate_oggetti, # SALVA LA LISTA DI OGGETTI ORDINE CORRETTI E ARRICCHITI
            }
            print(f"INFO [calcola_giri]: Percorso calcolato con successo per {vettore}.")
            total_calculated += 1

        # ... (Gestione eccezioni invariata) ...
        except googlemaps.exceptions.ApiError as e: total_errors += 1; print(f"ERRORE API Google Maps per {vettore}: {e}"); flash(f"Errore API Google Maps per {vettore}.", "danger")
        except ValueError as e: total_errors += 1; print(f"Errore elaborazione percorso per {vettore}: {e}"); flash(f"Errore elaborazione percorso per {vettore}.", "danger")
        except Exception as e: total_errors += 1; print(f"Errore INASPETTATO calcolo percorso per {vettore}: {e}"); flash(f"Errore inaspettato calcolo percorso per {vettore}.", "danger")


    # 4. Aggiorna store globale
    with app_data_store_lock:
        app_data_store["calculated_routes"] = calculated_routes_temp
        print("DEBUG [calcola_giri]: Aggiornato app_data_store['calculated_routes']")

    flash(f"Calcolo giri completato: {total_calculated} successi, {total_errors} errori.", "info" if total_errors == 0 else "warning")
    print("--- DEBUG: Fine /calcola-giri ---\n")
    return redirect(url_for('autisti'))


# --- Rotte Autisti e Consegne (con Lock) ---

@app.route('/autisti')
@login_required
def autisti():
    """Mostra l'elenco degli autisti con giri calcolati."""
    if not (current_user.has_role('admin') or current_user.has_role('autista')):
        flash("Accesso non autorizzato.", "danger")
        return redirect(url_for('dashboard'))

    # Leggi giri calcolati sotto lock
    with app_data_store_lock:
        # Crea una copia per il template
        giri_calcolati = dict(app_data_store.get("calculated_routes", {}))

    # Aggiungi autisti senza giro calcolato ma con ordini assegnati
    autisti_assegnati = set()
    with app_data_store_lock:
        for logistic_info in app_data_store.get("logistics", {}).values():
             if isinstance(logistic_info, dict) and logistic_info.get('nome') != 'Sconosciuto':
                 autisti_assegnati.add(logistic_info['nome'])

    autisti_senza_giro = autisti_assegnati - set(giri_calcolati.keys())

    return render_template('autisti.html',
                           giri=giri_calcolati,
                           autisti_senza_giro=sorted(list(autisti_senza_giro)),
                           active_page='autisti')


@app.route('/consegne/<autista_nome>')
@login_required
def consegne_autista(autista_nome):
    """Mostra il dettaglio del giro e delle tappe per un autista."""
    # ... (controllo permessi iniziale invariato) ...
    is_admin = current_user.has_role('admin')
    is_correct_driver = current_user.has_role('autista') and current_user.nome_autista == autista_nome
    if not (is_admin or is_correct_driver):
        flash("Accesso non autorizzato.", "danger")
        return redirect(url_for('dashboard'))

    # --- AGGIUNGI DEBUG PRINT ---
    print(f"\n--- DEBUG: Preparazione dati per /consegne/{autista_nome} ---")
    # --- FINE DEBUG PRINT ---

    with app_data_store_lock:
        giro_calcolato_orig = app_data_store.get("calculated_routes", {}).get(autista_nome)
        giro_calcolato = dict(giro_calcolato_orig) if giro_calcolato_orig else None
        delivery_events_copy = dict(app_data_store.get("delivery_events", {}))
        statuses_copy = dict(app_data_store.get("statuses", {}))
        driver_notes_copy = dict(app_data_store.get("driver_notes", {}))
        orders_assigned_no_route = []
        if not giro_calcolato:
             # Se il giro non è calcolato, prendi gli ordini direttamente dalla cache orders
             logistics_copy = dict(app_data_store.get("logistics", {}))
             orders_copy = dict(app_data_store.get("orders", {})) # Leggi la cache ordini aggiornata
             print(f"DEBUG: Giro non calcolato. Cerco ordini assegnati a {autista_nome} dalla cache ({len(orders_copy)} ordini totali)...")
             for order_key, logistic_info in logistics_copy.items():
                 if isinstance(logistic_info, dict) and logistic_info.get('nome') == autista_nome:
                    ordine_completo = orders_copy.get(order_key)
                    if ordine_completo:
                        ordine_copy = dict(ordine_completo)
                        ordine_copy['_order_key'] = order_key
                        orders_assigned_no_route.append(ordine_copy)
                        print(f"  + Aggiunto ordine {order_key} (senza giro)")
             orders_assigned_no_route.sort(key=lambda x: x.get('numero', 0))


    tappe_da_mostrare = []
    if giro_calcolato and 'tappe' in giro_calcolato:
         print(f"DEBUG: Uso le tappe dal giro calcolato per {autista_nome}.")
         tappe_da_mostrare = [dict(t) for t in giro_calcolato['tappe']] # Copie
    else:
        print(f"DEBUG: Uso la lista ordini assegnati (non da giro) per {autista_nome}.")
        tappe_da_mostrare = orders_assigned_no_route # Già copie
        if not tappe_da_mostrare:
            flash(f"Nessun ordine assegnato o giro calcolato trovato per {autista_nome}.", "warning")
        else:
             flash(f"Giro non ancora calcolato per {autista_nome}. Mostro elenco ordini assegnati.", "info")


    # Arricchisci le tappe con dati di stato consegna e note
    print(f"DEBUG: Arricchimento di {len(tappe_da_mostrare)} tappe...")
    for i, tappa in enumerate(tappe_da_mostrare):
        order_key = tappa.get('_order_key')
        if not order_key:
            order_key = f"{tappa.get('sigla','?')}:{tappa.get('serie','?')}:{tappa.get('numero','?')}"

        order_id = str(tappa.get('numero'))
        eventi = delivery_events_copy.get(order_key, {})
        status_ordine_picking = statuses_copy.get(order_id, {})

        tappa['start_time'] = eventi.get('start_time')
        tappa['end_time'] = eventi.get('end_time')
        # ... (calcolo durata) ...
        if tappa['start_time'] and tappa['end_time']:
             try:
                 start_dt = datetime.strptime(tappa['start_time'], '%H:%M:%S'); end_dt = datetime.strptime(tappa['end_time'], '%H:%M:%S')
                 durata_td = end_dt - start_dt; durata_sec = durata_td.total_seconds();
                 if durata_sec < 0: durata_sec += 24 * 3600
                 tappa['durata_effettiva_min'] = math.ceil(durata_sec / 60)
             except (ValueError, TypeError): tappa['durata_effettiva_min'] = None
        else: tappa['durata_effettiva_min'] = None

        tappa['colli_da_consegnare'] = status_ordine_picking.get('colli_totali_operatore', 'N/D')
        tappa['nota_autista'] = driver_notes_copy.get(order_key, '')
        # Stato consegna
        if tappa['end_time']: tappa['status_consegna'] = 'Completata'
        elif tappa['start_time']: tappa['status_consegna'] = 'In Corso'
        else: tappa['status_consegna'] = 'Da Iniziare'

        # --- AGGIUNGI DEBUG PRINT PER INDIRIZZO ---
        print(f"  - Tappa {i+1} (Ordine #{tappa.get('numero')} - Key: {order_key}):")
        print(f"    Indirizzo Effettivo: '{tappa.get('indirizzo_effettivo')}'")
        print(f"    Localita Effettiva: '{tappa.get('localita_effettiva')}'")
        print(f"    Fonte Indirizzo: '{tappa.get('fonte_indirizzo')}'")
        # --- FINE DEBUG PRINT ---

        # Assicurati che i campi esistano per il template (fallback se _effettivo manca per qualche motivo)
        if 'indirizzo_effettivo' not in tappa: tappa['indirizzo_effettivo'] = tappa.get('indirizzo', 'N/D')
        if 'localita_effettiva' not in tappa: tappa['localita_effettiva'] = tappa.get('localita', 'N/D')

    print(f"--- DEBUG: Fine preparazione dati per /consegne/{autista_nome} ---\n")

    return render_template('consegna_autista.html',
                           autista_nome=autista_nome,
                           giro=giro_calcolato,
                           tappe=tappe_da_mostrare)


# --- Spostamento Tappe (con Lock) ---
@app.route('/move_tappa/<autista_nome>/<int:index>/<direction>', methods=['POST'])
@login_required
def move_tappa(autista_nome, index, direction):
    """Sposta una tappa su o giù nell'ordine del giro calcolato."""
    # Controllo autorizzazione
    is_admin = current_user.has_role('admin')
    is_correct_driver = current_user.has_role('autista') and current_user.nome_autista == autista_nome
    if not (is_admin or is_correct_driver):
        flash("Accesso non autorizzato a modificare l'ordine delle tappe.", "danger")
        return redirect(url_for('consegne_autista', autista_nome=autista_nome))

    if direction not in ['up', 'down']:
         flash("Direzione spostamento non valida.", "danger")
         return redirect(url_for('consegne_autista', autista_nome=autista_nome))

    # Modifica l'ordine sotto lock
    with app_data_store_lock:
        giro_calcolato = app_data_store.get("calculated_routes", {}).get(autista_nome)
        if not giro_calcolato or 'tappe' not in giro_calcolato or not isinstance(giro_calcolato['tappe'], list):
            flash("Impossibile modificare: giro non calcolato o tappe non valide.", "warning")
            return redirect(url_for('consegne_autista', autista_nome=autista_nome))

        tappe = giro_calcolato['tappe'] # Riferimento diretto alla lista nello store
        if not (0 <= index < len(tappe)):
            flash("Indice tappa non valido.", "danger")
            return redirect(url_for('consegne_autista', autista_nome=autista_nome))

        tappa_da_spostare = tappe.pop(index)
        nuovo_index = -1

        if direction == 'up' and index > 0:
            nuovo_index = index - 1
        elif direction == 'down' and index < len(tappe): # Lunghezza lista diminuita di 1
            nuovo_index = index # Inserisci alla stessa posizione (che ora è quella successiva)

        if nuovo_index != -1 and 0 <= nuovo_index <= len(tappe):
             tappe.insert(nuovo_index, tappa_da_spostare)
             # Non serve riassegnare tappe a giro_calcolato, è modificato per riferimento
             flash('Ordine tappe aggiornato.', 'success')
             # FORSE: Ricalcolare orari previsti qui? O lasciare invariati?
             # Per ora li lasciamo invariati, l'autista gestisce l'ordine reale.
        else:
             # Reinserisci all'indice originale se lo spostamento non è valido
             tappe.insert(index, tappa_da_spostare)
             flash('Spostamento tappa non possibile (inizio/fine lista).', 'warning')

    return redirect(url_for('consegne_autista', autista_nome=autista_nome))


# --- Start/End Consegna (con Lock e Notifica) ---
@app.route('/consegna/start', methods=['POST'])
@login_required
def start_consegna():
    """Registra l'orario di inizio di una consegna."""
    # Controllo autorizzazione
    is_admin = current_user.has_role('admin')
    is_driver = current_user.has_role('autista')
    autista_nome_form = request.form.get('autista_nome')
    is_correct_driver = is_driver and current_user.nome_autista == autista_nome_form
    if not (is_admin or is_correct_driver):
         flash("Accesso non autorizzato ad avviare la consegna.", "danger")
         # Determina dove reindirizzare
         target_autista = autista_nome_form if autista_nome_form else (current_user.nome_autista if is_driver else None)
         if target_autista:
             return redirect(url_for('consegne_autista', autista_nome=target_autista))
         else:
             return redirect(url_for('dashboard'))

    order_key = request.form.get('order_key')
    if not order_key:
        flash("Errore: Chiave ordine mancante.", "danger")
        return redirect(url_for('consegne_autista', autista_nome=autista_nome_form))

    timestamp_inizio = datetime.now().strftime('%H:%M:%S')

    # Aggiorna evento sotto lock
    with app_data_store_lock:
        event = app_data_store["delivery_events"].setdefault(order_key, {})
        # Non sovrascrivere se già iniziato
        if 'start_time' not in event or not event['start_time']:
            event['start_time'] = timestamp_inizio
            flash(f"Consegna {order_key} iniziata alle {timestamp_inizio}.", "info")
        else:
             flash(f"Consegna {order_key} già iniziata precedentemente.", "warning")

    return redirect(url_for('consegne_autista', autista_nome=autista_nome_form))


@app.route('/consegna/end', methods=['POST'])
@login_required
def end_consegna():
    """Registra l'orario di fine consegna e invia notifica agli admin."""
    # Controllo autorizzazione
    is_admin = current_user.has_role('admin')
    is_driver = current_user.has_role('autista')
    autista_nome_form = request.form.get('autista_nome')
    is_correct_driver = is_driver and current_user.nome_autista == autista_nome_form
    if not (is_admin or is_correct_driver):
         flash("Accesso non autorizzato a terminare la consegna.", "danger")
         target_autista = autista_nome_form if autista_nome_form else (current_user.nome_autista if is_driver else None)
         if target_autista:
             return redirect(url_for('consegne_autista', autista_nome=target_autista))
         else:
             return redirect(url_for('dashboard'))

    order_key = request.form.get('order_key')
    if not order_key:
        flash("Errore: Chiave ordine mancante.", "danger")
        return redirect(url_for('consegne_autista', autista_nome=autista_nome_form))

    timestamp_fine = datetime.now().strftime('%H:%M:%S')
    nome_cliente_notifica = 'Cliente Sconosciuto' # Default

    # Aggiorna evento e leggi nome cliente sotto lock
    with app_data_store_lock:
        event = app_data_store["delivery_events"].setdefault(order_key, {})
        # Imposta fine solo se c'era un inizio e non c'è già una fine
        if 'start_time' in event and ('end_time' not in event or not event['end_time']):
             event['end_time'] = timestamp_fine
             # Recupera nome cliente per notifica
             ordine = app_data_store.get("orders", {}).get(order_key)
             if ordine:
                 nome_cliente_notifica = ordine.get('ragione_sociale', 'Cliente Sconosciuto')
             flash(f"Consegna per {nome_cliente_notifica} ({order_key}) completata alle {timestamp_fine}.", "success")
             send_notification_flag = True # Invia notifica
        elif 'end_time' in event and event['end_time']:
             flash(f"Consegna {order_key} già completata precedentemente.", "warning")
             send_notification_flag = False
        else: # Manca start_time
             flash(f"Errore: Impossibile completare consegna {order_key} senza un orario di inizio.", "danger")
             send_notification_flag = False


    # --- INVIO NOTIFICA (se consegna appena completata, fuori dal lock) ---
    if send_notification_flag:
        try:
            titolo_notifica = f"Consegna Completata ({autista_nome_form})"
            corpo_notifica = f"Ordine {order_key} a {nome_cliente_notifica} completato."
            admin_users = [user for user, data in users_db.items() if 'admin' in data.get('roles', [])]
            if not admin_users:
                 print("Nessun utente admin trovato per inviare notifica.")
            for admin in admin_users:
                print(f"Invio notifica completamento consegna ad admin: {admin}")
                send_push_notification(admin, titolo_notifica, corpo_notifica)
        except Exception as e:
            print(f"Errore durante invio notifica consegna {order_key}: {e}")
            flash("Consegna completata, ma errore invio notifica.", "warning")

    return redirect(url_for('consegne_autista', autista_nome=autista_nome_form))


# --- Funzione Calcolo Riepilogo Admin (con Lock interno) ---
def _calculate_admin_summary_data():
    """
    Calcola statistiche riassuntive per la dashboard admin.
    Legge i dati dallo store globale usando un lock.
    """
    with app_data_store_lock: # Blocca accesso a tutto lo store durante il calcolo
        # Crea copie per lavorare in sicurezza
        calculated_routes_copy = dict(app_data_store.get("calculated_routes", {}))
        delivery_events_copy = dict(app_data_store.get("delivery_events", {}))
        logistics_copy = dict(app_data_store.get("logistics", {}))
        orders_copy = dict(app_data_store.get("orders", {}))
        statuses_copy = dict(app_data_store.get("statuses", {}))

    dettagli_per_autista = {}
    consegne_totali_completate = 0
    consegne_totali_in_corso = 0
    tempo_totale_effettivo_sec = 0
    km_totali_previsti = 0.0
    consegne_per_ora = defaultdict(int) # Es: {9: 2, 10: 5, ...}

    # Itera sugli eventi per trovare consegne in corso o completate
    for order_key, evento in delivery_events_copy.items():
        logistic_info = logistics_copy.get(order_key)
        # Salta se non è un dict o manca il nome
        if not isinstance(logistic_info, dict) or not logistic_info.get('nome'):
            continue
        autista_nome = logistic_info['nome']

        # Inizializza struttura per autista se non esiste
        if autista_nome not in dettagli_per_autista:
             giro_pianificato = calculated_routes_copy.get(autista_nome, {})
             dettagli_per_autista[autista_nome] = {
                 'summary': dict(giro_pianificato), # Copia summary
                 'consegne': [], # Lista consegne per questo autista
                 'tempo_effettivo_sec': 0 # Tempo totale consegne completate
             }

        ordine = orders_copy.get(order_key)
        if not ordine: continue # Salta se l'ordine non è più nella cache

        status_consegna = "Assegnata"
        durata_effettiva_str = "-"
        ora_inizio = -1 # Ora intera per grafico

        start_time_str = evento.get('start_time')
        end_time_str = evento.get('end_time')

        if start_time_str:
            status_consegna = "In Corso"
            if not end_time_str: # Conta solo se non ancora completata
                consegne_totali_in_corso += 1
            try:
                # Arrotonda all'ora per il grafico
                start_dt = datetime.strptime(start_time_str, '%H:%M:%S')
                ora_inizio = start_dt.hour
            except (ValueError, TypeError): pass # Ignora se formato ora non valido

        if start_time_str and end_time_str:
            status_consegna = "Completata"
            consegne_totali_completate += 1
            try:
                start_dt = datetime.strptime(start_time_str, '%H:%M:%S')
                end_dt = datetime.strptime(end_time_str, '%H:%M:%S')
                durata_td = end_dt - start_dt
                durata_sec = durata_td.total_seconds()
                if durata_sec < 0: durata_sec += 24 * 3600 # Gestisce cambio giorno
                dettagli_per_autista[autista_nome]['tempo_effettivo_sec'] += durata_sec
                tempo_totale_effettivo_sec += durata_sec
                durata_min = math.ceil(durata_sec / 60)
                durata_effettiva_str = f"{durata_min} min"
                # Incrementa contatore per grafico solo se ora inizio valida
                if ora_inizio != -1: consegne_per_ora[ora_inizio] += 1
            except (ValueError, TypeError) as e:
                print(f"Errore calcolo durata consegna per {order_key}: {e}")
                pass # Lascia '-'

        order_id = str(ordine.get('numero'))
        status_ordine_picking = statuses_copy.get(order_id, {}) # Stato picking/controllo

        # Aggiungi dettaglio consegna alla lista dell'autista
        dettaglio_consegna = {
            'ragione_sociale': ordine.get('ragione_sociale', 'N/D'),
            'indirizzo': ordine.get('indirizzo', '-'),
            'localita': ordine.get('localita', '-'),
            'start_time_reale': start_time_str or '-',
            'end_time_reale': end_time_str or '-',
            'durata_effettiva': durata_effettiva_str,
            'colli': status_ordine_picking.get('colli_totali_operatore', 'N/D'),
            'status': status_consegna # Stato consegna (Assegnata, In Corso, Completata)
        }
        dettagli_per_autista[autista_nome]['consegne'].append(dettaglio_consegna)

    # Formatta tempi totali e calcola km totali previsti
    for autista_nome, dettagli in dettagli_per_autista.items():
         tempo_sec = dettagli['tempo_effettivo_sec']
         dettagli['summary']['tempo_totale_reale'] = time.strftime("%Hh %Mm", time.gmtime(tempo_sec)) if tempo_sec > 0 else "0h 0m"
         try:
            giro_pianificato = dettagli.get('summary', {})
            # Estrai km numerico dal formato "xx.x km"
            km_str = giro_pianificato.get('km_previsti', '0 km').split(' ')[0]
            km_autista = float(km_str) if km_str else 0.0
            km_totali_previsti += km_autista
         except ValueError: pass # Ignora se km non è numerico

    # Calcola statistiche generali
    tempo_medio_consegna_str = "-"
    if consegne_totali_completate > 0:
        try:
            tempo_medio_sec = tempo_totale_effettivo_sec / consegne_totali_completate
            tempo_medio_min = math.ceil(tempo_medio_sec / 60)
            tempo_medio_consegna_str = f"{tempo_medio_min} min"
        except ZeroDivisionError: pass

    summary_stats = {
        'consegne_totali': consegne_totali_completate,
        'consegne_in_corso': consegne_totali_in_corso,
        'km_totali': f"{km_totali_previsti:.1f} km",
        'tempo_medio': tempo_medio_consegna_str
    }

    # Prepara dati per il grafico consegne per ora
    ore_grafico = list(range(7, 21)) # Fascia oraria 7-20 per il grafico
    conteggi_grafico = [consegne_per_ora.get(h, 0) for h in ore_grafico]
    chart_data = {'labels': [f"{h}:00" for h in ore_grafico], 'data': conteggi_grafico}

    return summary_stats, dettagli_per_autista, chart_data


# --- Rotta Amministrazione (Usa _calculate con Lock) ---
@app.route('/amministrazione')
@login_required
def amministrazione():
    """Pagina riepilogativa per l'amministratore."""
    if not current_user.has_role('admin'):
        flash("Accesso non autorizzato alla pagina amministrazione.", "danger")
        return redirect(url_for('dashboard'))

    # Chiama la funzione helper che ora gestisce il lock internamente
    try:
        summary_stats, dettagli_per_autista, chart_data = _calculate_admin_summary_data()
    except Exception as e:
         print(f"Errore in _calculate_admin_summary_data: {e}")
         flash("Errore durante il calcolo delle statistiche amministrative.", "danger")
         summary_stats, dettagli_per_autista, chart_data = {}, {}, {'labels':[], 'data':[]}


    return render_template('amministrazione.html',
                           summary_stats=summary_stats,
                           dettagli_per_autista=dettagli_per_autista,
                           chart_data=chart_data, # Passa dati grafico al template
                           active_page='amministrazione')


# --- Dettaglio Ordine (con Lock) ---
@app.route('/order/<sigla>/<serie>/<numero>')
@login_required
def order_detail_view(sigla, serie, numero):
    """Mostra i dettagli di un singolo ordine."""
    if not (current_user.has_role('admin') or current_user.has_role('preparatore')):
        flash("Accesso non autorizzato al dettaglio ordine.", "danger")
        return redirect(url_for('dashboard'))

    order_key = f"{sigla}:{serie}:{numero}"
    order_id = str(numero)

    # Leggi ordine e stato sotto lock
    with app_data_store_lock:
        order_data = app_data_store.get("orders", {}).get(order_key)
        if order_id not in app_data_store.get("statuses", {}):
            app_data_store.setdefault("statuses", {})[order_id] = get_initial_status()
        # Crea una copia dello stato, assicurandoti che 'picked_items' sia un dict
        order_state_orig = app_data_store.get("statuses", {}).get(order_id, get_initial_status())
        order_state = dict(order_state_orig) # Copia
        if not isinstance(order_state.get('picked_items'), dict):
             order_state['picked_items'] = {} # Inizializza se non è dict

    if not order_data:
        # Prova a ricaricare i dati se l'ordine manca dalla cache
        print(f"Ordine {order_key} non in cache, tentativo di ricaricamento...")
        flash(f"Ordine {order_key} non trovato in cache, ricarico dati...", "info")
        load_all_data() # Ricarica tutto
        with app_data_store_lock: # Rileggi dopo ricaricamento
             order_data = app_data_store.get("orders", {}).get(order_key)
             if order_id in app_data_store.get("statuses", {}):
                  order_state = dict(app_data_store["statuses"][order_id])
             # else usa l'initial status già creato

        if not order_data:
            flash(f"Errore: Impossibile trovare l'ordine {order_key}.", "danger")
            return redirect(url_for('ordini_list'))

    # Crea una copia dell'ordine per sicurezza
    order_copy = dict(order_data)

    return render_template('order_detail.html',
                           order=order_copy,
                           state=order_state) 


# --- Azioni Ordine (con Lock e Notifica) ---
@app.route('/order/<sigla>/<serie>/<numero>/action', methods=['POST'])
@login_required
def order_action(sigla, serie, numero):
    """Gestisce le azioni sullo stato di un ordine (picking, controllo, approvazione)."""
    if not (current_user.has_role('admin') or current_user.has_role('preparatore')):
        flash("Accesso non autorizzato a modificare lo stato dell'ordine.", "danger")
        return redirect(url_for('order_detail_view', sigla=sigla, serie=serie, numero=numero))

    action = request.form.get('action')
    order_id = str(numero)
    order_key = f"{sigla}:{serie}:{numero}"
    order_name_notifica = f"#{order_id}" # Default per notifica
    send_notification_flag = False # Flag per inviare notifica dopo il lock

    # Leggi e aggiorna stato sotto lock
    with app_data_store_lock:
        current_state = app_data_store.get("statuses", {}).get(order_id)
        if not current_state:
            flash(f"Stato per l'ordine {order_id} non trovato.", "danger")
            return redirect(url_for('ordini_list')) # O alla pagina ordine se esiste ancora

        # Copia stato per confronto
        stato_precedente = current_state.get('status', 'Sconosciuto')

        # Recupera nome cliente per notifica (se disponibile)
        order_info = app_data_store.get("orders", {}).get(order_key, {})
        if order_info:
            order_name_notifica = f"#{order_id} ({order_info.get('ragione_sociale', 'N/D')})"

        # Applica l'azione
        if action == 'start_picking':
            if stato_precedente == 'Da Lavorare' or stato_precedente == 'In Controllo': # Permetti ripresa
                current_state['status'] = 'In Picking'
                flash(f"Ordine {order_name_notifica} messo 'In Picking'.", "info")
            else:
                 flash(f"Azione 'In Picking' non permessa dallo stato '{stato_precedente}'.", "warning")
        elif action == 'complete_picking':
            if stato_precedente == 'In Picking':
                current_state['status'] = 'In Controllo'
                picked_qty = {}
                for key, val in request.form.items():
                    if key.startswith('picked_qty_'):
                         item_code = key.replace('picked_qty_', '')
                         picked_qty[item_code] = val # Salva quantità come stringa per ora
                colli_totali = request.form.get('colli_totali_operatore', '0')
                try:
                    # Convalida colli totali come numero intero
                    current_state['colli_totali_operatore'] = int(colli_totali) if colli_totali else 0
                except ValueError:
                     current_state['colli_totali_operatore'] = 0 # Default a 0 se non valido
                     flash("Numero colli non valido, impostato a 0.", "warning")

                current_state['picked_items'] = picked_qty
                flash(f"Picking per {order_name_notifica} completato. In attesa di controllo.", "info")
            else:
                 flash(f"Azione 'Completa Picking' non permessa dallo stato '{stato_precedente}'.", "warning")
        elif action == 'approve_order':
            if stato_precedente == 'In Controllo':
                current_state['status'] = 'Completato'
                flash(f"Ordine {order_name_notifica} approvato e completato.", "success")
                send_notification_flag = True # Invia notifica dopo
            else:
                flash(f"Azione 'Approva Ordine' non permessa dallo stato '{stato_precedente}'.", "warning")
        elif action == 'reject_order':
            if stato_precedente == 'In Controllo':
                current_state['status'] = 'In Picking' # Torna in picking
                # Potresti voler resettare 'picked_items' o 'colli_totali' qui?
                flash(f"Ordine {order_name_notifica} rifiutato. Riportato a 'In Picking'.", "warning")
            else:
                 flash(f"Azione 'Rifiuta Ordine' non permessa dallo stato '{stato_precedente}'.", "warning")
        else:
             flash("Azione sullo stato ordine non riconosciuta.", "danger")

        # Riassegna per sicurezza (anche se modifica per riferimento)
        app_data_store.setdefault("statuses", {})[order_id] = current_state

    # --- INVIO NOTIFICA (se approvato, fuori dal lock) ---
    if send_notification_flag:
        try:
            admin_users = [user for user, data in users_db.items() if 'admin' in data.get('roles', [])]
            if not admin_users:
                 print("Nessun utente admin trovato per inviare notifica approvazione.")
            for admin in admin_users:
                print(f"Invio notifica approvazione ordine ad admin: {admin}")
                send_push_notification(admin, "Ordine Pronto Spedizione!", f"Ordine {order_name_notifica} approvato.")
        except Exception as e:
            print(f"Errore invio notifica approvazione ordine {order_key}: {e}")
            # Non sovrascrivere il flash di successo precedente
            flash("Errore durante invio notifica ad admin.", "warning")

    return redirect(url_for('order_detail_view', sigla=sigla, serie=serie, numero=numero))


# --- RIMOZIONE PDF: Funzione stampa_lista_prelievo rimossa ---


@app.route('/magazzino')
@login_required
def magazzino():
    """Pagina di ricerca articoli nel magazzino per codice o descrizione."""
    # ... (codice iniziale della funzione e controllo permessi invariato) ...
    query = request.args.get('q', '').strip()
    articles_list = [] # Lista finale con dettagli completi
    error_message = None
    search_type_used = None

    if query:
        print(f"Ricerca magazzino per: '{query}'")

        # --- Logica di ricerca per codice O descrizione (invariata) ---
        is_likely_code = ' ' not in query
        articles_data = None # Risultati iniziali della ricerca (lista)
        if is_likely_code:
            print("Ricerca per descrizione...")
            articles_data = search_articles(query)
            search_type_used = 'descrizione'
            if articles_data is not None and not articles_data:
                 print(f"Nessun risultato per codice '{query}', tento ricerca per descrizione...")
                 articles_data = search_articles(query)
                 search_type_used = 'descrizione'
        else:
             print("Ricerca per descrizione...")
             articles_data = search_articles(query)
             search_type_used = 'descrizione'

        if articles_data is None:
            error_message = f"Errore API durante la ricerca di '{query}'. Riprova più tardi."
        elif not articles_data:
             error_message = f"Nessun articolo trovato per '{query}' (cercato per {search_type_used})."
        else:
            # --- MODIFICA: Recupera dettagli per ogni articolo trovato ---
            print(f"Trovati {len(articles_data)} articoli. Recupero dettagli...")
            processed_count = 0
            detail_errors = 0
            for art_summary in articles_data: # Itera sui risultati della ricerca
                codice_art = art_summary.get('codice')
                if not codice_art:
                    print(f"Articolo saltato nei risultati di ricerca per mancanza codice: {art_summary}")
                    continue

                # Recupera dettagli completi (incl. cod_alt) con chiamata GET singola
                art_details = get_article_details(codice_art)

                # Crea il dizionario 'art' finale unendo summary e details
                art = dict(art_summary) # Parti dai dati della ricerca

                if art_details:
                    # Aggiungi/Sovrascrivi campi dai dettagli (es. cod_alt)
                    art['cod_alternativo'] = art_details.get('cod_alternativo', '') # Aggiungi cod_alt dai dettagli
                    # Potresti aggiornare anche altri campi se necessario
                    # art['descrizione'] = art_details.get('descrizione', art['descrizione']) # Esempio
                else:
                    # Se get_article_details fallisce, imposta cod_alt a errore/vuoto
                    art['cod_alternativo'] = 'N/D' # O un altro indicatore
                    detail_errors += 1
                    print(f"Errore nel recuperare dettagli per {codice_art}")

                # Calcola giacenza e prezzo (come prima, ma sul dizionario 'art' finale)
                try:
                    qta_carico = float(art.get('qta_carico', 0) or 0)
                    qta_scarico = float(art.get('qta_scarico', 0) or 0)
                    ord_cli_e = float(art.get('ord_cli_e', 0) or 0)
                    ord_cli_sps = float(art.get('ord_cli_sps', 0) or 0)
                    esis = qta_carico - qta_scarico
                    disp_net = esis - ord_cli_e - ord_cli_sps
                    art['giacenza_netta'] = disp_net
                    art['prezzo'] = get_article_price(codice_art, listino_id=4) if codice_art else 0.0
                    processed_count += 1
                except (ValueError, TypeError, KeyError) as e:
                    print(f"Errore calcolo dati magazzino per articolo {codice_art}: {e}")
                    art['giacenza_netta'] = 'Errore'
                    art['prezzo'] = 'Errore'
                    # Mantieni cod_alt come 'N/D' o il valore trovato

                articles_list.append(art) # Aggiungi l'articolo arricchito alla lista finale
            # --- FINE MODIFICA ---
            print(f"Dettagli recuperati per {processed_count} articoli ({detail_errors} errori nel recupero dettagli).")
            if detail_errors > 0:
                 flash(f"Attenzione: Non è stato possibile recuperare i dettagli per {detail_errors} articoli.", "warning")

    if error_message:
        flash(error_message, "warning")

    # Passa la lista finale 'articles_list' (che ora contiene 'cod_alt')
    return render_template('magazzino.html',
                           query=query,
                           articles=articles_list,
                           active_page='magazzino')

# --- API Barcode (OK) ---
@app.route('/api/find-by-barcode', methods=['POST'])
@login_required
def find_by_barcode():
    """API endpoint per trovare il codice articolo primario da un barcode (alias)."""
    if not (current_user.has_role('admin') or current_user.has_role('preparatore')):
        return jsonify({'status': 'error', 'message': 'Accesso non autorizzato'}), 403

    data = request.json
    if not data or 'barcode' not in data:
        return jsonify({'status': 'error', 'message': 'Dati mancanti (barcode)'}), 400

    barcode = data['barcode'].strip()
    if not barcode:
        return jsonify({'status': 'error', 'message': 'Barcode vuoto fornito'}), 400

    print(f"Ricerca API per barcode: {barcode}")
    primary_code = get_article_by_alias(barcode) # Gestisce errori API interni

    if primary_code:
        print(f"Barcode {barcode} trovato, codice primario: {primary_code}")
        return jsonify({'status': 'success', 'primary_code': primary_code})
    else:
        # Potrebbe essere "non trovato" o errore API
        print(f"Barcode {barcode} non trovato o errore API.")
        return jsonify({'status': 'not_found', 'message': 'Codice a barre non trovato o errore API.'}), 404


# --- Fabbisogno (con fix indentazione) ---
@app.route('/fabbisogno')
@login_required
def fabbisogno():
    """Calcola e mostra il fabbisogno di articoli per un dato giorno."""
    # --- FIX INDENTAZIONE: Corpo della funzione inserito qui ---
    if not (current_user.has_role('admin') or current_user.has_role('preparatore')):
        flash("Accesso non autorizzato al calcolo fabbisogno.", "danger")
        return redirect(url_for('dashboard'))

    giorno_filtro = request.args.get('giorno_filtro', '').strip()
    fabbisogno_list = []
    data_selezionata_formattata = ''
    error_message = None

    if giorno_filtro:
        orders_list_copy = load_all_data() # Ottiene dati correnti (o None)

        if orders_list_copy is None:
            error_message = "Errore API: Impossibile caricare gli ordini per calcolare il fabbisogno."
        else:
            try:
                giorno_da_cercare = giorno_filtro.zfill(2)
                if not giorno_da_cercare.isdigit() or len(giorno_da_cercare) != 2:
                    raise ValueError("Formato giorno non valido.")

                print(f"Calcolo fabbisogno per giorno che termina con: '{giorno_da_cercare}'")
                ordini_del_giorno = [
                    order for order in orders_list_copy
                    if isinstance(order.get('data_documento'), str) and len(order['data_documento']) == 8 and order['data_documento'].endswith(giorno_da_cercare)
                ]

                if not ordini_del_giorno:
                     error_message = f"Nessun ordine trovato per il giorno '{giorno_filtro}'."
                     print(error_message)
                else:
                    print(f"Trovati {len(ordini_del_giorno)} ordini per il giorno. Aggrego articoli...")
                    fabbisogno_dict = defaultdict(lambda: {'codice': '', 'descrizione': '', 'quantita_totale': 0.0})
                    items_processed = 0
                    for order in ordini_del_giorno:
                        for item in order.get('righe', []):
                            codice = item.get('codice_articolo')
                            desc = item.get('descr_articolo', 'N/D')
                            try:
                                # Usa 'or 0' per gestire None o stringhe vuote prima di float
                                qta = float(item.get('quantita', 0) or 0)
                            except (ValueError, TypeError):
                                print(f"Attenzione: Quantità non valida per art. {codice} in ordine {order.get('numero')}: {item.get('quantita')}")
                                qta = 0.0

                            if codice and qta > 0: # Aggrega solo se codice esiste e qta > 0
                                fabbisogno_dict[codice]['codice'] = codice
                                fabbisogno_dict[codice]['descrizione'] = desc
                                fabbisogno_dict[codice]['quantita_totale'] += qta
                                items_processed += 1

                    fabbisogno_list = sorted(fabbisogno_dict.values(), key=lambda x: x['descrizione'])
                    data_selezionata_formattata = f"Giorno: {giorno_filtro}"
                    print(f"Aggregati {len(fabbisogno_list)} articoli unici da {items_processed} righe.")

            except ValueError as e:
                error_message = f"Filtro giorno non valido: {e}."
                print(error_message)
            except Exception as e:
                 error_message = f"Errore durante il calcolo del fabbisogno: {e}"
                 print(error_message)

    if error_message:
        flash(error_message, "warning")

    return render_template('fabbisogno.html',
                           fabbisogno_list=fabbisogno_list,
                           giorno_selezionato=giorno_filtro,
                           data_selezionata_formattata=data_selezionata_formattata,
                           active_page='fabbisogno')

@app.route('/api/scan-barcode/<sigla>/<int:serie>/<int:numero>', methods=['POST'])
@login_required
def scan_barcode_for_order(sigla, serie, numero):
    """
    Gestisce la scansione di un barcode per un ordine specifico.
    Trova l'articolo corrispondente e aggiorna la quantità 'picked' per la riga d'ordine.
    """
    if not (current_user.has_role('admin') or current_user.has_role('preparatore')):
        return jsonify({'status': 'error', 'message': 'Accesso non autorizzato'}), 403

    data = request.json
    barcode = data.get('barcode', '').strip()
    if not barcode:
        return jsonify({'status': 'error', 'message': 'Barcode mancante'}), 400

    order_key = f"{sigla}:{serie}:{numero}"
    order_id = str(numero)

    print(f"Ricevuto barcode '{barcode}' per ordine {order_key}")

    # 1. Trova codice articolo primario dall'alias (barcode)
    primary_code = find_article_code_by_alt_code(barcode) # Gestisce errori API interni
    if not primary_code:
        print(f"Barcode '{barcode}' non trovato o errore API.")
        return jsonify({'status': 'not_found', 'message': f"Barcode '{barcode}' non trovato."}), 404

    print(f"Barcode '{barcode}' corrisponde a codice primario '{primary_code}'")

    # 2. Aggiorna lo stato dell'ordine (sotto lock)
    with app_data_store_lock:
        order_data = app_data_store.get("orders", {}).get(order_key)
        order_status = app_data_store.get("statuses", {}).get(order_id)

        if not order_data or not order_status:
            print(f"Ordine {order_key} o stato non trovato nello store.")
            return jsonify({'status': 'error', 'message': 'Ordine non trovato'}), 404

        # Assicurati che picked_items sia un dizionario
        if not isinstance(order_status.get('picked_items'), dict):
             order_status['picked_items'] = {}

        # 3. Trova la riga corrispondente nell'ordine (prima riga non completamente prelevata)
        target_row_id = None
        target_row_index = -1
        found_match = False
        row_update_details = None

        for i, row in enumerate(order_data.get('righe', [])):
            if row.get('codice_articolo') == primary_code:
                row_id_str = str(row.get('id_riga')) # Chiave per picked_items
                if not row_id_str:
                    print(f"WARN: Riga {i} per articolo {primary_code} senza id_riga.")
                    continue

                try:
                    qta_ordinata = float(row.get('quantita', 0) or 0)
                    qta_gia_prelevata = float(order_status['picked_items'].get(row_id_str, 0) or 0)
                except (ValueError, TypeError):
                     print(f"WARN: Quantità non valida per riga {row_id_str}, articolo {primary_code}")
                     qta_ordinata = 0
                     qta_gia_prelevata = 0

                # Se questa riga ha ancora quantità da prelevare
                if qta_gia_prelevata < qta_ordinata:
                    target_row_id = row_id_str
                    target_row_index = i # Salva indice per riferimento
                    found_match = True

                    # Incrementa la quantità prelevata per questa riga
                    new_picked_qty = qta_gia_prelevata + 1
                    order_status['picked_items'][target_row_id] = new_picked_qty

                    print(f"Articolo '{primary_code}' trovato! Riga ID: {target_row_id}. Qta prelevata aggiornata a: {new_picked_qty}/{qta_ordinata}")

                    # Prepara dettagli per la risposta JSON
                    row_update_details = {
                        'id_riga': target_row_id,
                        'codice_articolo': primary_code,
                        'descrizione': row.get('descr_articolo', 'N/D'),
                        'qta_ordinata': qta_ordinata,
                        'qta_prelevata': new_picked_qty
                    }
                    break # Ferma alla prima riga trovata con quantità disponibile

        # 4. Gestisci i risultati
        if found_match and row_update_details:
            # Salva lo stato aggiornato (anche se modificato per riferimento)
            app_data_store.setdefault("statuses", {})[order_id] = order_status
            return jsonify({
                'status': 'success',
                'message': f"Articolo '{primary_code}' aggiunto.",
                'item': row_update_details
            })
        elif any(r.get('codice_articolo') == primary_code for r in order_data.get('righe', [])):
             # Articolo presente ma già completamente prelevato
             print(f"Articolo '{primary_code}' presente nell'ordine ma già completamente prelevato.")
             return jsonify({'status': 'already_picked', 'message': f"Articolo '{primary_code}' già completamente prelevato."}), 409 # Conflict
        else:
             # Articolo non trovato nell'ordine
             print(f"Articolo '{primary_code}' (da barcode '{barcode}') non trovato nelle righe dell'ordine {order_key}.")
             return jsonify({'status': 'item_not_in_order', 'message': f"Articolo '{primary_code}' non presente in questo ordine."}), 404 # Not Foun
        
@app.route('/api/update-alt-code', methods=['POST'])
@login_required
def update_alt_code_api():
    """API endpoint per aggiornare il codice alternativo di un articolo."""
    if not (current_user.has_role('admin') or current_user.has_role('preparatore')):
        return jsonify({'status': 'error', 'message': 'Accesso non autorizzato'}), 403

    data = request.json
    article_code = data.get('article_code')
    alt_code = data.get('alt_code') # Può essere stringa vuota per cancellare

    # Controlla che article_code sia presente e alt_code sia definito (anche se None o vuoto)
    if not article_code or alt_code is None:
        print("ERRORE API update_alt_code: Dati mancanti nella richiesta.")
        return jsonify({'status': 'error', 'message': 'Codice articolo o nuovo codice alternativo mancante.'}), 400

    print(f"Richiesta API per aggiornare cod_alternativo di '{article_code}' a '{alt_code}'")

    # Chiama la funzione API Mexal per l'aggiornamento
    success = update_article_alt_code(article_code, alt_code)

    if success:
        # Nota: La cache locale non viene aggiornata qui.
        return jsonify({'status': 'success', 'message': 'Codice alternativo aggiornato con successo.'})
    else:
        print(f"ERRORE API update_alt_code: Fallito aggiornamento per '{article_code}'.")
        return jsonify({'status': 'error', 'message': 'Errore durante l\'aggiornamento via API Mexal.'}), 500

@app.route('/clienti_indirizzi')
@login_required
def clienti_indirizzi():
    """Pagina temporanea per visualizzare clienti e indirizzi di spedizione."""
    # Autorizzazione (solo admin)
    if not current_user.has_role('admin'):
        flash("Accesso non autorizzato.", "danger")
        return redirect(url_for('dashboard'))

    # 1. Recupera clienti
    clients = get_all_clients() # Chiama la funzione API
    if clients is None: # Controlla se la chiamata API ha fallito
        flash("Errore nel recupero dell'elenco clienti dall'API.", "danger")
        clients = [] # Imposta lista vuota per evitare errori nel template

    # 2. Recupera indirizzi
    all_addresses = get_all_shipping_addresses() # Chiama la funzione API
    if all_addresses is None: # Controlla se la chiamata API ha fallito
        flash("Errore nel recupero degli indirizzi di spedizione dall'API.", "warning")
        all_addresses = [] # Imposta lista vuota

    # 3. Organizza indirizzi per codice cliente
    addresses_by_client = defaultdict(list) # Usa defaultdict per semplicità
    for addr in all_addresses:
        client_code = addr.get('cod_conto') # Recupera il codice cliente dall'indirizzo
        if client_code: # Assicurati che il codice esista
            addresses_by_client[client_code].append(addr) # Aggiungi l'indirizzo alla lista del cliente

    # 4. Ordina clienti per ragione sociale (alfabeticamente, ignorando maiuscole/minuscole)
    clients.sort(key=lambda c: c.get('ragione_sociale', '').lower())

    # 5. Passa i dati recuperati e organizzati al template
    return render_template('clienti_indirizzi.html',
                           clients=clients,                 # Lista dei clienti ordinata
                           addresses_map=addresses_by_client, # Dizionario con indirizzi per cliente
                           active_page='clienti_indirizzi')

@app.route('/todo')
@login_required # Accessibile a tutti i loggati
def todo_list():
    """Visualizza la lista To-Do CONDIVISA."""
    # user_id = current_user.id # Non serve più filtrare per utente
    try:
        # Recupera TUTTE le task, separate per stato
        incomplete_tasks = TodoItem.query.filter_by(is_completed=False).order_by(TodoItem.created_at.desc()).all()
        completed_tasks = TodoItem.query.filter_by(is_completed=True).order_by(TodoItem.completed_at.desc()).all()
    except Exception as e:
        print(f"Errore DB leggendo ToDo condivisa: {e}")
        flash("Errore nel caricamento delle cose da fare.", "danger")
        incomplete_tasks = []
        completed_tasks = []

    return render_template('todo.html',
                           incomplete_tasks=incomplete_tasks,
                           completed_tasks=completed_tasks,
                           active_page='todo')

@app.route('/todo/add', methods=['POST'])
@login_required
def add_todo():
    """Aggiunge una nuova task CONDIVISA."""
    description = request.form.get('description', '').strip()
    creator_id = current_user.id # Salva chi l'ha creata

    if not description:
        flash("La descrizione non può essere vuota.", "warning")
    else:
        try:
            # Crea task senza user_id, ma con created_by
            new_task = TodoItem(created_by=creator_id, description=description)
            db.session.add(new_task)
            print(f"DEBUG [add_todo]: Tentativo commit nuova task CONDIVISA da {creator_id}: '{description}'")
            db.session.commit()
            print(f"DEBUG [add_todo]: Commit Riuscito.")
            flash("Nuova cosa da fare aggiunta alla lista condivisa!", "success")

            # --- Invia notifica (a chi? Forse a tutti gli admin/preparatori?) ---
            # Potresti modificare send_push_notification per inviare a un gruppo
            # Per ora, invia solo a chi l'ha creata (come prima)
            try:
                description_short = (description[:40] + '...') if len(description) > 40 else description
                notification_title = "Nuova Cosa da Fare (Condivisa)"; notification_body = f"Aggiunto: '{description_short}'"
                print(f"Tentativo invio notifica ToDo a {creator_id}")
                send_push_notification(creator_id, notification_title, notification_body)
                # QUI POTRESTI AGGIUNGERE UN CICLO PER INVIARE AD ALTRI UTENTI SE NECESSARIO
                admin_users = [user for user, data in users_db.items() if 'admin' in data.get('roles', [])]
                for admin in admin_users:
                    if admin != creator_id: # Non inviare di nuovo a chi l'ha creata
                        send_push_notification(admin, f"Nuova Task da {creator_id}", f"Aggiunto: '{description_short}'")
            except Exception as notify_err: print(f"ERRORE [add_todo]: Fallito invio notifica push: {notify_err}")
            # --- Fine Invio Notifica ---

        except Exception as e:
            db.session.rollback()
            print(f"ERRORE CRITICO [add_todo]: Fallito commit DB condiviso da {creator_id}: {e}")
            flash("Errore durante l'aggiunta della cosa da fare.", "danger")

    return redirect(url_for('todo_list'))

@app.route('/todo/toggle/<int:item_id>', methods=['POST'])
@login_required
def toggle_todo(item_id):
    """Marca una task CONDIVISA come completata o la riapre (solo admin/preparatori)."""
    # --- AGGIUNTA CONTROLLO RUOLO ---
    if not (current_user.has_role('admin') or current_user.has_role('preparatore')):
        flash("Non hai i permessi per modificare lo stato delle task.", "warning")
        return redirect(url_for('todo_list'))
    # --- FINE CONTROLLO RUOLO ---

    completer_id = current_user.id # Chi sta facendo l'azione
    task = None
    try:
        # Cerca task per ID, senza filtrare per utente
        task = TodoItem.query.get(item_id) # Usa get per chiave primaria
        if task:
            original_state = task.is_completed
            if task.is_completed:
                # Riapri
                task.is_completed = False
                task.completed_at = None
                task.completed_by = None # Rimuovi chi l'aveva completata
                action_msg = "riaperta"
                flash_cat = "info"
            else:
                # Completa
                task.is_completed = True
                task.completed_at = datetime.utcnow()
                task.completed_by = completer_id # Salva chi l'ha completata
                action_msg = "completata"
                flash_cat = "success"

            print(f"DEBUG [toggle_todo]: Tentativo commit toggle task CONDIVISA {item_id} da {completer_id} (da {original_state} a {task.is_completed})")
            db.session.commit()
            print(f"DEBUG [toggle_todo]: Commit Riuscito.")
            flash(f"'{task.description[:30]}...' {action_msg}!", flash_cat)
        else:
            flash("Operazione non trovata.", "warning")
    except Exception as e:
        db.session.rollback()
        print(f"ERRORE CRITICO [toggle_todo]: Fallito commit DB condiviso per task {item_id}, user {completer_id}: {e}")
        flash("Errore durante l'aggiornamento dello stato.", "danger")

    return redirect(url_for('todo_list'))

@app.route('/todo/delete/<int:item_id>', methods=['POST'])
@login_required
def delete_todo(item_id):
    """Elimina una task CONDIVISA (solo admin)."""
    # --- AGGIUNTA CONTROLLO RUOLO ---
    if not current_user.has_role('admin'):
        flash("Non hai i permessi per eliminare le task.", "warning")
        return redirect(url_for('todo_list'))
    # --- FINE CONTROLLO RUOLO ---

    deleter_id = current_user.id
    task = None
    try:
        # Cerca task per ID, senza filtrare per utente
        task = TodoItem.query.get(item_id)
        if task:
            description_short = task.description[:30]
            db.session.delete(task)
            print(f"DEBUG [delete_todo]: Tentativo commit delete task CONDIVISA {item_id} da {deleter_id}: '{description_short}'")
            db.session.commit()
            print(f"DEBUG [delete_todo]: Commit Riuscito.")
            flash(f"'{description_short}...' eliminata.", "success")
        else:
            flash("Operazione non trovata.", "warning")
    except Exception as e:
        db.session.rollback()
        print(f"ERRORE CRITICO [delete_todo]: Fallito commit DB condiviso per task {item_id}, user {deleter_id}: {e}")
        flash("Errore durante l'eliminazione.", "danger")

    return redirect(url_for('todo_list'))


# --- NUOVA POSIZIONE: Creazione DB all'avvio, prima di app.run ---
with app.app_context():
    try:
        print("Verifica/Creazione tabelle database all'avvio...")
        db.create_all()
        print("Verifica/Creazione tabelle completata.")
    except Exception as e:
        print(f"ERRORE CRITICO durante creazione tabelle DB all'avvio: {e}")
        # Considera di uscire dall'app se il DB è essenziale e non può essere creato
        # import sys
        # sys.exit(1)


# --- Avvio App ---
if __name__ == '__main__':
    # Stampa configurazione per debug
    print("--- Configurazione Avvio ---")
    print(f"SECRET_KEY: {'Configurata (da env o default)' if app.config['SECRET_KEY'] else 'NON CONFIGURATA!'}")
    print(f"SQLALCHEMY_DATABASE_URI: {app.config['SQLALCHEMY_DATABASE_URI']}")
    print(f"VAPID_PUBLIC_KEY: {'Configurata' if VAPID_PUBLIC_KEY else 'NON CONFIGURATA!'}")
    print(f"VAPID_PRIVATE_KEY: {'Configurata' if VAPID_PRIVATE_KEY else 'NON CONFIGURATA!'}")
    print(f"VAPID_CLAIM_EMAIL: {VAPID_CLAIM_EMAIL}")
    print(f"MX_API_BASE_URL (da env): {os.getenv('MX_API_BASE_URL')}") # Logga valore env
    print(f"MX_AUTH (da env): {'Configurato' if os.getenv('MX_AUTH') else 'NON CONFIGURATO!'}")
    print(f"GOOGLE_MAPS_API_KEY (da env): {'Configurata' if os.getenv('GOOGLE_MAPS_API_KEY') else 'NON CONFIGURATA!'}")
    print(f"GMAPS_ORIGIN (da env): {os.getenv('GMAPS_ORIGIN')}")
    print(f"DEFAULT_STOP_TIME_MIN (da env): {os.getenv('DEFAULT_STOP_TIME_MIN')}")
    print("--------------------------")

    if not os.getenv('MX_AUTH'):
        print("\nATTENZIONE: MX_AUTH non è configurato nelle variabili d'ambiente!\n")
    # Aggiungi altri controlli per chiavi essenziali (VAPID, Google Maps, Secret Key)

    # Usa host='0.0.0.0' per essere accessibile sulla rete locale
    # Usa debug=True SOLO per sviluppo, MAI in produzione
    # Considera l'uso di un server WSGI (Gunicorn, Waitress) per produzione
    app.run(host='0.0.0.0', port=5001, debug=True)


