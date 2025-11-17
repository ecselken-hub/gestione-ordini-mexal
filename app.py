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
import io
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired
from werkzeug.security import generate_password_hash, check_password_hash
import json
from flask_sqlalchemy import SQLAlchemy
from pywebpush import webpush, WebPushException
import threading 
import dropbox
from fpdf import FPDF

# Carica variabili d'ambiente da .env (se esiste)
load_dotenv()

app = Flask(__name__)

class PDF(FPDF):
    def footer(self):
        # Va 1.5 cm dal fondo
        self.set_y(-15)
        # Seleziona Arial corsivo 8
        self.set_font("Arial", "I", 8)
        # Stampa 'Pagina X / Y' centrato
        self.cell(0, 10, f"Pagina {self.page_no()}/{{nb}}", 0, 0, "C")


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

GRUPPI_PESCE = ['01-PESCE', '01-CEFALOPODI', '01-CROSTACEI']
GRUPPI_FRUTTI = ['01-FRUTTI MARE', '01-OSTRICHE']
GRUPPI_GELO = ['03-MAT-PRIM-GELO,', '03-PIATTI-PRONTI', '04-SURIMI-GRANCH', '05-DESSERT-GELO',
               '06-FETT-SLI-TART', '01-EDMAME-WAKAME', '02-GAM-NOB-EBI', '04-PANE-PASTA',
               '07-UOVA-MAS-TOBK']
GRUPPI_SECCO = ['01-ACET-MIR-SAKE', '02-RISO', '03-ALGHE', '04-SALSA-SOIA', '05-PASTA-CEREALI',
                '06-CONDIMENTI', '07-FRUTT-FRUTSEC', '08-SALS-DRES-TOP', '09-BIRRA', '10-SAKE',
                '11-DESSERT-SECCO', '01-ALTRO-MATER']

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
    created_by = db.Column(db.String(80), nullable=True, index=True)
    description = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    is_completed = db.Column(db.Boolean, default=False, nullable=False)
    completed_at = db.Column(db.DateTime, nullable=True)
    completed_by = db.Column(db.String(80), nullable=True)
    assigned_to = db.Column(db.String(80), nullable=True, index=True) # <-- NUOVO CAMPO

    def __repr__(self):
        status = "Completato" if self.is_completed else "Da fare"
        creator = self.created_by or "Sconosciuto"
        assignee = f" -> {self.assigned_to}" if self.assigned_to else ""
        return f'<Todo {self.id} [{status}] - By: {creator}{assignee}>'

# --- Modello DB PushSubscription (OK) ---
class PushSubscription(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(50), nullable=False, index=True) # Aggiunto index
    subscription_json = db.Column(db.Text, nullable=False)
    # Potresti aggiungere un timestamp di creazione/aggiornamento
    # created_at = db.Column(db.DateTime, default=datetime.utcnow)

class PickingState(db.Model):
    """ Salva lo stato di picking per un singolo ordine. """
    # Usiamo 'order_key' (es. "OC:1:4197") come chiave primaria
    order_key = db.Column(db.String(50), primary_key=True) 
    order_id = db.Column(db.String(20), index=True) # Il 'numero' ordine
    status = db.Column(db.String(50), default='Da Lavorare', index=True)
    # Salva l'intera packing list come stringa JSON
    packing_list_json = db.Column(db.Text, default='[]') 
    # Salva i picked_items (riepilogo) come stringa JSON
    picked_items_json = db.Column(db.Text, default='{}') 
    colli_totali_operatore = db.Column(db.Integer, default=0)
    pdf_filename = db.Column(db.String(255), nullable=True)

class LogisticsAssignment(db.Model):
    """ Salva l'assegnazione autista e le note per un ordine. """
    order_key = db.Column(db.String(50), primary_key=True)
    autista_codice = db.Column(db.String(50), nullable=True)
    autista_nome = db.Column(db.String(100), nullable=True, index=True)
    nota_autista = db.Column(db.Text, nullable=True)

class DeliveryEvent(db.Model):
    """ Salva gli orari di inizio e fine consegna. """
    order_key = db.Column(db.String(50), primary_key=True)
    start_time_str = db.Column(db.String(10), nullable=True)
    end_time_str = db.Column(db.String(10), nullable=True)

class CalculatedRoute(db.Model):
    """ Salva il giro calcolato per un autista. """
    autista_nome = db.Column(db.String(100), primary_key=True)
    # Salva l'intero oggetto 'giro' (summary + tappe) come JSON
    route_data_json = db.Column(db.Text, nullable=False)
    last_calculated = db.Column(db.DateTime, default=datetime.utcnow)

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


def load_all_data():
    """
    Carica (o ricarica) dati da API Mexal, dando priorità
    all'indirizzo di spedizione e POPOLA IL DB con gli stati.
    """
    print("--- Inizio caricamento di massa dei dati dall'API (con priorità indirizzi spedizione) ---")

    # 1. Carica Clienti
    clients_response = mx_call_api('risorse/clienti/ricerca', method='POST', data={'filtri': []})
    if not clients_response or not isinstance(clients_response.get('dati'), list): 
        print("Errore CRITICO: Impossibile caricare i dati clienti.")
        flash("Errore nel recupero dei dati clienti.", "danger")
        return None, None # Restituisce None per ordini e mappa
    client_map = {client['codice']: client for client in clients_response['dati'] if 'codice' in client}
    print(f"Caricati {len(client_map)} clienti.")
    
    # 2. Carica Metodi Pagamento
    payment_map = get_payment_methods()
    if not payment_map: 
        flash("Attenzione: Non è stato possibile caricare i metodi di pagamento.", "warning")
        payment_map = {}
    print(f"Caricati {len(payment_map)} metodi di pagamento.")
    
    # 3. Carica Testate Ordini
    orders_response = mx_call_api('risorse/documenti/ordini-clienti/ricerca', method='POST', data={'filtri': []})
    if not orders_response or not isinstance(orders_response.get('dati'), list): 
        print("Errore CRITICO: Impossibile caricare gli ordini.")
        flash("Errore nel recupero degli ordini.", "danger")
        return None, None
    orders = orders_response['dati']
    print(f"Caricate {len(orders)} testate ordini.")
    
    # 4. Carica Righe Ordini
    rows_response = mx_call_api('risorse/documenti/ordini-clienti/righe/ricerca', method='POST', data={'filtri': []})
    rows_map = defaultdict(list)
    if rows_response and isinstance(rows_response.get('dati'), list):
        row_count = 0
        for row in rows_response['dati']:
            sigla = row.get('sigla', '?'); serie = row.get('serie', '?'); numero = row.get('numero', '?')
            if sigla != '?' and serie != '?' and numero != '?': 
                rows_map[f"{sigla}:{serie}:{numero}"].append(row)
                row_count += 1
        print(f"Caricate {row_count} righe ordini.")
    else: 
        print("Attenzione: Non è stato possibile caricare le righe degli ordini.")
        flash("Attenzione: Errore caricamento righe.", "warning")

    # 5. Assembla i dati e Sincronizza il DB
    # Manteniamo una mappa degli ordini in memoria per questa richiesta (ma non nello store globale)
    orders_data_map = {} 
    print("Inizio assemblaggio dati ordini e sincronizzazione stati DB...")
    processed_count = 0
    address_fetch_errors = 0
    specific_address_used_count = 0
    new_states_created = 0

    # Recupera tutti gli stati esistenti in una sola query
    existing_states = {state.order_key: state for state in PickingState.query.all()}
    
    for order in orders:
        sigla = order.get('sigla', '?'); serie = order.get('serie', '?'); numero = order.get('numero', '?')
        order_key = f"{sigla}:{serie}:{numero}"
        order_id_str = str(numero) if numero != '?' else None
        if not order_id_str: 
            continue

        # --- Sincronizza Stato Picking con DB ---
        if order_key not in existing_states:
            new_state = PickingState(order_key=order_key, order_id=order_id_str)
            db.session.add(new_state)
            existing_states[order_key] = new_state # Aggiungi al set per questa sessione
            new_states_created += 1
        # --- Fine Sincronizzazione ---

        client_code = order.get('cod_conto')
        client_data = client_map.get(client_code, {})

        order['ragione_sociale'] = client_data.get('ragione_sociale', 'N/D')
        order['telefono'] = client_data.get('telefono', 'N/D')

        # --- LOGICA INDIRIZZO (Invariata) ---
        shipping_address_id = order.get('cod_anag_sped')
        effective_address = client_data.get('indirizzo', 'N/D')
        effective_locality = client_data.get('localita', 'N/D')
        effective_cap = client_data.get('cap', '')
        effective_provincia = client_data.get('provincia', '')
        effective_telefono = order['telefono']
        shipping_details_source = "Anagrafica Cliente"

        if shipping_address_id:
            shipping_address_data = get_shipping_address(shipping_address_id)
            if shipping_address_data and isinstance(shipping_address_data, dict):
                addr_sped = shipping_address_data.get('indirizzo')
                loc_sped = shipping_address_data.get('localita')
                if addr_sped and loc_sped:
                    effective_address = addr_sped
                    effective_locality = loc_sped
                    effective_cap = shipping_address_data.get('cap', effective_cap)
                    effective_provincia = shipping_address_data.get('provincia', effective_provincia)
                    effective_telefono = shipping_address_data.get('telefono1', effective_telefono)
                    shipping_details_source = f"Indirizzo Sped. ID: {shipping_address_id}"
                    specific_address_used_count += 1
                else:
                    address_fetch_errors += 1
            else:
                address_fetch_errors += 1
        
        order['indirizzo_effettivo'] = effective_address
        order['localita_effettiva'] = effective_locality
        order['cap_effettivo'] = effective_cap
        order['provincia_effettiva'] = effective_provincia
        order['telefono_effettivo'] = effective_telefono
        order['fonte_indirizzo'] = shipping_details_source
        # --- FINE LOGICA INDIRIZZO ---

        dati_aggiuntivi = get_dati_aggiuntivi(client_code)
        order['orario1_start'] = dati_aggiuntivi.get('orario1start')
        order['orario1_end'] = dati_aggiuntivi.get('orario1end')
        order['nota'] = order.get('nota', '')
        order['pagamento_desc'] = payment_map.get(order.get('id_pagamento'), 'N/D')
        order['righe'] = rows_map.get(order_key, [])

        orders_data_map[order_key] = order # Costruisci la mappa
        processed_count += 1

    # Commit di tutti i nuovi stati creati in una sola transazione
    try:
        db.session.commit()
        print(f"Sincronizzazione DB completata. Creati {new_states_created} nuovi stati ordine.")
    except Exception as e:
        db.session.rollback()
        print(f"ERRORE CRITICO durante il commit dei nuovi stati: {e}")
        flash("Errore nel salvataggio dei nuovi stati ordine. Riprovare.", "danger")
        return None, None

    print(f"--- Caricamento completato. {processed_count} ordini in cache. Usati {specific_address_used_count} indirizzi sped. specifici ({address_fetch_errors} errori). ---")
    if address_fetch_errors > 0:
         flash(f"Attenzione: Impossibile recuperare o validare {address_fetch_errors} indirizzi di spedizione. Usato indirizzo cliente.", "warning")
    
    # Restituisce la mappa degli ordini e la mappa dei clienti
    return orders_data_map, client_map


# --- Cache Semplice per i dati (sostituisce app_data_store["orders"]) ---
# Mantiene i dati in memoria per 10 minuti per ridurre le chiamate API
_cache = {
    "orders_map": None,
    "client_map": None,
    "last_load_time": None
}
_article_details_cache = {}
CACHE_DURATION = timedelta(minutes=10) # Cache valida per 10 minuti

def get_cached_order_data():
    """
    Funzione helper che gestisce il caricamento e il caching dei dati
    degli ordini e dei clienti. Sostituisce la lettura da app_data_store.
    """
    now = datetime.now()
    if _cache["orders_map"] and _cache["last_load_time"] and (now - _cache["last_load_time"] < CACHE_DURATION):
        print("Dati ordini letti dalla cache (valida).")
        return _cache["orders_map"], _cache["client_map"]
    
    print("Cache scaduta o vuota. Ricarico i dati da Mexal...")
    orders_map, client_map = load_all_data() # Questa funzione ora popola il DB
    
    if orders_map is not None:
        _cache["orders_map"] = orders_map
        _cache["client_map"] = client_map
        _cache["last_load_time"] = now
        print("Cache ordini aggiornata.")
    else:
        print("Caricamento dati fallito. La cache non è stata aggiornata.")
        # Restituisce la cache vecchia se disponibile, altrimenti None
        return _cache["orders_map"], _cache["client_map"] 
        
    return orders_map, client_map

# --- Polling Route (Modificato per invalidare la cache) ---
@app.route('/check-updates')
@login_required
def check_updates():
    """
    Controlla se ci sono state modifiche su Mexal.
    Se rileva modifiche, invalida la cache in memoria.
    """
    last_load = _cache.get("last_load_time")

    if not last_load or not isinstance(last_load, datetime):
        print("Polling: Dati mai caricati, forzo aggiornamento.")
        return jsonify({'new_data': True})

    try:
        last_load_str = last_load.strftime('%Y%m%d %H%M%S')
    except Exception as e:
        print(f"Polling: Errore formattazione last_load_time ({last_load}): {e}. Forzo aggiornamento.")
        _cache["orders_map"] = None
        _cache["last_load_time"] = None
        return jsonify({'new_data': True})

    search_data = { 'filtri': [{'campo': 'data_ult_mod', 'condizione': '>', 'valore': last_load_str}] }

    print(f"Polling: Verifico aggiornamenti da {last_load_str}...")
    updates_testate = mx_call_api('risorse/documenti/ordini-clienti/ricerca', method='POST', data=search_data)
    updates_righe = mx_call_api('risorse/documenti/ordini-clienti/righe/ricerca', method='POST', data=search_data)

    if updates_testate is None or updates_righe is None:
         print("Polling: Errore durante la chiamata API.")
         return jsonify({'new_data': False, 'error': 'API check failed'})

    if (isinstance(updates_testate.get('dati'), list) and updates_testate['dati']) or \
       (isinstance(updates_righe.get('dati'), list) and updates_righe['dati']):
        print("Polling: Rilevati aggiornamenti. Invalido cache ordini e articoli.")
        _cache["orders_map"] = None # Invalida cache ordini
        _cache["last_load_time"] = None
        _article_details_cache.clear() # <-- SVUOTA CACHE ARTICOLI
        return jsonify({'new_data': True})
    else:
        print(f"Polling: Nessun aggiornamento rilevato.")
        return jsonify({'new_data': False})


# --- Rotte Principali (Rifattorizzate per DB) ---

@app.route('/')
@login_required
def dashboard():
    """Reindirizza l'utente alla pagina appropriata in base al ruolo."""
    # ... (Codice invariato) ...
    if current_user.has_role('admin'):
        return redirect(url_for('ordini_list'))
    elif current_user.has_role('preparatore'):
        return redirect(url_for('ordini_list'))
    elif current_user.has_role('autista'):
        if current_user.nome_autista:
            return redirect(url_for('consegne_autista', autista_nome=current_user.nome_autista))
        else:
            flash("Profilo autista non completamente configurato (nome mancante).", "warning")
            return redirect(url_for('autisti'))
    else:
        flash("Ruolo utente non definito o non autorizzato.", "danger")
        logout_user()
        return redirect(url_for('login'))
    
@app.route('/ordini')
@login_required
def ordini_list():
    """Mostra l'elenco degli ordini, raggruppati per data."""
    if not (current_user.has_role('admin') or current_user.has_role('preparatore')):
        flash("Accesso non autorizzato alla lista ordini.", "danger")
        return redirect(url_for('dashboard'))

    orders_map, _ = get_cached_order_data() # Ottiene la mappa degli ordini
    if orders_map is None:
        return render_template('orders.html', ordini_per_data=OrderedDict(), giorno_selezionato=None, active_page='ordini', enable_polling=False)

    giorno_filtro = request.args.get('giorno_filtro')
    filtered_orders_keys = []

    # Filtra le CHIAVI degli ordini
    if giorno_filtro:
        try:
            giorno_da_cercare = giorno_filtro.strip().zfill(2)
            if not giorno_da_cercare.isdigit() or len(giorno_da_cercare) != 2:
                raise ValueError("Formato giorno non valido.")
            
            for key, order in orders_map.items():
                if isinstance(order.get('data_documento'), str) and len(order['data_documento']) == 8 and order['data_documento'].endswith(giorno_da_cercare):
                    filtered_orders_keys.append(key)
            
            if not filtered_orders_keys:
                 flash(f"Nessun ordine trovato per il giorno '{giorno_filtro}'.", "info")

        except ValueError as e:
            flash(f"Filtro giorno non valido: {e}. Mostro tutti gli ordini.", "warning")
            filtered_orders_keys = list(orders_map.keys())
    else:
        filtered_orders_keys = list(orders_map.keys())

    # Ordina le CHIAVI per data documento
    filtered_orders_keys.sort(
        key=lambda key: orders_map.get(key, {}).get('data_documento', '0'), 
        reverse=True
    )

    # Recupera gli stati solo per gli ordini filtrati
    ordini_per_data = OrderedDict()
    if filtered_orders_keys:
        # Fai una singola query per tutti gli stati necessari
        states_db = db.session.query(PickingState).filter(
            PickingState.order_key.in_(filtered_orders_keys)
        ).all()
        states_map = {state.order_key: state for state in states_db}
    else:
        states_map = {}
        
    for key in filtered_orders_keys:
        order = orders_map[key]
        state = states_map.get(key)

        order['local_status'] = state.status if state else 'Da Lavorare'
        
        date_str = order.get('data_documento')
        data_formattata = "Data Sconosciuta"
        if isinstance(date_str, str) and len(date_str) == 8:
             try:
                data_formattata = f"{date_str[6:8]}/{date_str[4:6]}/{date_str[0:4]}"
             except IndexError: pass
        order['data_formattata'] = data_formattata

        ordini_per_data.setdefault(data_formattata, []).append(order)

    return render_template('orders.html', ordini_per_data=ordini_per_data, giorno_selezionato=giorno_filtro, active_page='ordini', enable_polling=True)


@app.route('/trasporto')
@login_required
def trasporto():
    """Pagina per l'assegnazione dei vettori agli ordini."""
    if not current_user.has_role('admin'):
        flash("Accesso non autorizzato.", "danger")
        return redirect(url_for('dashboard'))

    orders_map, _ = get_cached_order_data()
    if orders_map is None:
        return render_template('trasporto.html', ordini_per_data=OrderedDict(), vettori=[], active_page='trasporto', enable_polling=False)

    vettori = get_vettori()
    if not vettori:
        flash("Attenzione: Errore nel caricamento dei vettori.", "warning")
        vettori = []

    ordini_per_data = OrderedDict()
    # Ordina le CHIAVI
    sorted_keys = sorted(
        orders_map.keys(), 
        key=lambda key: orders_map.get(key, {}).get('data_documento', '0'), 
        reverse=True
    )

    # Recupera tutte le assegnazioni in una sola query
    assignments_db = LogisticsAssignment.query.all()
    assignments_map = {a.order_key: a for a in assignments_db}

    for key in sorted_keys:
        order = orders_map[key]
        assignment = assignments_map.get(key)
        
        if assignment:
            order['vettore_assegnato_info'] = {
                'codice': assignment.autista_codice,
                'nome': assignment.autista_nome
            }
            order['nota_autista'] = assignment.nota_autista or ''
        else:
            order['vettore_assegnato_info'] = None
            order['nota_autista'] = ''

        date_str = order.get('data_documento')
        data_formattata = "Data Sconosciuta"
        if isinstance(date_str, str) and len(date_str) == 8:
             try: data_formattata = f"{date_str[6:8]}/{date_str[4:6]}/{date_str[0:4]}"
             except IndexError: pass
        order['data_formattata'] = data_formattata

        ordini_per_data.setdefault(data_formattata, []).append(order)

    return render_template('trasporto.html', ordini_per_data=ordini_per_data, vettori=vettori, active_page='trasporto', enable_polling=True)


# --- Salvataggio Assegnazioni (Rifattorizzato per DB) ---
@app.route('/assign_all_vettori', methods=['POST'])
@login_required
def assign_all_vettori():
    """Salva le assegnazioni vettore e le note autista sul DB."""
    if not current_user.has_role('admin'):
        flash("Accesso non autorizzato.", "danger")
        return redirect(url_for('dashboard'))

    vettori = get_vettori()
    if vettori is None:
        flash("Errore nel recupero dei vettori, impossibile salvare le assegnazioni.", "danger")
        return redirect(url_for('trasporto'))
    vettori_map = {v['codice']: v.get('ragione_sociale') or v.get('descrizione', 'Sconosciuto') for v in vettori if 'codice' in v}

    updated_logistics = 0
    updated_notes = 0
    
    # Raccogli tutti i dati dal form
    form_data = request.form
    order_keys_in_form = set()
    vettore_data = {}
    nota_data = {}

    for key, value in form_data.items():
        if key.startswith('vettore_'):
            order_key = key.replace('vettore_', '')
            order_keys_in_form.add(order_key)
            vettore_data[order_key] = value.strip()
        elif key.startswith('nota_autista_'):
            order_key = key.replace('nota_autista_', '')
            order_keys_in_form.add(order_key)
            nota_data[order_key] = value.strip()

    if not order_keys_in_form:
        flash("Nessun dato ricevuto dal form.", "warning")
        return redirect(url_for('trasporto'))

    # Recupera tutti gli assignment esistenti per gli ordini nel form
    existing_assignments = LogisticsAssignment.query.filter(
        LogisticsAssignment.order_key.in_(order_keys_in_form)
    ).all()
    assignments_map = {a.order_key: a for a in existing_assignments}

    try:
        for order_key in order_keys_in_form:
            assignment = assignments_map.get(order_key)
            
            vettore_codice = vettore_data.get(order_key)
            nota = nota_data.get(order_key, '') # Nota autista
            
            vettore_nome = vettori_map.get(vettore_codice) if vettore_codice else None
            
            if not vettore_codice and not nota:
                # Se entrambi sono vuoti, cancella l'assignment se esiste
                if assignment:
                    db.session.delete(assignment)
                    updated_logistics += 1 # Conta come aggiornamento
            else:
                # Se c'è almeno un dato, crea o aggiorna
                if not assignment:
                    # Crea nuovo
                    assignment = LogisticsAssignment(
                        order_key=order_key,
                        autista_codice=vettore_codice,
                        autista_nome=vettore_nome,
                        nota_autista=nota
                    )
                    db.session.add(assignment)
                    updated_logistics += 1
                else:
                    # Aggiorna esistente se i dati sono cambiati
                    if assignment.autista_codice != vettore_codice or assignment.nota_autista != nota:
                        assignment.autista_codice = vettore_codice
                        assignment.autista_nome = vettore_nome
                        assignment.nota_autista = nota
                        updated_logistics += 1
                        
        db.session.commit()
        flash(f"Salvataggio completato. Aggiornate {updated_logistics} assegnazioni/note.", "success")
        
    except Exception as e:
        db.session.rollback()
        print(f"ERRORE [assign_all_vettori]: {e}")
        flash(f"Errore durante il salvataggio nel database: {e}", "danger")
    
    return redirect(url_for('trasporto'))


# --- Calcolo Giri (Rifattorizzato per DB) ---
@app.route('/calcola-giri')
@login_required
def calcola_giri():
    """Calcola i percorsi ottimizzati usando l'indirizzo effettivo e salva su DB."""
    if not current_user.has_role('admin'):
        flash("Accesso non autorizzato.", "danger")
        return redirect(url_for('dashboard'))

    print("\n--- DEBUG: Avvio /calcola-giri ---")

    # 1. Recupera gli ordini assegnati dal DB
    assignments = LogisticsAssignment.query.filter(
        LogisticsAssignment.autista_nome.isnot(None),
        LogisticsAssignment.autista_nome != 'Sconosciuto'
    ).all()
    
    if not assignments:
        flash("Nessun ordine assegnato ai vettori.", "info")
        print("DEBUG [calcola_giri]: Nessun ordine da processare.")
        return redirect(url_for('autisti'))
        
    # 2. Recupera i dati degli ordini dalla cache
    orders_map, _ = get_cached_order_data()
    if orders_map is None:
        flash("Errore nel caricamento dei dati degli ordini. Impossibile calcolare i giri.", "danger")
        return redirect(url_for('autisti'))

    # 3. Raggruppa ordini per vettore
    giri_per_vettore = defaultdict(list)
    print("DEBUG [calcola_giri]: Raggruppamento ordini per vettore...")
    for assign in assignments:
        ordine_completo = orders_map.get(assign.order_key)
        if ordine_completo:
            ordine_completo['_order_key'] = assign.order_key
            giri_per_vettore[assign.autista_nome].append(ordine_completo)
            print(f"  + Ordine {assign.order_key} assegnato a {assign.autista_nome}. Indirizzo: '{ordine_completo.get('indirizzo_effettivo')}'")
        else:
            print(f"WARN [calcola_giri]: Ordine {assign.order_key} non trovato nella cache.")

    # 4. Inizializza Google Maps Client
    google_api_key = os.getenv('GOOGLE_MAPS_API_KEY')
    if not google_api_key:
        flash("Errore: Chiave API Google Maps non configurata.", "danger")
        return redirect(url_for('autisti'))
    try: 
        gmaps = googlemaps.Client(key=google_api_key)
    except Exception as e: 
        flash(f"Errore inizializzazione Google Maps: {e}", "danger")
        return redirect(url_for('autisti'))

    # 5. Calcola percorso per ogni vettore
    origin = os.getenv('GMAPS_ORIGIN', "Japlab, Via Ferraris, 3, 84018 Scafati SA")
    default_stop_time_min = int(os.getenv('DEFAULT_STOP_TIME_MIN', '10'))
    total_calculated = 0
    total_errors = 0
    
    # Lista dei giri calcolati da salvare sul DB
    calculated_routes_to_save = []

    print("DEBUG [calcola_giri]: Inizio ciclo calcolo percorsi...")
    for vettore, ordini_assegnati in giri_per_vettore.items():
        if not ordini_assegnati: continue

        waypoints = []
        valid_orders_for_route = []
        print(f"\nDEBUG [calcola_giri]: Preparo waypoints per {vettore}...")
        for o in ordini_assegnati:
            addr = o.get('indirizzo_effettivo', '').strip()
            loc = o.get('localita_effettiva', '').strip()
            if addr and loc:
                waypoint_str = f"{addr}, {loc}"
                waypoints.append(waypoint_str)
                valid_orders_for_route.append(o)
                print(f"    -> Waypoint VALIDO aggiunto: '{waypoint_str}'")
            else:
                print(f"    -> Waypoint NON VALIDO. Ordine #{o.get('numero')} escluso.")
                flash(f"Ordine #{o.get('numero')} per {vettore} escluso: indirizzo/località mancante.", "warning")

        if not waypoints:
            print(f"WARN [calcola_giri]: Nessun waypoint valido trovato per {vettore}.")
            continue

        partenza_prevista = datetime.now().replace(hour=8, minute=0, second=0, microsecond=0)

        try:
            print(f"DEBUG [calcola_giri]: Chiamata Google Maps API per {vettore}...")
            directions_result = gmaps.directions(
                origin=origin, destination=origin, waypoints=waypoints,
                optimize_waypoints=True, mode="driving",
            )
            
            if not directions_result or not isinstance(directions_result, list) or not directions_result[0].get('legs'):
                raise ValueError("Risposta API Google Maps non valida o vuota.")

            route = directions_result[0]
            google_waypoint_order_indices = route.get('waypoint_order', [])
            
            tappe_ordinate_oggetti = []
            for index in google_waypoint_order_indices:
                 if 0 <= index < len(valid_orders_for_route):
                     tappe_ordinate_oggetti.append(valid_orders_for_route[index])
                 else:
                     print(f"ERRORE [calcola_giri]: Indice waypoint {index} non valido!")

            distanza_complessiva_m = sum(leg.get('distance', {}).get('value', 0) for leg in route['legs'])
            durata_guida_sec = sum(leg.get('duration', {}).get('value', 0) for leg in route['legs'])
            tempo_soste_sec = len(tappe_ordinate_oggetti) * default_stop_time_min * 60
            durata_totale_stimata_sec = durata_guida_sec + tempo_soste_sec
            rientro_previsto = partenza_prevista + timedelta(seconds=durata_totale_stimata_sec)

            orario_tappa_corrente = partenza_prevista
            for i, tappa_obj in enumerate(tappe_ordinate_oggetti):
                if i < len(route['legs']):
                    leg_duration_sec = route['legs'][i].get('duration', {}).get('value', 0)
                    orario_tappa_corrente += timedelta(seconds=leg_duration_sec)
                    tappa_obj['orario_previsto'] = orario_tappa_corrente.strftime('%H:%M')
                    orario_tappa_corrente += timedelta(minutes=default_stop_time_min)
                else:
                    tappa_obj['orario_previsto'] = "Rientro"

            # Prepara l'oggetto da salvare nel DB
            route_data_to_save = {
                'data': datetime.now().strftime('%d/%m/%Y'),
                'partenza_stimata': partenza_prevista.strftime('%H:%M'),
                'num_consegne': len(tappe_ordinate_oggetti),
                'km_previsti': f"{distanza_complessiva_m / 1000:.1f} km",
                'tempo_guida_stimato': time.strftime("%Hh %Mm", time.gmtime(durata_guida_sec)),
                'tempo_soste_stimato': time.strftime("%Hh %Mm", time.gmtime(tempo_soste_sec)),
                'tempo_totale_stimato': time.strftime("%Hh %Mm", time.gmtime(durata_totale_stimata_sec)),
                'rientro_previsto': rientro_previsto.strftime('%H:%M'),
                'tappe': tappe_ordinate_oggetti, # Questa è una lista di dizionari
            }
            
            calculated_routes_to_save.append({
                'autista_nome': vettore,
                'route_data_json': json.dumps(route_data_to_save) # Serializza in JSON
            })
            
            print(f"INFO [calcola_giri]: Percorso calcolato con successo per {vettore}.")
            total_calculated += 1

        except Exception as e:
            total_errors += 1
            print(f"ERRORE calcolo percorso per {vettore}: {e}")
            flash(f"Errore calcolo percorso per {vettore}: {e}", "danger")

    # 6. Salva tutti i giri calcolati sul DB
    if calculated_routes_to_save:
        try:
            # Pulisci i giri vecchi
            db.session.query(CalculatedRoute).delete()
            print("DEBUG [calcola_giri]: Vecchi giri calcolati eliminati dal DB.")
            
            # Aggiungi i nuovi
            for route_data in calculated_routes_to_save:
                route_obj = CalculatedRoute(
                    autista_nome=route_data['autista_nome'],
                    route_data_json=route_data['route_data_json'],
                    last_calculated=datetime.utcnow()
                )
                db.session.add(route_obj)
            
            db.session.commit()
            print(f"DEBUG [calcola_giri]: {len(calculated_routes_to_save)} nuovi giri salvati sul DB.")
        except Exception as e:
            db.session.rollback()
            print(f"ERRORE CRITICO [calcola_giri]: Impossibile salvare i giri calcolati sul DB: {e}")
            flash("Errore nel salvataggio dei giri calcolati.", "danger")
            total_errors += 1

    flash(f"Calcolo giri completato: {total_calculated} successi, {total_errors} errori.", "info" if total_errors == 0 else "warning")
    print("--- DEBUG: Fine /calcola-giri ---\n")
    return redirect(url_for('autisti'))


# --- Rotte Autisti e Consegne (Rifattorizzate per DB) ---

@app.route('/autisti')
@login_required
def autisti():
    """Mostra l'elenco degli autisti con giri calcolati dal DB."""
    if not (current_user.has_role('admin') or current_user.has_role('autista')):
        flash("Accesso non autorizzato.", "danger")
        return redirect(url_for('dashboard'))

    # Leggi giri calcolati dal DB
    giri_calcolati_db = CalculatedRoute.query.order_by(CalculatedRoute.autista_nome).all()
    
    giri_calcolati_dict = {}
    for giro in giri_calcolati_db:
        try:
            # Deserializza il JSON per passarlo al template
            giri_calcolati_dict[giro.autista_nome] = json.loads(giro.route_data_json)
        except Exception as e:
            print(f"ERRORE [autisti]: Impossibile deserializzare giro per {giro.autista_nome}: {e}")
            
    # Trova autisti assegnati ma senza giro
    autisti_assegnati = db.session.query(LogisticsAssignment.autista_nome).distinct().filter(
        LogisticsAssignment.autista_nome.isnot(None),
        LogisticsAssignment.autista_nome != 'Sconosciuto'
    ).all()
    
    autisti_assegnati_set = {nome for (nome,) in autisti_assegnati}
    autisti_senza_giro = autisti_assegnati_set - set(giri_calcolati_dict.keys())

    return render_template('autisti.html',
                           giri=giri_calcolati_dict,
                           autisti_senza_giro=sorted(list(autisti_senza_giro)),
                           active_page='autisti')


@app.route('/consegne/<autista_nome>')
@login_required
def consegne_autista(autista_nome):
    """Mostra il dettaglio del giro e delle tappe per un autista, leggendo dal DB."""
    is_admin = current_user.has_role('admin')
    is_correct_driver = current_user.has_role('autista') and current_user.nome_autista == autista_nome
    if not (is_admin or is_correct_driver):
        flash("Accesso non autorizzato.", "danger")
        return redirect(url_for('dashboard'))

    print(f"\n--- DEBUG: Preparazione dati per /consegne/{autista_nome} ---")

    giro_calcolato = None
    tappe_da_mostrare = []

    # 1. Recupera il giro calcolato dal DB
    giro_db = CalculatedRoute.query.get(autista_nome)
    
    if giro_db:
        try:
            giro_calcolato = json.loads(giro_db.route_data_json)
            tappe_da_mostrare = giro_calcolato.get('tappe', [])
            print(f"DEBUG: Uso le {len(tappe_da_mostrare)} tappe dal giro calcolato in DB per {autista_nome}.")
        except Exception as e:
            print(f"ERRORE [consegne_autista]: Impossibile deserializzare giro per {autista_nome}: {e}")
            giro_calcolato = None
    
    # 2. Se il giro non è calcolato, recupera gli ordini assegnati
    if not giro_calcolato:
        print(f"DEBUG: Giro non calcolato. Cerco ordini assegnati a {autista_nome}...")
        assignments = LogisticsAssignment.query.filter_by(autista_nome=autista_nome).all()
        order_keys_assegnati = [a.order_key for a in assignments]
        
        if order_keys_assegnati:
            orders_map, _ = get_cached_order_data()
            if orders_map:
                for key in order_keys_assegnati:
                    ordine_completo = orders_map.get(key)
                    if ordine_completo:
                        ordine_completo['_order_key'] = key
                        tappe_da_mostrare.append(ordine_completo)
                print(f"  + Aggiunti {len(tappe_da_mostrare)} ordini (senza giro)")
                tappe_da_mostrare.sort(key=lambda x: x.get('numero', 0))
        
        if not tappe_da_mostrare:
            flash(f"Nessun ordine assegnato o giro calcolato trovato per {autista_nome}.", "warning")
        else:
            flash(f"Giro non ancora calcolato per {autista_nome}. Mostro elenco ordini assegnati.", "info")

    # 3. Arricchisci le tappe con dati di stato dal DB
    order_keys = [t.get('_order_key') or f"{t.get('sigla','?')}:{t.get('serie','?')}:{t.get('numero','?')}" for t in tappe_da_mostrare]
    
    if order_keys:
        events_db = DeliveryEvent.query.filter(DeliveryEvent.order_key.in_(order_keys)).all()
        events_map = {e.order_key: e for e in events_db}
        
        statuses_db = PickingState.query.filter(PickingState.order_key.in_(order_keys)).all()
        statuses_map = {s.order_key: s for s in statuses_db}
        
        # Le note sono già negli assignment, ma le ricarichiamo per sicurezza se il giro è calcolato
        notes_db = LogisticsAssignment.query.filter(LogisticsAssignment.order_key.in_(order_keys)).all()
        notes_map = {n.order_key: n.nota_autista for n in notes_db}

    print(f"DEBUG: Arricchimento di {len(tappe_da_mostrare)} tappe...")
    for i, tappa in enumerate(tappe_da_mostrare):
        order_key = tappa.get('_order_key')
        
        evento = events_map.get(order_key)
        status_ordine_picking = statuses_map.get(order_key)

        tappa['start_time'] = evento.start_time_str if evento else None
        tappa['end_time'] = evento.end_time_str if evento else None
        
        if tappa['start_time'] and tappa['end_time']:
             try:
                 start_dt = datetime.strptime(tappa['start_time'], '%H:%M:%S')
                 end_dt = datetime.strptime(tappa['end_time'], '%H:%M:%S')
                 durata_td = end_dt - start_dt
                 durata_sec = durata_td.total_seconds()
                 if durata_sec < 0: durata_sec += 24 * 3600
                 tappa['durata_effettiva_min'] = math.ceil(durata_sec / 60)
             except (ValueError, TypeError): tappa['durata_effettiva_min'] = None
        else: 
            tappa['durata_effettiva_min'] = None

        tappa['colli_da_consegnare'] = status_ordine_picking.colli_totali_operatore if status_ordine_picking else 'N/D'
        tappa['nota_autista'] = notes_map.get(order_key, '')
        
        if tappa['end_time']: tappa['status_consegna'] = 'Completata'
        elif tappa['start_time']: tappa['status_consegna'] = 'In Corso'
        else: tappa['status_consegna'] = 'Da Iniziare'

        if 'indirizzo_effettivo' not in tappa: tappa['indirizzo_effettivo'] = tappa.get('indirizzo', 'N/D')
        if 'localita_effettiva' not in tappa: tappa['localita_effettiva'] = tappa.get('localita', 'N/D')

    print(f"--- DEBUG: Fine preparazione dati per /consegne/{autista_nome} ---\n")

    return render_template('consegna_autista.html',
                           autista_nome=autista_nome,
                           giro=giro_calcolato,
                           tappe=tappe_da_mostrare)


# --- Spostamento Tappe (Rifattorizzato per DB) ---
@app.route('/move_tappa/<autista_nome>/<int:index>/<direction>', methods=['POST'])
@login_required
def move_tappa(autista_nome, index, direction):
    """Sposta una tappa su o giù nell'ordine del giro calcolato sul DB."""
    is_admin = current_user.has_role('admin')
    is_correct_driver = current_user.has_role('autista') and current_user.nome_autista == autista_nome
    if not (is_admin or is_correct_driver):
        flash("Accesso non autorizzato.", "danger")
        return redirect(url_for('consegne_autista', autista_nome=autista_nome))

    if direction not in ['up', 'down']:
         flash("Direzione non valida.", "danger")
         return redirect(url_for('consegne_autista', autista_nome=autista_nome))

    try:
        giro_db = CalculatedRoute.query.get(autista_nome)
        if not giro_db:
            flash("Impossibile modificare: giro non calcolato.", "warning")
            return redirect(url_for('consegne_autista', autista_nome=autista_nome))

        # Deserializza, modifica, riserializza
        giro_data = json.loads(giro_db.route_data_json)
        tappe = giro_data.get('tappe', [])
        
        if not (0 <= index < len(tappe)):
            flash("Indice tappa non valido.", "danger")
            return redirect(url_for('consegne_autista', autista_nome=autista_nome))

        tappa_da_spostare = tappe.pop(index)
        nuovo_index = -1

        if direction == 'up' and index > 0:
            nuovo_index = index - 1
        elif direction == 'down' and index < len(tappe):
            nuovo_index = index

        if nuovo_index != -1 and 0 <= nuovo_index <= len(tappe):
             tappe.insert(nuovo_index, tappa_da_spostare)
             giro_data['tappe'] = tappe # Reinserisci le tappe modificate
             giro_db.route_data_json = json.dumps(giro_data) # Riserializza
             db.session.commit() # Salva sul DB
             flash('Ordine tappe aggiornato.', 'success')
        else:
             flash('Spostamento tappa non possibile.', 'warning')

    except Exception as e:
        db.session.rollback()
        print(f"ERRORE [move_tappa]: {e}")
        flash("Errore durante l'aggiornamento del giro.", "danger")

    return redirect(url_for('consegne_autista', autista_nome=autista_nome))


# --- Start/End Consegna (Rifattorizzato per DB) ---
@app.route('/consegna/start', methods=['POST'])
@login_required
def start_consegna():
    """Registra l'orario di inizio di una consegna sul DB."""
    is_admin = current_user.has_role('admin')
    is_driver = current_user.has_role('autista')
    autista_nome_form = request.form.get('autista_nome')
    is_correct_driver = is_driver and current_user.nome_autista == autista_nome_form
    if not (is_admin or is_correct_driver):
         flash("Accesso non autorizzato.", "danger")
         target_autista = autista_nome_form if autista_nome_form else (current_user.nome_autista if is_driver else None)
         return redirect(url_for('consegne_autista', autista_nome=target_autista) if target_autista else url_for('dashboard'))

    order_key = request.form.get('order_key')
    if not order_key:
        flash("Errore: Chiave ordine mancante.", "danger")
        return redirect(url_for('consegne_autista', autista_nome=autista_nome_form))

    timestamp_inizio = datetime.now().strftime('%H:%M:%S')

    try:
        evento = DeliveryEvent.query.get(order_key)
        if not evento:
            evento = DeliveryEvent(order_key=order_key, start_time_str=timestamp_inizio)
            db.session.add(evento)
            flash(f"Consegna {order_key} iniziata alle {timestamp_inizio}.", "info")
        elif not evento.start_time_str:
            evento.start_time_str = timestamp_inizio
            flash(f"Consegna {order_key} iniziata alle {timestamp_inizio}.", "info")
        else:
            flash(f"Consegna {order_key} già iniziata precedentemente.", "warning")
            
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"ERRORE [start_consegna]: {e}")
        flash("Errore database durante l'avvio della consegna.", "danger")

    return redirect(url_for('consegne_autista', autista_nome=autista_nome_form))


@app.route('/consegna/end', methods=['POST'])
@login_required
def end_consegna():
    """Registra l'orario di fine consegna sul DB e invia notifica."""
    is_admin = current_user.has_role('admin')
    is_driver = current_user.has_role('autista')
    autista_nome_form = request.form.get('autista_nome')
    is_correct_driver = is_driver and current_user.nome_autista == autista_nome_form
    if not (is_admin or is_correct_driver):
         flash("Accesso non autorizzato.", "danger")
         target_autista = autista_nome_form if autista_nome_form else (current_user.nome_autista if is_driver else None)
         return redirect(url_for('consegne_autista', autista_nome=target_autista) if target_autista else url_for('dashboard'))

    order_key = request.form.get('order_key')
    if not order_key:
        flash("Errore: Chiave ordine mancante.", "danger")
        return redirect(url_for('consegne_autista', autista_nome=autista_nome_form))

    timestamp_fine = datetime.now().strftime('%H:%M:%S')
    nome_cliente_notifica = 'Cliente Sconosciuto'
    send_notification_flag = False

    try:
        evento = DeliveryEvent.query.get(order_key)
        if not evento or not evento.start_time_str:
            flash(f"Errore: Impossibile completare consegna {order_key} senza un orario di inizio.", "danger")
        elif evento.end_time_str:
            flash(f"Consegna {order_key} già completata precedentemente.", "warning")
        else:
            evento.end_time_str = timestamp_fine
            db.session.commit()
            
            # Recupera nome cliente per notifica (dalla cache ordini)
            orders_map, _ = get_cached_order_data()
            if orders_map:
                ordine = orders_map.get(order_key)
                if ordine:
                    nome_cliente_notifica = ordine.get('ragione_sociale', 'Cliente Sconosciuto')
            
            flash(f"Consegna per {nome_cliente_notifica} ({order_key}) completata alle {timestamp_fine}.", "success")
            send_notification_flag = True
            
    except Exception as e:
        db.session.rollback()
        print(f"ERRORE [end_consegna]: {e}")
        flash("Errore database durante la chiusura della consegna.", "danger")

    # --- INVIO NOTIFICA (fuori dalla transazione DB) ---
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


# --- Amministrazione (Rifattorizzato per DB) ---
def _calculate_admin_summary_data():
    """
    Calcola statistiche riassuntive per la dashboard admin, leggendo dal DB.
    """
    # Esegui le query sul DB
    try:
        assignments_db = LogisticsAssignment.query.all()
        events_db = DeliveryEvent.query.all()
        routes_db = CalculatedRoute.query.all()
        statuses_db = PickingState.query.all()
        
        # Recupera dati ordini (ragione sociale, indirizzi) dalla cache
        orders_map, _ = get_cached_order_data()
        if orders_map is None:
            orders_map = {} # Evita crash se API Mexal fallisce
            print("WARN [admin_summary]: Mappa ordini vuota, i nomi dei clienti potrebbero mancare.")
            
    except Exception as e:
        print(f"ERRORE CRITICO [admin_summary] query DB: {e}")
        # Restituisci dati vuoti per evitare crash del template
        return {}, {}, {'labels':[], 'data':[]}, []

    # Mappe per un accesso rapido
    events_map = {e.order_key: e for e in events_db}
    statuses_map = {s.order_key: s for s in statuses_db}
    routes_map = {r.autista_nome: json.loads(r.route_data_json) for r in routes_db}

    dettagli_per_autista = {}
    consegne_totali_completate = 0
    consegne_totali_in_corso = 0
    tempo_totale_effettivo_sec = 0
    km_totali_previsti = 0.0
    consegne_per_ora = defaultdict(int)

    # Itera su TUTTE le assegnazioni logistiche
    for assign in assignments_db:
        autista_nome = assign.autista_nome
        if not autista_nome or autista_nome == 'Sconosciuto':
            continue
            
        order_key = assign.order_key
        evento = events_map.get(order_key)
        ordine = orders_map.get(order_key, {}) # Prendi dalla cache
        status_ordine_picking = statuses_map.get(order_key)

        if autista_nome not in dettagli_per_autista:
             giro_pianificato = routes_map.get(autista_nome, {})
             dettagli_per_autista[autista_nome] = {
                 'summary': giro_pianificato, # Contiene già i dati del giro
                 'consegne': [],
                 'tempo_effettivo_sec': 0
             }

        status_consegna = "Assegnata"
        durata_effettiva_str = "-"
        ora_inizio = -1

        start_time_str = evento.start_time_str if evento else None
        end_time_str = evento.end_time_str if evento else None

        if start_time_str:
            status_consegna = "In Corso"
            if not end_time_str:
                consegne_totali_in_corso += 1
            try:
                start_dt = datetime.strptime(start_time_str, '%H:%M:%S')
                ora_inizio = start_dt.hour
            except (ValueError, TypeError): pass

        if start_time_str and end_time_str:
            status_consegna = "Completata"
            consegne_totali_completate += 1
            try:
                start_dt = datetime.strptime(start_time_str, '%H:%M:%S')
                end_dt = datetime.strptime(end_time_str, '%H:%M:%S')
                durata_td = end_dt - start_dt
                durata_sec = durata_td.total_seconds()
                if durata_sec < 0: durata_sec += 24 * 3600
                dettagli_per_autista[autista_nome]['tempo_effettivo_sec'] += durata_sec
                tempo_totale_effettivo_sec += durata_sec
                durata_min = math.ceil(durata_sec / 60)
                durata_effettiva_str = f"{durata_min} min"
                if ora_inizio != -1: consegne_per_ora[ora_inizio] += 1
            except (ValueError, TypeError) as e:
                print(f"Errore calcolo durata consegna per {order_key}: {e}")
                pass

        dettaglio_consegna = {
            'ragione_sociale': ordine.get('ragione_sociale', 'N/D'),
            'indirizzo': ordine.get('indirizzo_effettivo', ordine.get('indirizzo', '-')),
            'localita': ordine.get('localita_effettiva', ordine.get('localita', '-')),
            'start_time_reale': start_time_str or '-',
            'end_time_reale': end_time_str or '-',
            'durata_effettiva': durata_effettiva_str,
            'colli': status_ordine_picking.colli_totali_operatore if status_ordine_picking else 'N/D',
            'status': status_consegna,
            'pdf_filename': status_ordine_picking.pdf_filename if status_ordine_picking else None
        }
        dettagli_per_autista[autista_nome]['consegne'].append(dettaglio_consegna)

    # Formatta tempi totali e calcola km
    for autista_nome, dettagli in dettagli_per_autista.items():
         tempo_sec = dettagli['tempo_effettivo_sec']
         dettagli['summary']['tempo_totale_reale'] = time.strftime("%Hh %Mm", time.gmtime(tempo_sec)) if tempo_sec > 0 else "0h 0m"
         try:
            giro_pianificato = dettagli.get('summary', {})
            km_str = giro_pianificato.get('km_previsti', '0 km').split(' ')[0]
            km_autista = float(km_str) if km_str else 0.0
            km_totali_previsti += km_autista
         except ValueError: pass

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

    # Prepara dati per il grafico
    ore_grafico = list(range(7, 21))
    conteggi_grafico = [consegne_per_ora.get(h, 0) for h in ore_grafico]
    chart_data = {'labels': [f"{h}:00" for h in ore_grafico], 'data': conteggi_grafico}

    # Crea la lista di tutti i PDF (usa la mappa degli stati già caricata)
    all_generated_pdfs_list = []
    for state in statuses_db:
        if state.pdf_filename:
            ordine = orders_map.get(state.order_key, {})
            all_generated_pdfs_list.append({
                'filename': state.pdf_filename,
                'client_name': ordine.get('ragione_sociale', 'Cliente Sconosciuto'),
                'order_id': state.order_id
            })
    
    all_generated_pdfs_list.sort(key=lambda x: x['filename'], reverse=True)

    return summary_stats, dettagli_per_autista, chart_data, all_generated_pdfs_list


@app.route('/amministrazione')
@login_required
def amministrazione():
    """Pagina riepilogativa per l'amministratore (legge dal DB)."""
    if not current_user.has_role('admin'):
        flash("Accesso non autorizzato.", "danger")
        return redirect(url_for('dashboard'))

    try:
        summary_stats, dettagli_per_autista, chart_data, pdf_list = _calculate_admin_summary_data()
    except Exception as e:
         print(f"Errore in _calculate_admin_summary_data: {e}")
         import traceback; traceback.print_exc()
         flash("Errore durante il calcolo delle statistiche amministrative.", "danger")
         summary_stats, dettagli_per_autista, chart_data, pdf_list = {}, {}, {'labels':[], 'data':[]}, []

    return render_template('amministrazione.html',
                           summary_stats=summary_stats,
                           dettagli_per_autista=dettagli_per_autista,
                           chart_data=chart_data,
                           pdf_list=pdf_list,
                           active_page='amministrazione')


# --- Dettaglio Ordine (Rifattorizzato per DB) ---
@app.route('/order/<sigla>/<serie>/<numero>')
@login_required
def order_detail_view(sigla, serie, numero):
    """Mostra i dettagli dell'ordine, leggendo lo stato dal DB."""
    if not (current_user.has_role('admin') or current_user.has_role('preparatore')):
        flash("Accesso non autorizzato.", "danger")
        return redirect(url_for('dashboard'))

    order_key = f"{sigla}:{serie}:{numero}"
    order_id = str(numero) # order_id è solo il numero

    # 1. Recupera i dati dell'ordine (immutabili) dalla cache
    orders_map, _ = get_cached_order_data()
    if orders_map is None:
        flash("Errore nel caricamento dei dati ordine, riprova.", "danger")
        return redirect(url_for('ordini_list'))
        
    order_data = orders_map.get(order_key)

    if not order_data:
        flash(f"Errore: Impossibile trovare l'ordine {order_key}.", "danger")
        # Invalida la cache e ricarica
        _cache["orders_map"] = None
        _cache["last_load_time"] = None
        return redirect(url_for('ordini_list'))
    
    # 2. Recupera lo stato (mutabile) dal DB
    order_state_db = PickingState.query.get(order_key)
    
    if not order_state_db:
        # Questo non dovrebbe succedere se load_all_data() ha funzionato
        print(f"WARN [order_detail_view]: Stato non trovato nel DB per {order_key}. Lo creo al volo.")
        try:
            order_state_db = PickingState(order_key=order_key, order_id=order_id)
            db.session.add(order_state_db)
            db.session.commit()
            flash("Stato ordine inizializzato.", "info")
        except Exception as e:
            db.session.rollback()
            print(f"ERRORE [order_detail_view]: Impossibile creare stato per {order_key}: {e}")
            flash("Errore critico nel DB, impossibile caricare lo stato.", "danger")
            return redirect(url_for('ordini_list'))

    # 3. Deserializza i JSON per il template
    try:
        packing_list = json.loads(order_state_db.packing_list_json or '[]')
        picked_items = json.loads(order_state_db.picked_items_json or '{}')
    except json.JSONDecodeError:
        print(f"ERRORE [order_detail_view]: JSON corrotto nel DB per {order_key}. Resetto.")
        packing_list = []
        picked_items = {}
        # Salva lo stato resettato
        try:
            order_state_db.packing_list_json = '[]'
            order_state_db.picked_items_json = '{}'
            db.session.commit()
        except Exception:
            db.session.rollback()

    # Crea un dizionario "state" per il template
    order_state_dict = {
        'status': order_state_db.status,
        'colli_totali_operatore': order_state_db.colli_totali_operatore,
        'pdf_filename': order_state_db.pdf_filename,
        'packing_list': packing_list,
        'picked_items': picked_items
    }

    return render_template('order_detail.html',
                           order=order_data, # Dati ordine (righe, cliente...)
                           state=order_state_dict) # Stato picking (status, packing_list...)


# --- Funzioni API Picking (Rifattorizzate per DB) ---
#    (Queste ora sono più complesse perché leggono e scrivono JSON dal DB)

def _add_item_to_collo_helper(sigla, serie, numero, collo_id, primary_code):
    """
    Funzione helper per aggiungere un articolo a un collo (leggendo e scrivendo dal DB).
    """
    order_key = f"{sigla}:{serie}:{numero}"
    order_id = str(numero)

    try:
        # 1. Recupera lo stato dal DB
        state = PickingState.query.get(order_key)
        if not state:
            return jsonify({'status': 'error', 'message': 'Stato ordine non trovato nel DB'}), 404
        
        # 2. Recupera i dati dell'ordine dalla cache
        orders_map, _ = get_cached_order_data()
        order_data = orders_map.get(order_key)
        if not order_data:
            return jsonify({'status': 'error', 'message': 'Dati ordine non trovati in cache'}), 404

        # 3. Deserializza la packing list e il riepilogo
        try:
            packing_list = json.loads(state.packing_list_json or '[]')
            picked_items = json.loads(state.picked_items_json or '{}')
        except json.JSONDecodeError:
            print(f"ERRORE JSON [add_item]: JSON corrotto per {order_key}. Resetto.")
            packing_list = []
            picked_items = {}

        # 4. Verifica articolo e qta target (come prima)
        articolo_in_ordine = False
        target_row_id = None
        qta_target_totale = 0.0
        righe_ordine_originali = order_data.get('righe', [])
        for item in righe_ordine_originali:
            if item.get('codice_articolo') == primary_code:
                articolo_in_ordine = True
                target_row_id = str(item.get('id_riga'))
                # Calcola qta target (come prima)
                nr_colli_val = 0.0; quantita_per_collo_val = 0.0
                if item.get('nr_colli') is not None and str(item.get('nr_colli')).strip() != '': 
                    try: nr_colli_val = float(str(item.get('nr_colli')).replace(',', '.'))
                    except ValueError: nr_colli_val = 0.0
                if item.get('quantita') is not None and str(item.get('quantita')).strip() != '': 
                    try: quantita_per_collo_val = float(str(item.get('quantita')).replace(',', '.'))
                    except ValueError: quantita_per_collo_val = 0.0
                qta_target_totale = (nr_colli_val * quantita_per_collo_val) if nr_colli_val > 0 else quantita_per_collo_val
                qta_target_totale = round(qta_target_totale)
                break

        if not articolo_in_ordine:
             return jsonify({'status': 'item_not_in_order', 'message': f"Articolo '{primary_code}' non presente in questo ordine."}), 404
        
        # 5. Trova (o crea) il collo
        collo_da_aggiornare = None
        for collo in packing_list:
            if collo.get('collo_id') == collo_id:
                collo_da_aggiornare = collo; break
        
        if not collo_da_aggiornare:
            # Questo non dovrebbe succedere, create_new_collo dovrebbe essere chiamato prima
            print(f"WARN [add_item]: Collo {collo_id} non trovato, creazione in corso...")
            collo_da_aggiornare = {'collo_id': collo_id, 'items': {}}
            packing_list.append(collo_da_aggiornare)
            
        # 6. Incrementa la quantità
        if 'items' not in collo_da_aggiornare: collo_da_aggiornare['items'] = {}
        qta_attuale_nel_collo = collo_da_aggiornare['items'].get(primary_code, 0)
        qta_attuale_nel_collo += 1
        collo_da_aggiornare['items'][primary_code] = qta_attuale_nel_collo

        # 7. Aggiorna il riepilogo 'picked_items'
        qta_totale_prelevata = 0
        for collo in packing_list:
             qta_totale_prelevata += collo.get('items', {}).get(primary_code, 0)
        
        if target_row_id:
             picked_items[target_row_id] = qta_totale_prelevata
        
        # 8. Verifica overpick (come prima)
        message = f"Aggiunto 1 Pz a Collo {collo_id} (Tot. {int(qta_totale_prelevata)}/{int(qta_target_totale)} Pz)"
        status = 'success'
        if qta_totale_prelevata > qta_target_totale:
            message = f"Attenzione! Qta prelevata ({int(qta_totale_prelevata)}) supera ordinato ({int(qta_target_totale)})!"
            status = 'warning_overpick'
        elif qta_totale_prelevata == qta_target_totale:
             message = f"Articolo {primary_code} completato! (Tot. {int(qta_totale_prelevata)}/{int(qta_target_totale)} Pz)"
             status = 'success_completed'

        # 9. Serializza e SALVA SUL DB
        state.packing_list_json = json.dumps(packing_list)
        state.picked_items_json = json.dumps(picked_items)
        db.session.commit()

        # Restituisci i dati aggiornati
        return jsonify({
            'status': status,
            'message': message,
            'packing_list': packing_list,
            'picked_items': picked_items
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"ERRORE CRITICO [add_item_helper] per {order_key}: {e}")
        import traceback; traceback.print_exc()
        return jsonify({'status': 'error', 'message': f"Errore server: {e}"}), 500

# Le tre funzioni API (scan, add, remove) chiamano l'helper, quindi non serve modificarle
@app.route('/api/scan-barcode/<sigla>/<int:serie>/<int:numero>/collo/<int:collo_id>', methods=['POST'])
@login_required
def scan_barcode_for_collo(sigla, serie, numero, collo_id):
    if not (current_user.has_role('admin') or current_user.has_role('preparatore')):
        return jsonify({'status': 'error', 'message': 'Accesso non autorizzato'}), 403
    data = request.json
    barcode = data.get('barcode', '').strip()
    if not barcode:
        return jsonify({'status': 'error', 'message': 'Barcode mancante'}), 400
    
    primary_code = find_article_code_by_alt_code(barcode)
    if not primary_code:
        temp_details = get_article_details(barcode)
        if temp_details and temp_details.get('codice') == barcode:
             primary_code = barcode
        else:
             return jsonify({'status': 'not_found', 'message': f"Articolo non trovato per barcode '{barcode}'."}), 404
    
    return _add_item_to_collo_helper(sigla, serie, numero, collo_id, primary_code)

@app.route('/api/order/<sigla>/<int:serie>/<int:numero>/collo/<int:collo_id>/item/add', methods=['POST'])
@login_required
def add_item_to_collo_by_code(sigla, serie, numero, collo_id):
    if not (current_user.has_role('admin') or current_user.has_role('preparatore')):
        return jsonify({'status': 'error', 'message': 'Accesso non autorizzato'}), 403
    data = request.json
    article_code = data.get('article_code', '').strip()
    if not article_code:
        return jsonify({'status': 'error', 'message': 'Codice Articolo mancante'}), 400
    
    return _add_item_to_collo_helper(sigla, serie, numero, collo_id, article_code)

@app.route('/api/order/<sigla>/<int:serie>/<int:numero>/collo/create', methods=['POST'])
@login_required
def create_new_collo(sigla, serie, numero):
    """Crea un nuovo collo vuoto per l'ordine (sul DB)."""
    if not (current_user.has_role('admin') or current_user.has_role('preparatore')):
        return jsonify({'status': 'error', 'message': 'Accesso non autorizzato'}), 403

    order_key = f"{sigla}:{serie}:{numero}"
    
    try:
        state = PickingState.query.get(order_key)
        if not state:
            return jsonify({'status': 'error', 'message': 'Ordine non trovato'}), 404
        
        packing_list = json.loads(state.packing_list_json or '[]')
        
        new_collo_id = 1
        if packing_list:
            try:
                max_id = max(c.get('collo_id', 0) for c in packing_list)
                new_collo_id = max_id + 1
            except ValueError: pass
        
        new_collo = {'collo_id': new_collo_id, 'items': {}}
        packing_list.append(new_collo)
        
        # Salva sul DB
        state.packing_list_json = json.dumps(packing_list)
        db.session.commit()
        
        print(f"DEBUG [create_collo]: Creato Collo {new_collo_id} per ordine {order_key}")
        
        return jsonify({
            'status': 'success',
            'new_collo_id': new_collo_id,
            'packing_list': packing_list # Restituisce la lista aggiornata
        })
    except Exception as e:
        db.session.rollback()
        print(f"ERRORE [create_new_collo] per {order_key}: {e}")
        return jsonify({'status': 'error', 'message': f'Errore server: {e}'}), 500

@app.route('/api/order/<sigla>/<int:serie>/<int:numero>/collo/<int:collo_id>/item/remove', methods=['POST'])
@login_required
def remove_item_from_collo(sigla, serie, numero, collo_id):
    """Rimuove 1 pezzo di un articolo da un collo (sul DB)."""
    if not (current_user.has_role('admin') or current_user.has_role('preparatore')):
        return jsonify({'status': 'error', 'message': 'Accesso non autorizzato'}), 403
        
    data = request.json
    article_code = data.get('article_code')
    if not article_code:
         return jsonify({'status': 'error', 'message': 'Codice articolo mancante'}), 400

    order_key = f"{sigla}:{serie}:{numero}"
    print(f"Richiesta rimozione 1 pz di '{article_code}' da Collo {collo_id}, Ordine {order_key}")

    try:
        state = PickingState.query.get(order_key)
        if not state:
            return jsonify({'status': 'error', 'message': 'Stato ordine non trovato'}), 404
            
        orders_map, _ = get_cached_order_data()
        order_data = orders_map.get(order_key, {})

        packing_list = json.loads(state.packing_list_json or '[]')
        picked_items = json.loads(state.picked_items_json or '{}')
        
        collo_da_aggiornare = None
        for collo in packing_list:
            if collo.get('collo_id') == collo_id:
                collo_da_aggiornare = collo
                break
        
        if not collo_da_aggiornare or 'items' not in collo_da_aggiornare:
             return jsonify({'status': 'error', 'message': f"Collo {collo_id} non trovato o vuoto."}), 404
             
        qta_attuale_nel_collo = collo_da_aggiornare['items'].get(article_code, 0)
        
        if qta_attuale_nel_collo <= 0:
            if article_code in collo_da_aggiornare['items']:
                 del collo_da_aggiornare['items'][article_code]
                 state.packing_list_json = json.dumps(packing_list) # Salva la pulizia
                 db.session.commit()
            return jsonify({
                'status': 'success',
                'message': f"Articolo {article_code} non presente nel collo {collo_id}.",
                'packing_list': packing_list,
                'picked_items': picked_items
            })
            
        # Riduci quantità di 1
        qta_attuale_nel_collo -= 1
        
        if qta_attuale_nel_collo == 0:
            del collo_da_aggiornare['items'][article_code]
        else:
            collo_da_aggiornare['items'][article_code] = qta_attuale_nel_collo
        
        # Aggiorna il riepilogo 'picked_items'
        target_row_id = None
        for item in order_data.get('righe', []):
             if item.get('codice_articolo') == article_code:
                 target_row_id = str(item.get('id_riga'))
                 break

        qta_totale_prelevata = 0
        for collo in packing_list:
             qta_totale_prelevata += collo.get('items', {}).get(article_code, 0)
        
        if target_row_id:
             picked_items[target_row_id] = qta_totale_prelevata
        
        # Salva tutto sul DB
        state.packing_list_json = json.dumps(packing_list)
        state.picked_items_json = json.dumps(picked_items)
        db.session.commit()
        
        return jsonify({
            'status': 'success',
            'message': f"Rimosso 1 pz di {article_code} da Collo {collo_id}",
            'packing_list': packing_list,
            'picked_items': picked_items
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"ERRORE [remove_item] per {order_key}: {e}")
        return jsonify({'status': 'error', 'message': f'Errore server: {e}'}), 500

# --- Azioni Ordine (Rifattorizzato per DB) ---
@app.route('/order/<sigla>/<serie>/<numero>/action', methods=['POST'])
@login_required
def order_action(sigla, serie, numero):
    """
    Gestisce le azioni (Start, Complete, Approve, Reject) sul DB.
    'Approve' genera il file PDF e salva il nome sul DB.
    """
    if not (current_user.has_role('admin') or current_user.has_role('preparatore')):
        flash("Accesso non autorizzato.", "danger")
        return redirect(url_for('dashboard'))

    action = request.form.get('action')
    order_key = f"{sigla}:{serie}:{numero}"
    order_id = str(numero) # Per il flash message
    order_name_notifica = f"#{order_id}"
    send_notification_flag = False
    
    picking_data_to_save = None # Dati per il PDF

    try:
        # Recupera lo stato dal DB
        state = PickingState.query.get(order_key)
        if not state:
            flash(f"Stato ordine {order_id} non trovato nel DB.", "danger")
            return redirect(url_for('ordini_list'))

        stato_precedente = state.status
        
        # Recupera i dati ordine (per nome cliente e righe) dalla cache
        orders_map, _ = get_cached_order_data()
        order_info = orders_map.get(order_key, {})
        if order_info:
            order_name_notifica = f"#{order_id} ({order_info.get('ragione_sociale', 'N/D')})"

        # --- Logica Azioni ---
        if action == 'start_picking':
            if stato_precedente == 'Da Lavorare' or stato_precedente == 'In Controllo':
                state.status = 'In Picking'
                # Resetta packing list E picked_items quando si (ri)inizia
                state.packing_list_json = '[]'
                state.picked_items_json = '{}'
                state.colli_totali_operatore = 0
                db.session.commit()
                flash(f"Ordine {order_name_notifica} messo 'In Picking'. Packing list resettata.", "info")
            else:
                 flash(f"Azione 'In Picking' non permessa.", "warning")

        elif action == 'complete_picking':
            if stato_precedente == 'In Picking':
                state.status = 'In Controllo'
                
                colli_totali_str = request.form.get('colli_totali_operatore', '0')
                try:
                    colli_totali = int(colli_totali_str) if colli_totali_str else 0
                    colli_totali = max(0, colli_totali)
                except ValueError:
                     colli_totali = 0
                     flash("Numero colli non valido.", "warning")

                # Salva i colli totali dichiarati
                state.colli_totali_operatore = colli_totali
                db.session.commit()
                flash(f"Packing list inviata al controllo. Colli dichiarati: {colli_totali}", "success")
            else:
                 flash(f"Azione 'Completa Picking' non permessa.", "warning")

        elif action == 'approve_order':
              if stato_precedente == 'In Controllo':
                state.status = 'Completato'
                # Non fare il commit qui, lo facciamo dopo aver salvato il nome del file
                
                # Prepara i dati per il salvataggio file
                picking_data_to_save = {
                    "order_key": order_key,
                    "sigla": sigla, "serie": serie, "numero": numero,
                    "cliente": order_info.get('ragione_sociale', 'N/D'),
                    "operatore": current_user.id,
                    "colli_totali_dichiarati": state.colli_totali_operatore,
                    "packing_list_dettagliata": json.loads(state.packing_list_json or '[]'),
                    "order_rows": list(order_info.get('righe', []))
                }
                # Il flag per la notifica e il flash verranno gestiti dopo la creazione del PDF
              else: 
                   flash(f"Azione 'Approva Ordine' non permessa.", "warning")

        elif action == 'reject_order':
              if stato_precedente == 'In Controllo':
                state.status = 'In Picking' # Torna in picking
                db.session.commit()
                flash(f"Ordine {order_name_notifica} rifiutato. Riportato a 'In Picking'.", "warning")
              else: 
                flash(f"Azione 'Rifiuta Ordine' non permessa.", "warning")
        else:
              flash(f"Azione ('{action}') non riconosciuta.", "danger")

        print(f"DEBUG [order_action]: Ordine {order_key}, Azione '{action}', Stato Post DB: '{state.status}'")

    except Exception as e:
        db.session.rollback()
        print(f"ERRORE CRITICO [order_action] nel DB: {e}")
        flash(f"Errore database: {e}", "danger")
        return redirect(url_for('order_detail_view', sigla=sigla, serie=serie, numero=numero))


    # --- Blocco Creazione PDF (ORA FUORI DALLA TRANSAZIONE) ---
    if picking_data_to_save:
        pdf_bytes = None
        filename = None
        try:
            # --- 1. Genera la mappa delle descrizioni ---
            desc_map = {
                item.get('codice_articolo'): item.get('descr_articolo', 'N/D')
                for item in picking_data_to_save['order_rows']
            }

            # --- 2. Definisci il nome del file ---
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{picking_data_to_save['sigla']}-{picking_data_to_save['serie']}-{picking_data_to_save['numero']}_{picking_data_to_save['operatore']}_{timestamp}.pdf"

            # --- 3. Genera il PDF con FPDF2 (Layout Migliorato) ---
            print(f"DEBUG [complete_picking]: Generazione PDF (fpdf2) per {filename}...")
            
            pdf = PDF(orientation="P", unit="mm", format="A4")
            pdf.alias_nb_pages()
            pdf.add_page()
            pdf.set_auto_page_break(auto=True, margin=15)
            
            COL_W_QTY = 18
            COL_W_CODE = 42
            COL_W_DESC = 130
            
            pdf.set_font("Arial", "B", 20)
            pdf.cell(0, 12, "PACKING LIST", border=0, ln=1, align="C")
            pdf.ln(5)

            pdf.set_font("Arial", size=10)
            pdf.cell(95, 6, f"Ordine: {picking_data_to_save['order_key']}", ln=0)
            pdf.cell(95, 6, f"Data: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}", ln=1, align="R")
            pdf.cell(0, 6, f"Cliente: {picking_data_to_save['cliente']}", ln=1)
            pdf.cell(0, 6, f"Operatore: {picking_data_to_save['operatore']}", ln=1)
            
            pdf.set_font("Arial", "B", 12)
            pdf.set_fill_color(240, 240, 240)
            pdf.cell(0, 8, f"COLLI TOTALI DICHIARATI: {picking_data_to_save['colli_totali_dichiarati']}", ln=1, fill=True, align="C")
            pdf.ln(7)

            riepilogo_totale_articoli = defaultdict(float)
            packing_list_ordinata = sorted(picking_data_to_save['packing_list_dettagliata'], key=lambda c: c['collo_id'])

            # 4. Scrivi dettaglio per collo
            for collo in packing_list_ordinata:
                collo_id = collo.get('collo_id')
                items_in_collo = collo.get('items', {})
                
                pdf.set_font("Arial", "B", 13)
                pdf.set_fill_color(230, 230, 230)
                pdf.cell(0, 10, f"COLLO {collo_id}", border=0, ln=1, fill=True)
                
                if not items_in_collo:
                    pdf.set_font("Arial", "I", 9)
                    pdf.cell(0, 7, "(Vuoto)", ln=1, align="C")
                    pdf.ln(3)
                else:
                    pdf.set_font("Arial", "B", 9)
                    pdf.cell(COL_W_QTY, 6, "Qta", border="B")
                    pdf.cell(COL_W_CODE, 6, "Codice", border="B")
                    pdf.cell(COL_W_DESC, 6, "Descrizione", border="B", ln=1)
                    
                    pdf.set_font("Arial", size=9)
                    for codice_art, qta in sorted(items_in_collo.items()):
                        desc = desc_map.get(codice_art, 'N/D')
                        qta_str = str(int(qta))
                        cod_str = f"[{codice_art}]"
                        
                        pdf.set_x(pdf.l_margin + COL_W_QTY + COL_W_CODE)
                        row_height = pdf.multi_cell(COL_W_DESC, 5, desc, border=0, ln=0, dry_run=True, output="HEIGHT")
                        row_height = max(5, row_height)
                        pdf.set_x(pdf.l_margin) 
                        
                        pdf.set_font("Arial", "B", 9)
                        pdf.cell(COL_W_QTY, row_height, qta_str, border=0, align="L")
                        pdf.set_font("Arial", "", 9)
                        pdf.cell(COL_W_CODE, row_height, cod_str, border=0)
                        pdf.multi_cell(COL_W_DESC, 5, desc, border=0, ln=1)
                        
                        riepilogo_totale_articoli[codice_art] += qta
                pdf.ln(5)

            # 5. Scrivi riepilogo totale articoli
            pdf.ln(5)
            pdf.set_font("Arial", "B", 13)
            pdf.set_fill_color(230, 230, 230)
            pdf.cell(0, 10, "RIEPILOGO ARTICOLI TOTALI PRELEVATI", border=0, ln=1, fill=True)
            
            pdf.set_font("Arial", "B", 9)
            pdf.cell(COL_W_QTY, 6, "Qta Tot.", border="B")
            pdf.cell(COL_W_CODE, 6, "Codice", border="B")
            pdf.cell(COL_W_DESC, 6, "Descrizione", border="B", ln=1)
            pdf.set_font("Arial", size=9)
            
            if not riepilogo_totale_articoli:
                pdf.cell(0, 7, "Nessun articolo prelevato.", ln=1)
            else:
                for codice_art, qta_totale in sorted(riepilogo_totale_articoli.items()):
                    desc = desc_map.get(codice_art, 'N/D')
                    qta_str = str(int(qta_totale))
                    cod_str = f"[{codice_art}]"
                    
                    pdf.set_x(pdf.l_margin + COL_W_QTY + COL_W_CODE)
                    row_height = pdf.multi_cell(COL_W_DESC, 5, desc, border=0, ln=0, dry_run=True, output="HEIGHT")
                    row_height = max(5, row_height)
                    pdf.set_x(pdf.l_margin) 
                    
                    pdf.set_font("Arial", "B", 9)
                    pdf.cell(COL_W_QTY, row_height, qta_str, border=0, align="L")
                    pdf.set_font("Arial", "", 9)
                    pdf.cell(COL_W_CODE, row_height, cod_str, border=0)
                    pdf.multi_cell(COL_W_DESC, 5, desc, border=0, ln=1)

            # --- 6. Ottieni il PDF come bytes ---
            pdf_bytes = pdf.output()
            print(f"DEBUG [complete_picking]: PDF (estetico) generato ({len(pdf_bytes)} bytes).")

            # --- 7. Tenta Upload su Dropbox ---
            upload_success, upload_message = _upload_to_dropbox(pdf_bytes, filename)
            
            if upload_success:
                flash(f"Packing list PDF salvata su Dropbox ({filename}).", "success")
                send_notification_flag = True # Attiva notifica solo se upload OK
                # Ora salva il nome del file e lo stato 'Completato' sul DB
                try:
                    state = PickingState.query.get(order_key)
                    if state:
                        state.pdf_filename = filename
                        state.status = 'Completato' # Imposta lo stato qui
                        db.session.commit()
                        print(f"DEBUG [order_action]: Salvato filename e stato 'Completato' per {order_key}")
                    else:
                        flash("ERRORE: Stato ordine perso dopo creazione PDF.", "danger")
                except Exception as e_save:
                    db.session.rollback()
                    print(f"ERRORE [order_action]: Fallito salvataggio filename/status PDF: {e_save}")
                    flash("Errore nel salvare il riferimento al PDF.", "warning")
            else:
                flash(f"ATTENZIONE: Fallito upload PDF su Dropbox ({upload_message}). L'ordine NON è stato approvato.", "danger")
                # Non impostiamo lo stato a 'Completato' se l'upload fallisce

        except Exception as e_gen:
            print(f"ERRORE CRITICO [complete_picking]: {e_gen}")
            import traceback; traceback.print_exc()
            flash("Picking completato, MA fallito generazione/upload del PDF.", "danger")

        # --- 8. Salva localmente (come bytes) ---
        if pdf_bytes and filename:
            try:
                output_folder = os.path.join(app.root_path, 'picking_lists_locali')
                os.makedirs(output_folder, exist_ok=True)
                filepath = os.path.join(output_folder, filename)
                with open(filepath, 'wb') as f_local:
                    f_local.write(pdf_bytes)
                print(f"DEBUG [complete_picking]: Backup PDF locale salvato in: {filepath}")
                flash("File PDF salvato anche localmente come backup.", "info")
            except Exception as e_local:
                print(f"ERRORE CRITICO [complete_picking]: Fallito salvataggio backup PDF locale: {e_local}")
                flash("Fallito ANCHE salvataggio backup PDF locale!", "danger")
    # --- FINE SALVATAGGIO FILE ---


    # --- Invio notifica (se 'approve_order' è riuscito) ---
    if send_notification_flag:
        try:
            admin_users = [user for user, data in users_db.items() if 'admin' in data.get('roles', [])]
            if not admin_users:
                 print("WARN [order_action]: Nessun admin per notifica approvazione.")
            for admin in admin_users:
                print(f"Invio notifica approvazione ordine {order_name_notifica} ad admin: {admin}")
                send_push_notification(admin, "Ordine Pronto Spedizione!", f"Ordine {order_name_notifica} approvato.")
        except Exception as e:
            print(f"ERRORE [order_action]: Fallito invio notifica approvazione: {e}")
            flash("Ordine approvato, ma errore invio notifica.", "warning")

    return redirect(url_for('order_detail_view', sigla=sigla, serie=serie, numero=numero))

# --- Rotte Magazzino, Clienti, Todo (Invariate) ---
# ... (incolla qui le tue funzioni magazzino, update_alt_code_api, clienti_indirizzi, e tutte le rotte todo_...) ...
# (Assicurati di incollare: magazzino, update_alt_code_api, clienti_indirizzi, todo_list, add_todo, toggle_todo, delete_todo)
@app.route('/magazzino')
@login_required
def magazzino():
    if not (current_user.has_role('admin') or current_user.has_role('preparatore')):
        flash("Accesso non autorizzato.", "danger")
        return redirect(url_for('dashboard'))
    
    query = request.args.get('q', '').strip()
    articles_list = []
    error_message = None
    search_type_used = None

    if query:
        print(f"Ricerca magazzino per: '{query}'")
        is_likely_code = ' ' not in query
        articles_data = None
        
        if is_likely_code:
            print("Ricerca per codice...")
            articles_data = search_articles_by_code(query) # Funzione API specifica
            search_type_used = 'codice'
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
            print(f"Trovati {len(articles_data)} articoli. Recupero dettagli...")
            processed_count = 0
            detail_errors = 0
            for art_summary in articles_data:
                codice_art = art_summary.get('codice')
                if not codice_art:
                    continue

                art_details = get_article_details(codice_art)
                art = dict(art_summary)

                if art_details:
                    art['cod_alternativo'] = art_details.get('cod_alternativo', '')
                else:
                    art['cod_alternativo'] = 'N/D'
                    detail_errors += 1
                    print(f"Errore nel recuperare dettagli per {codice_art}")

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

                articles_list.append(art)
            
            print(f"Dettagli recuperati per {processed_count} articoli ({detail_errors} errori).")
            if detail_errors > 0:
                 flash(f"Attenzione: Non è stato possibile recuperare i dettagli per {detail_errors} articoli.", "warning")

    if error_message:
        flash(error_message, "warning")

    return render_template('magazzino.html',
                           query=query,
                           articles=articles_list,
                           active_page='magazzino')

@app.route('/api/update-alt-code', methods=['POST'])
@login_required
def update_alt_code_api():
    if not (current_user.has_role('admin') or current_user.has_role('preparatore')):
        return jsonify({'status': 'error', 'message': 'Accesso non autorizzato'}), 403
    data = request.json
    article_code = data.get('article_code')
    alt_code = data.get('alt_code')
    if not article_code or alt_code is None:
        return jsonify({'status': 'error', 'message': 'Dati mancanti.'}), 400
    
    success = update_article_alt_code(article_code, alt_code)
    
    if success:
        return jsonify({'status': 'success', 'message': 'Codice alternativo aggiornato.'})
    else:
        return jsonify({'status': 'error', 'message': 'Errore API Mexal.'}), 500

@app.route('/clienti_indirizzi')
@login_required
def clienti_indirizzi():
    if not current_user.has_role('admin'):
        flash("Accesso non autorizzato.", "danger")
        return redirect(url_for('dashboard'))
    clients = get_all_clients()
    if clients is None:
        flash("Errore nel recupero clienti.", "danger")
        clients = []
    all_addresses = get_all_shipping_addresses()
    if all_addresses is None:
        flash("Errore nel recupero indirizzi.", "warning")
        all_addresses = []
    
    addresses_by_client = defaultdict(list)
    for addr in all_addresses:
        client_code = addr.get('cod_conto')
        if client_code:
            addresses_by_client[client_code].append(addr)
    
    clients.sort(key=lambda c: c.get('ragione_sociale', '').lower())
    
    return render_template('clienti_indirizzi.html',
                           clients=clients,
                           addresses_map=addresses_by_client,
                           active_page='clienti_indirizzi')

@app.route('/todo')
@login_required
def todo_list():
    try:
        incomplete_tasks = TodoItem.query.filter_by(is_completed=False).order_by(TodoItem.created_at.desc()).all()
        completed_tasks = TodoItem.query.filter_by(is_completed=True).order_by(TodoItem.completed_at.desc()).all()
    except Exception as e:
        print(f"Errore DB leggendo ToDo: {e}")
        flash("Errore nel caricamento delle cose da fare.", "danger")
        incomplete_tasks = []
        completed_tasks = []
    
    assignable_users = sorted(list(users_db.keys()))
    return render_template('todo.html',
                           incomplete_tasks=incomplete_tasks,
                           completed_tasks=completed_tasks,
                           assignable_users=assignable_users,
                           active_page='todo')

@app.route('/todo/add', methods=['POST'])
@login_required
def add_todo():
    description = request.form.get('description', '').strip()
    assigned_user = request.form.get('assign_to')
    creator_id = current_user.id
    if assigned_user == "": assigned_user = None

    if not description:
        flash("La descrizione non può essere vuota.", "warning")
    else:
        try:
            new_task = TodoItem(created_by=creator_id,
                                description=description,
                                assigned_to=assigned_user)
            db.session.add(new_task)
            db.session.commit()
            flash(f"Nuova cosa da fare aggiunta{(' e assegnata a ' + assigned_user) if assigned_user else ''}!", "success")
            
            try:
                description_short = (description[:40] + '...') if len(description) > 40 else description
                send_push_notification(creator_id, "Nuova Task Aggiunta", f"Hai aggiunto: '{description_short}'")
                if assigned_user and assigned_user != creator_id:
                    send_push_notification(assigned_user, "Nuova Task Assegnata", f"Ti è stata assegnata: '{description_short}' da {creator_id}")
            except Exception as notify_err: print(f"ERRORE [add_todo]: Fallito invio notifica: {notify_err}")
        
        except Exception as e:
            db.session.rollback()
            print(f"ERRORE CRITICO [add_todo]: {e}")
            flash("Errore durante l'aggiunta.", "danger")
    return redirect(url_for('todo_list'))

@app.route('/todo/toggle/<int:item_id>', methods=['POST'])
@login_required
def toggle_todo(item_id):
    if not (current_user.has_role('admin') or current_user.has_role('preparatore')):
        flash("Non hai i permessi per modificare lo stato.", "warning")
        return redirect(url_for('todo_list'))
    
    completer_id = current_user.id
    try:
        task = TodoItem.query.get(item_id)
        if task:
            if task.is_completed:
                task.is_completed = False
                task.completed_at = None
                task.completed_by = None
                action_msg = "riaperta"
                flash_cat = "info"
            else:
                task.is_completed = True
                task.completed_at = datetime.utcnow()
                task.completed_by = completer_id
                action_msg = "completata"
                flash_cat = "success"
            db.session.commit()
            flash(f"'{task.description[:30]}...' {action_msg}!", flash_cat)
        else:
            flash("Operazione non trovata.", "warning")
    except Exception as e:
        db.session.rollback()
        print(f"ERRORE CRITICO [toggle_todo]: {e}")
        flash("Errore durante l'aggiornamento.", "danger")
    return redirect(url_for('todo_list'))

@app.route('/todo/delete/<int:item_id>', methods=['POST'])
@login_required
def delete_todo(item_id):
    if not current_user.has_role('admin'):
        flash("Non hai i permessi per eliminare.", "warning")
        return redirect(url_for('todo_list'))
    
    try:
        task = TodoItem.query.get(item_id)
        if task:
            description_short = task.description[:30]
            db.session.delete(task)
            db.session.commit()
            flash(f"'{description_short}...' eliminata.", "success")
        else:
            flash("Operazione non trovata.", "warning")
    except Exception as e:
        db.session.rollback()
        print(f"ERRORE CRITICO [delete_todo]: {e}")
        flash("Errore durante l'eliminazione.", "danger")
    return redirect(url_for('todo_list'))

def get_cached_article_group(codice):
    """
    Funzione helper per il caching "lazy" dei gruppi merceologici.
    Chiama l'API solo se il codice non è già in cache.
    """
    # 1. Prova a leggere dalla cache in memoria
    if codice in _article_details_cache:
        return _article_details_cache[codice]
    
    # 2. Se non c'è, chiama l'API (questo accadrà solo la prima volta)
    print(f"Fabbisogno (Cache Miss): Chiamata API per dettagli art: {codice}")
    details = get_article_details(codice)
    
    # 3. Salva in cache e restituisci
    if details and details.get('cod_grp_merc'):
        gruppo = details['cod_grp_merc'] or 'Nessun Gruppo'
    else:
        gruppo = 'Nessun Gruppo'
        
    _article_details_cache[codice] = gruppo
    return gruppo

@app.route('/fabbisogno')
@login_required
def fabbisogno():
    """
    Calcola il fabbisogno giornaliero e lo SMISTA in 5 gruppi
    per l'interfaccia a schede.
    (Modificato per sommare i COLLI, non le quantità)
    """
    if not (current_user.has_role('admin') or current_user.has_role('preparatore')):
        flash("Accesso non autorizzato.", "danger")
        return redirect(url_for('dashboard'))

    giorno_filtro = request.args.get('giorno_filtro', '').strip()
    data_selezionata_formattata = ''
    error_message = None
    
    # Dizionari per ogni scheda
    data_pesce = OrderedDict()
    data_frutti = OrderedDict()
    data_gelo = OrderedDict()
    data_secco = OrderedDict()
    data_altri = OrderedDict()

    if giorno_filtro:
        orders_map, _ = get_cached_order_data()
        
        if orders_map is None:
            error_message = "Errore API: Impossibile caricare gli ordini."
        else:
            try:
                giorno_da_cercare = giorno_filtro.zfill(2)
                if not giorno_da_cercare.isdigit() or len(giorno_da_cercare) != 2:
                    raise ValueError("Formato giorno non valido.")

                print(f"Fabbisogno: Filtro per giorno che termina con: '{giorno_da_cercare}'")
                
                ordini_del_giorno = [
                    o for o in orders_map.values()
                    if isinstance(o.get('data_documento'), str) and len(o['data_documento']) == 8 and o['data_documento'].endswith(giorno_da_cercare)
                ]

                if not ordini_del_giorno:
                     error_message = f"Nessun ordine trovato per il giorno '{giorno_filtro}'."
                else:
                    print(f"Fabbisogno: Trovati {len(ordini_del_giorno)} ordini. Inizio aggregazione...")
                    
                    # 1. Aggregazione
                    grouped_data = {} # Dizionario temporaneo
                    for order in ordini_del_giorno:
                        cliente = order.get('ragione_sociale', 'Cliente Sconosciuto')
                        
                        for item in order.get('righe', []):
                            codice = item.get('codice_articolo')
                            if not codice: continue

                            gruppo = get_cached_article_group(codice)

                            # --- MODIFICA LOGICA DI SOMMA ---
                            try: 
                                # Sommiamo i COLLI (nr_colli)
                                colli_val = float(str(item.get('nr_colli', 0) or 0).replace(',', '.'))
                                # Prendiamo la QTA PER COLLO (quantita)
                                qta_val = float(str(item.get('quantita', 0) or 0).replace(',', '.'))
                            except (ValueError, TypeError): 
                                colli_val = 0.0
                                qta_val = 0.0

                            # Se non ci sono colli, non mostriamo nulla
                            if colli_val > 0:
                                if gruppo not in grouped_data: grouped_data[gruppo] = {}
                                if codice not in grouped_data[gruppo]:
                                    grouped_data[gruppo][codice] = {
                                        'descrizione': item.get('descr_articolo', 'N/D'),
                                        'totale_colli': 0.0,
                                        'qta_per_collo': qta_val, # Assumiamo sia costante
                                        'clienti': defaultdict(float)
                                    }
                                
                                grouped_data[gruppo][codice]['totale_colli'] += colli_val
                                grouped_data[gruppo][codice]['clienti'][cliente] += colli_val
                                # Se la qta per collo è 0 in questa riga, ma era 0 anche prima, prova a prenderla
                                if grouped_data[gruppo][codice]['qta_per_collo'] == 0 and qta_val > 0:
                                    grouped_data[gruppo][codice]['qta_per_collo'] = qta_val
                            # --- FINE MODIFICA LOGICA DI SOMMA ---

                    print("Fabbisogno: Aggregazione completata. Inizio smistamento schede...")
                    
                    # 2. Smistamento nelle 5 schede
                    for gruppo, articoli_dict in sorted(grouped_data.items()):
                        sorted_articoli_list = sorted(
                            articoli_dict.items(),
                            key=lambda item: item[1].get('totale_colli', 0), # Ordina per totale_colli
                            reverse=True 
                        )
                        articoli_ordinati = OrderedDict(sorted_articoli_list)

                        if gruppo in GRUPPI_PESCE:
                            data_pesce[gruppo] = articoli_ordinati
                        elif gruppo in GRUPPI_FRUTTI:
                            data_frutti[gruppo] = articoli_ordinati
                        elif gruppo in GRUPPI_GELO:
                            data_gelo[gruppo] = articoli_ordinati
                        elif gruppo in GRUPPI_SECCO:
                            data_secco[gruppo] = articoli_ordinati
                        else:
                            data_altri[gruppo] = articoli_ordinati
                    
                    data_selezionata_formattata = f"Giorno: {giorno_filtro}"
                    print("Fabbisogno: Smistamento completato.")

            except ValueError as e:
                error_message = f"Filtro giorno non valido: {e}."
            except Exception as e:
                 print(f"Errore inatteso durante calcolo fabbisogno: {e}")
                 import traceback; traceback.print_exc()
                 error_message = "Si è verificato un errore durante il calcolo."

    if error_message: flash(error_message, "warning")

    return render_template('fabbisogno.html',
                           giorno_selezionato=giorno_filtro,
                           data_selezionata_formattata=data_selezionata_formattata,
                           # Passiamo i 5 dizionari al template
                           data_pesce=data_pesce,
                           data_frutti=data_frutti,
                           data_gelo=data_gelo,
                           data_secco=data_secco,
                           data_altri=data_altri,
                           active_page='fabbisogno')

@app.route('/download-pdf/<path:filename>')
@login_required
def download_pdf(filename):
    """
    Gestisce il download di un PDF da Dropbox in modo sicuro.
    """
    if not current_user.has_role('admin'):
        flash("Accesso non autorizzato.", "danger")
        return redirect(url_for('dashboard'))

    if not DROPBOX_TOKEN:
        flash("Errore: Dropbox non configurato sul server.", "danger")
        return redirect(url_for('amministrazione'))

    dropbox_path = f"/{filename}"
    print(f"DEBUG [download_pdf]: Tentativo download '{dropbox_path}' da Dropbox...")

    try:
        dbx = dropbox.Dropbox(DROPBOX_TOKEN)
        metadata, res = dbx.files_download(path=dropbox_path)
        
        # Crea la risposta
        response = make_response(res.content)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Length'] = str(metadata.size)
        
        # Se è una richiesta JavaScript, mostralo inline.
        # Altrimenti, scaricalo come allegato.
        if request.args.get('for_js'):
            response.headers['Content-Disposition'] = f"inline; filename={filename}"
        else:
            response.headers['Content-Disposition'] = f"attachment; filename={filename}"
        
        # Permetti al JavaScript su localhost di chiamare questa rotta
        response.headers['Access-Control-Allow-Origin'] = '*'

        return response
        
    except dropbox.exceptions.ApiError as e:
        print(f"ERRORE [download_pdf]: File non trovato su Dropbox '{dropbox_path}': {e}")
        flash(f"Errore: File {filename} non trovato su Dropbox.", "danger")
        return redirect(url_for('amministrazione'))
    except Exception as e:
        print(f"ERRORE [download_pdf]: Errore generico: {e}")
        flash("Errore sconosciuto durante il download del file.", "danger")
        return redirect(url_for('amministrazione'))


# --- Creazione DB all'avvio ---
with app.app_context():
    try:
        print("Verifica/Creazione tabelle database all'avvio...")
        db.create_all()
        print("Verifica/Creazione tabelle completata.")
    except Exception as e:
        print(f"ERRORE CRITICO durante creazione tabelle DB all'avvio: {e}")


# --- Avvio App ---
if __name__ == '__main__':
    print("--- Configurazione Avvio ---")
    print(f"SECRET_KEY: {'Configurata' if app.config['SECRET_KEY'] else 'NON CONFIGURATA!'}")
    print(f"SQLALCHEMY_DATABASE_URI: {app.config['SQLALCHEMY_DATABASE_URI']}")
    # ... (altri print di configurazione) ...
    print("--------------------------")
    
    # Per produzione su Render, gunicorn sarà il punto d'ingresso.
    # Questo app.run() è solo per il test locale.
    app.run(host='0.0.0.0', port=5001, debug=True)


