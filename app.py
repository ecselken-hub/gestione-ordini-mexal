from flask import Flask, render_template, request, redirect, url_for, flash, Response, jsonify, send_from_directory
from mexal_api import mx_call_api, get_vettori, get_shipping_address, get_dati_aggiuntivi, get_payment_methods, search_articles, get_article_price
import time
import os
import googlemaps
from datetime import datetime, timedelta
from collections import OrderedDict, defaultdict
import math
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user # Importa Flask-Login
from flask_wtf import FlaskForm # Importa Flask-WTF
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired
from werkzeug.security import generate_password_hash, check_password_hash # Per le password
from fpdf import FPDF # Importa la libreria PDF
import io # Necessario per inviare il PDF
import json # Per le notifiche
from flask_sqlalchemy import SQLAlchemy
from pywebpush import webpush, WebPushException

app = Flask(__name__)
# CHIAVE SEGRETA: Fondamentale per la sicurezza delle sessioni. Cambiala con una stringa casuale!
app.config['SECRET_KEY'] = 'dhjsbbfkjbcdvkjhrkjdjs82328933jdeshfe' 

render_disk_path = os.environ.get('RENDER_DISK_PATH')

if render_disk_path:
    # Siamo su Render: usa il disco persistente
    db_path = os.path.join(render_disk_path, 'notifications.db')
    print(f"Siamo su Render. Percorso DB: {db_path}")
else:
    # Siamo in locale: usa un file 'local.db' nella cartella 'instance'
    # La 'instance_path' è una cartella sicura creata da Flask
    instance_path = app.instance_path
    db_path = os.path.join(instance_path, 'local.db')
    
    # Assicurati che la cartella 'instance' esista
    try:
        os.makedirs(instance_path, exist_ok=True)
        print(f"Siamo in locale. Percorso DB: {db_path}")
    except OSError as e:
        print(f"Errore creando la cartella instance: {e}")

app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
db = SQLAlchemy(app)

VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY")
VAPID_CLAIM_EMAIL = "mailto:ecsel.ken@gmail.com"

# --- Configurazione Flask-Login ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login' # Dice a Flask-Login qual è la pagina di login
login_manager.login_message = "Effettua il login per accedere a questa pagina."
login_manager.login_message_category = "info" # Categoria per i messaggi flash

# --- Modello Utente Semplificato ---
# In un'app reale, questi dati verrebbero da un database.
# Ora usiamo password "hashate" per sicurezza. Genera gli hash una volta.
# Esempio per generare hash: print(generate_password_hash('adminpassword', method='pbkdf2:sha256'))
users_db = {
    "admin": {
        "password_hash": "pbkdf2:sha256:1000000$twPz6aqEEUMtxMlO$3df53c4ca2f5741368b0aae9016540e9ffe77ffb72e89e23c71e731751f125a3", # Incolla qui l'hash generato per 'adminpassword'
        "roles": ["admin"]
        },
    "autista": {
        "password_hash": "pbkdf2:sha256:1000000$UaOzWrh0Z3pgGA61$5ca28f52448332464f940ea727acab917096c2d6b9ad2bd97509b47ae42ac", # Incolla qui l'hash generato per 'driverpass'
        "roles": ["autista"]
        },
     "boxer": { # Aggiunto utente specifico per l'autista
        "password_hash": "pbkdf2:sha256:1000000$aeWrP3lEfXCCRalu$15db591b7eae61ccd44c36f385c1687df33777272f792b3b1c1be38fe4410419", # Incolla qui l'hash generato per 'boxerpass' (inventa una password)
        "roles": ["autista"],
        "nome_autista": "BOXER" # Associa l'utente al nome autista
        },
     "expert": { # Aggiunto utente specifico per l'autista
        "password_hash": "pbkdf2:sha256:1000000$QCYdpjrbJ9zDuAdg$a558fe5f3e0736b28b9ac9b91c7364127020bf98334fc1df326715f812ba19d6", # Incolla qui l'hash generato per 'expertpass' (inventa una password)
        "roles": ["autista"],
        "nome_autista": "EXPERT"
        },
    "preparatore": {
        "password_hash": "pbkdf2:sha256:1000000$zH0IGyoD70dZGUy6$631637c5a341ab4b29eee85d6462949b705ea0138241b9073ea95d296ead6651", # Incolla qui l'hash generato per 'pickerpass'
        "roles": ["preparatore"]
        }
}

class User(UserMixin):
    """Classe utente richiesta da Flask-Login."""
    def __init__(self, id, roles, nome_autista=None):
        self.id = id
        self.roles = roles
        self.nome_autista = nome_autista # Aggiunto per gli autisti

    def has_role(self, role):
        return role in self.roles

@login_manager.user_loader
def load_user(user_id):
    """Callback per ricaricare l'oggetto utente dall'ID salvato in sessione."""
    user_data = users_db.get(user_id)
    if user_data:
        return User(id=user_id, roles=user_data['roles'], nome_autista=user_data.get('nome_autista'))
    return None

# --- Modulo di Login ---
class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Accedi')

# --- Rotte di Login/Logout ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard')) # Se già loggato, va alla dashboard
    form = LoginForm()
    if form.validate_on_submit():
        user_data = users_db.get(form.username.data)
        # Verifica l'hash della password
        if user_data and check_password_hash(user_data['password_hash'], form.password.data):
            user_obj = User(id=form.username.data, roles=user_data['roles'], nome_autista=user_data.get('nome_autista'))
            login_user(user_obj) # Registra l'utente come loggato
            flash('Login effettuato con successo.', 'success')
            return redirect(url_for('dashboard')) # Reindirizza alla dashboard dopo il login
        else:
            flash('Username o password non validi.', 'danger')
    return render_template('login.html', form=form)

@app.route('/logout')
@login_required # Solo gli utenti loggati possono fare logout
def logout():
    logout_user() # Cancella la sessione utente
    flash('Logout effettuato con successo.', 'success')
    return redirect(url_for('login')) # Reindirizza alla pagina di login

class PushSubscription(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    # L'utente a cui appartiene questa sottoscrizione (l'admin)
    user_id = db.Column(db.String(50), nullable=False) 
    # Il JSON completo della sottoscrizione inviato dal browser
    subscription_json = db.Column(db.Text, nullable=False)

# --- ROTTE PER LE NOTIFICHE ---
@app.route('/vapid-public-key')
@login_required
def get_vapid_public_key():
    """Invia la chiave VAPID pubblica al client."""
    return jsonify({'public_key': os.getenv('VAPID_PUBLIC_KEY')})

@app.route('/save-subscription', methods=['POST'])
@login_required
def save_subscription():
    """Salva la sottoscrizione push di un utente nel database."""
    subscription_data = request.json
    user_id = current_user.id
    
    # Controlla se la sottoscrizione esiste già per questo utente
    existing_sub = PushSubscription.query.filter_by(
        user_id=user_id, 
        subscription_json=json.dumps(subscription_data)
    ).first()
    
    if not existing_sub:
        new_sub = PushSubscription(
            user_id=user_id,
            subscription_json=json.dumps(subscription_data)
        )
        db.session.add(new_sub)
        db.session.commit()
        print(f"Nuova sottoscrizione salvata per l'utente {user_id}")
    else:
        print(f"Sottoscrizione già esistente per l'utente {user_id}")
        
    return jsonify({'success': True})

def send_push_notification(user_id, title, body):
    """Invia una notifica a tutte le sottoscrizioni di un utente."""
    subscriptions = PushSubscription.query.filter_by(user_id=user_id).all()
    if not subscriptions:
        print(f"Nessuna sottoscrizione trovata per l'utente {user_id}")
        return

    payload = json.dumps({"title": title, "body": body})
    
    for sub in subscriptions:
        try:
            subscription_info = json.loads(sub.subscription_json)
            webpush(
                subscription_info=subscription_info,
                data=payload,
                vapid_private_key=VAPID_PRIVATE_KEY,
                vapid_claims={"sub": VAPID_CLAIM_EMAIL}
            )
        except WebPushException as ex:
            print(f"Errore invio notifica: {ex}")
            # Se la sottoscrizione è scaduta o non valida, la rimuoviamo
            if ex.response and ex.response.status_code in [404, 410]:
                db.session.delete(sub)
                db.session.commit()
                print(f"Sottoscrizione rimossa: {ex.response.status_code}")

# --- Store e Funzioni Dati (invariate) ---
app_data_store = {
    "orders": {}, 
    "statuses": {}, 
    "logistics": {}, 
    "delivery_events": {}, 
    "calculated_routes": {},
    "driver_notes": {},
    "last_load_time": None
}
def get_initial_status(): return {'status': 'Da Lavorare', 'picked_items': {}, 'colli_totali_operatore': 0}

def load_all_data():
    if app_data_store.get("orders"): return list(app_data_store["orders"].values())
    print("--- Inizio caricamento di massa dei dati dall'API ---")
    clients_response = mx_call_api('risorse/clienti/ricerca', method='POST', data={'Filtri': []})
    client_map = {client['codice']: client for client in (clients_response.get('dati') or [])}
    payment_map = get_payment_methods()
    orders_response = mx_call_api('risorse/documenti/ordini-clienti/ricerca', method='POST', data={'Filtri': []})
    if not orders_response or not orders_response.get('dati'): return None
    orders = orders_response['dati']
    rows_response = mx_call_api('risorse/documenti/ordini-clienti/righe/ricerca', method='POST', data={'Filtri': []})
    rows_map = {}
    if rows_response and rows_response.get('dati'):
        for row in rows_response['dati']:
            order_key = f"{row['sigla']}:{row['serie']}:{row['numero']}"
            rows_map.setdefault(order_key, []).append(row)
    for order in orders:
        order_key = f"{order['sigla']}:{order['serie']}:{order['numero']}"
        client_code = order.get('cod_conto')
        client_data = client_map.get(client_code, {})
        order['ragione_sociale'] = client_data.get('ragione_sociale', 'N/D')
        order['telefono'] = client_data.get('telefono', 'N/D')
        shipping_address_id = order.get('cod_anag_sped')
        shipping_address_data = get_shipping_address(shipping_address_id) if shipping_address_id else None
        if shipping_address_data:
            order['indirizzo'] = shipping_address_data.get('indirizzo', 'N/D')
            order['localita'] = shipping_address_data.get('localita', 'N/D')
        else:
            order['indirizzo'] = client_data.get('indirizzo', 'N/D')
            order['localita'] = client_data.get('localita', 'N/D')
        dati_aggiuntivi = get_dati_aggiuntivi(client_code)
        order['orario1_start'] = dati_aggiuntivi.get('orario1start') 
        order['orario1_end'] = dati_aggiuntivi.get('orario1end')
        order['nota'] = order.get('nota', '')
        order['pagamento_desc'] = payment_map.get(order.get('id_pagamento'), 'N/D')
        order['righe'] = rows_map.get(order_key, [])
        app_data_store["orders"][order_key] = order
    # Salva l'ora di questo caricamento
    app_data_store["last_load_time"] = datetime.now()
    return list(app_data_store["orders"].values())

@app.route('/')
@login_required
def dashboard():
    if current_user.has_role('admin'): return redirect(url_for('ordini_list'))
    elif current_user.has_role('preparatore'): return redirect(url_for('ordini_list'))
    elif current_user.has_role('autista'):
        if current_user.nome_autista: return redirect(url_for('consegne_autista', autista_nome=current_user.nome_autista))
        else: return redirect(url_for('autisti'))
    else: return "Ruolo non definito", 403

@app.route('/ordini')
@login_required
def ordini_list():
    if not (current_user.has_role('admin') or current_user.has_role('preparatore')): return "Accesso non autorizzato", 403
    orders_list = load_all_data() or []
    giorno_filtro = request.args.get('giorno_filtro')
    if giorno_filtro:
        giorno_da_cercare = giorno_filtro.zfill(2)
        orders_list = [order for order in orders_list if order.get('data_documento', '').endswith(giorno_da_cercare)]
    orders_list.sort(key=lambda order: order.get('data_documento', ''), reverse=True)
    ordini_per_data = OrderedDict()
    for order in orders_list:
        order_id = str(order.get('numero'))
        if order_id not in app_data_store["statuses"]: app_data_store["statuses"][order_id] = get_initial_status()
        order['local_status'] = app_data_store["statuses"].get(order_id, {}).get('status', 'Da Lavorare')
        date_str = order.get('data_documento')
        if date_str and len(date_str) == 8: order['data_formattata'] = f"{date_str[6:8]}/{date_str[4:6]}/{date_str[0:4]}"
        else: order['data_formattata'] = "Data non disponibile"
        data = order['data_formattata']
        if data not in ordini_per_data: ordini_per_data[data] = []
        ordini_per_data[data].append(order)
    return render_template('orders.html', ordini_per_data=ordini_per_data, giorno_selezionato=giorno_filtro, active_page='ordini', enable_polling=True)

@app.route('/trasporto')
@login_required
def trasporto():
    if not current_user.has_role('admin'): return "Accesso non autorizzato", 403
    orders_list = load_all_data() or []
    vettori = get_vettori()
    vettori_map = {v['codice']: v.get('ragione_sociale') or v.get('descrizione') for v in vettori}
    for key, value in app_data_store["logistics"].items():
        if isinstance(value, str): app_data_store["logistics"][key] = {'codice': value, 'nome': vettori_map.get(value)}
    ordini_per_data = OrderedDict()
    orders_list.sort(key=lambda order: order.get('data_documento', ''), reverse=True)
    for order in orders_list:
        order_key = f"{order['sigla']}:{order['serie']}:{order['numero']}"
        logistic_info = app_data_store["logistics"].get(order_key)
        if logistic_info:
            order['vettore_assegnato'] = logistic_info.get('codice') if isinstance(logistic_info, dict) else logistic_info
        order['nota_autista'] = app_data_store["driver_notes"].get(order_key, '')
        date_str = order.get('data_documento')
        if date_str and len(date_str) == 8: data_formattata = f"{date_str[6:8]}/{date_str[4:6]}/{date_str[0:4]}"
        else: data_formattata = "Data Sconosciuta"
        if data_formattata not in ordini_per_data: ordini_per_data[data_formattata] = []
        ordini_per_data[data_formattata].append(order)
    return render_template('trasporto.html', ordini_per_data=ordini_per_data, vettori=vettori, active_page='trasporto', enable_polling=True)
    
# --- NUOVA ROTTA PER IL POLLING ---
@app.route('/check-updates')
@login_required
def check_updates():
    """
    Controlla se ci sono nuovi ordini o modifiche su Mexal
    dall'ultimo caricamento dati.
    """
    last_load = app_data_store.get("last_load_time")
    if not last_load:
        # Dati mai caricati, forza aggiornamento
        app_data_store["orders"] = {} # Svuota cache
        return jsonify({'new_data': True})

    # Formatta l'ora per la chiamata API (es: '20251020 143000')
    last_load_str = last_load.strftime('%Y%m%d %H%M%S')
    
    # Cerca documenti modificati dopo l'ultimo caricamento
    # 'data_ult_mod' è un campo standard menzionato nella documentazione
    search_data = {
        'Filtri': [
            {'Campo': 'data_ult_mod', 'Operatore': '>', 'Valore': last_load_str}
        ]
    }
    
    # Controlliamo sia le testate che le righe per le modifiche
    updates_testate = mx_call_api('risorse/documenti/ordini-clienti/ricerca', method='POST', data=search_data)
    updates_righe = mx_call_api('risorse/documenti/ordini-clienti/righe/ricerca', method='POST', data=search_data)
    
    if (updates_testate and updates_testate.get('dati')) or (updates_righe and updates_righe.get('dati')):
        print("Rilevati aggiornamenti da Mexal. Svuoto la cache.")
        # Se ci sono aggiornamenti, svuota la cache per forzare un ricaricamento completo
        app_data_store["orders"] = {} 
        app_data_store["last_load_time"] = None
        return jsonify({'new_data': True})
    
    # Nessuna novità
    print("Nessun aggiornamento da Mexal.")
    return jsonify({'new_data': False})


@app.route('/assign_all_vettori', methods=['POST'])
@login_required
def assign_all_vettori():
    if not current_user.has_role('admin'): return "Accesso non autorizzato", 403
    for key, value in request.form.items():
        if key.startswith('vettore_'):
            order_key = key.replace('vettore_', '')
            vettore_codice = value
            if vettore_codice: app_data_store["logistics"][order_key] = vettore_codice
            else: 
                if order_key in app_data_store["logistics"]: del app_data_store["logistics"][order_key]
        elif key.startswith('nota_autista_'):
            order_key = key.replace('nota_autista_', '')
            nota_autista = value.strip()
            if nota_autista: app_data_store["driver_notes"][order_key] = nota_autista
            else:
                 if order_key in app_data_store["driver_notes"]: del app_data_store["driver_notes"][order_key]
    return redirect(url_for('trasporto'))

@app.route('/calcola-giri')
@login_required
def calcola_giri():
    if not current_user.has_role('admin'): return "Accesso non autorizzato", 403
    giri_per_vettore = {}
    for order_key, logistic_info in app_data_store["logistics"].items():
        if isinstance(logistic_info, str): # Assicura che sia dict
             vettori = get_vettori(); vettori_map = {v['codice']: v.get('ragione_sociale') or v.get('descrizione') for v in vettori}
             logistic_info = {'codice': logistic_info, 'nome': vettori_map.get(logistic_info)}; app_data_store["logistics"][order_key] = logistic_info
        if isinstance(logistic_info, dict):
            vettore_nome = logistic_info.get('nome', 'Sconosciuto')
            if vettore_nome not in giri_per_vettore: giri_per_vettore[vettore_nome] = []
            ordine_completo = app_data_store["orders"].get(order_key)
            if ordine_completo: giri_per_vettore[vettore_nome].append(ordine_completo)

    app_data_store["calculated_routes"] = {}
    for vettore, ordini_assegnati in giri_per_vettore.items():
        if not ordini_assegnati: continue
        partenza_prevista = datetime.now().replace(hour=8, minute=0, second=0)
        origin = "Japlab, Via Ferraris, 3, 84018 Scafati SA"
        waypoints = [f"{o['indirizzo']}, {o['localita']}" for o in ordini_assegnati if o.get('indirizzo') and o.get('localita')]
        if not waypoints: continue
        try:
            gmaps = googlemaps.Client(key=os.getenv('GOOGLE_MAPS_API_KEY'))
            directions_result = gmaps.directions(origin=origin, destination=origin, waypoints=waypoints, optimize_waypoints=True)
            if not directions_result: continue
            route = directions_result[0]
            # Salva l'ordine originale restituito da Google Maps
            google_waypoint_order = route['waypoint_order']
            # Crea la lista di tappe nell'ordine ottimizzato
            tappe_ordinate_oggetti = [ordini_assegnati[i] for i in google_waypoint_order]
            
            distanza_complessiva_km = sum(leg['distance']['value'] for leg in route['legs']) / 1000
            durata_complessiva_sec = sum(leg['duration']['value'] for leg in route['legs'])
            rientro_previsto = partenza_prevista + timedelta(seconds=durata_complessiva_sec)
            orario_tappa_corrente = partenza_prevista
            for i, leg_index in enumerate(google_waypoint_order):
                leg = route['legs'][i] # Usa l'indice del ciclo per le legs
                orario_tappa_corrente += timedelta(seconds=leg['duration']['value'])
                tappa_attuale = tappe_ordinate_oggetti[i] # Usa l'indice del ciclo per le tappe
                tappa_attuale['orario_previsto'] = orario_tappa_corrente.strftime('%H:%M')
            
            app_data_store["calculated_routes"][vettore] = {
                'data': datetime.now().strftime('%d/%m/%Y'), 'partenza_max': (partenza_prevista - timedelta(minutes=30)).strftime('%H:%M'),
                'num_consegne': len(tappe_ordinate_oggetti), 'km_previsti': f"{distanza_complessiva_km:.1f} km",
                'tempo_previsto': time.strftime("%Hh %Mm", time.gmtime(durata_complessiva_sec)), 'rientro_previsto': rientro_previsto.strftime('%H:%M'),
                'tappe': tappe_ordinate_oggetti, # Questa lista è già ordinata
                'efficienza': 'N/D', 'consumo_carburante': 'N/D'
            }
        except Exception as e:
            print(f"Errore durante il calcolo del percorso per {vettore}: {e}")
    return redirect(url_for('autisti'))

@app.route('/autisti')
@login_required
def autisti():
    if not (current_user.has_role('admin') or current_user.has_role('autista')): return "Accesso non autorizzato", 403
    return render_template('autisti.html', active_page='autisti')

@app.route('/consegne/<autista_nome>')
@login_required
def consegne_autista(autista_nome):
    if not current_user.has_role('admin'):
        if current_user.has_role('autista') and current_user.nome_autista != autista_nome: return "Accesso non autorizzato", 403
    
    giro_calcolato = app_data_store["calculated_routes"].get(autista_nome)
    
    # Usa le tappe ordinate dal giro calcolato, se esiste
    tappe_da_mostrare = giro_calcolato.get('tappe', []) if giro_calcolato else []
    
    # Se il giro non è calcolato, prendi la lista non ordinata
    if not tappe_da_mostrare:
        for order_key, logistic_info in app_data_store["logistics"].items():
             if isinstance(logistic_info, str): # Converti se necessario
                 vettori = get_vettori(); vettori_map = {v['codice']: v.get('ragione_sociale') or v.get('descrizione') for v in vettori}
                 logistic_info = {'codice': logistic_info, 'nome': vettori_map.get(logistic_info)}; app_data_store["logistics"][order_key] = logistic_info
             if isinstance(logistic_info, dict) and logistic_info.get('nome') == autista_nome:
                ordine_completo = app_data_store["orders"].get(order_key)
                if ordine_completo: tappe_da_mostrare.append(ordine_completo)
    
    # Arricchisci le tappe
    for tappa in tappe_da_mostrare:
        order_key = f"{tappa['sigla']}:{tappa['serie']}:{tappa['numero']}"
        order_id = str(tappa.get('numero'))
        eventi = app_data_store["delivery_events"].get(order_key, {})
        status = app_data_store["statuses"].get(order_id, {})
        tappa['start_time'] = eventi.get('start_time')
        tappa['end_time'] = eventi.get('end_time')
        tappa['colli_da_consegnare'] = status.get('colli_totali_operatore', 'N/D')
        tappa['nota_autista'] = app_data_store["driver_notes"].get(order_key, '')
            
    return render_template('consegna_autista.html', autista_nome=autista_nome, giro=giro_calcolato, tappe=tappe_da_mostrare)

# --- NUOVE FUNZIONI PER RIORDINARE LE TAPPE ---
@app.route('/move_tappa/<autista_nome>/<int:index>/<direction>', methods=['POST'])
@login_required
def move_tappa(autista_nome, index, direction):
    if not (current_user.has_role('admin') or (current_user.has_role('autista') and current_user.nome_autista == autista_nome)):
        return "Accesso non autorizzato", 403

    giro_calcolato = app_data_store["calculated_routes"].get(autista_nome)
    if giro_calcolato and 'tappe' in giro_calcolato:
        tappe = giro_calcolato['tappe']
        if 0 <= index < len(tappe):
            tappa_da_spostare = tappe.pop(index)
            nuovo_index = -1
            if direction == 'up' and index > 0:
                nuovo_index = index - 1
            elif direction == 'down' and index < len(tappe): # len(tappe) è ora uno in meno
                nuovo_index = index + 1
            
            if nuovo_index != -1:
                 tappe.insert(nuovo_index, tappa_da_spostare)
                 # Salva la lista riordinata nello store
                 app_data_store["calculated_routes"][autista_nome]['tappe'] = tappe
                 flash('Ordine tappe aggiornato.', 'success')
            else:
                 flash('Spostamento non valido.', 'warning')
                 tappe.insert(index, tappa_da_spostare) # Rimetti a posto se non valido

    return redirect(url_for('consegne_autista', autista_nome=autista_nome))
# --- FINE NUOVE FUNZIONI ---

@app.route('/consegna/start', methods=['POST'])
@login_required
def start_consegna():
    # ... (logica invariata)
    if not (current_user.has_role('admin') or current_user.has_role('autista')): return "Accesso non autorizzato", 403
    order_key = request.form.get('order_key')
    autista_nome = request.form.get('autista_nome')
    if order_key: app_data_store["delivery_events"].setdefault(order_key, {})['start_time'] = datetime.now().strftime('%H:%M:%S')
    return redirect(url_for('consegne_autista', autista_nome=autista_nome))

@app.route('/consegna/end', methods=['POST'])
@login_required
def end_consegna():
    # ... (logica invariata)
    if not (current_user.has_role('admin') or current_user.has_role('autista')): return "Accesso non autorizzato", 403
    order_key = request.form.get('order_key')
    autista_nome = request.form.get('autista_nome')
    if order_key: app_data_store["delivery_events"].setdefault(order_key, {})['end_time'] = datetime.now().strftime('%H:%M:%S')
    return redirect(url_for('consegne_autista', autista_nome=autista_nome))

def _calculate_admin_summary_data():
    """Calcola dati avanzati per la dashboard Admin."""
    dettagli_per_autista = {}
    giri_calcolati = app_data_store.get("calculated_routes", {})
    
    # Contatori generali
    consegne_totali_completate = 0
    consegne_totali_in_corso = 0
    tempo_totale_effettivo_sec = 0
    km_totali_previsti = 0.0
    consegne_per_ora = defaultdict(int) # Es: {9: 2, 10: 5, ...}
    
    # Itera sugli eventi per trovare consegne in corso o completate
    for order_key, evento in app_data_store.get("delivery_events", {}).items():
        logistic_info = app_data_store["logistics"].get(order_key)
        if not isinstance(logistic_info, dict): continue # Salta se non assegnato correttamente
        
        autista_nome = logistic_info.get('nome')
        if not autista_nome: continue

        if autista_nome not in dettagli_per_autista:
             giro_pianificato = giri_calcolati.get(autista_nome, {})
             dettagli_per_autista[autista_nome] = {
                 'summary': giro_pianificato, 
                 'consegne': [], 
                 'tempo_effettivo_sec': 0
             }

        ordine = app_data_store["orders"].get(order_key)
        if not ordine: continue
        
        status_consegna = "Assegnata"
        durata_effettiva_str = "-"
        durata_sec = 0
        ora_inizio = -1

        if 'start_time' in evento:
            status_consegna = "In Corso"
            consegne_totali_in_corso += 1
            try:
                start_dt = datetime.strptime(evento['start_time'], '%H:%M:%S')
                ora_inizio = start_dt.hour # Registra l'ora di inizio per il grafico
            except (ValueError, TypeError): pass

        if 'end_time' in evento and 'start_time' in evento:
            status_consegna = "Completata"
            consegne_totali_completate += 1
            if consegne_totali_in_corso > 0: consegne_totali_in_corso -= 1 # Non è più in corso
            try:
                start_dt = datetime.strptime(evento['start_time'], '%H:%M:%S')
                end_dt = datetime.strptime(evento['end_time'], '%H:%M:%S')
                durata_td = end_dt - start_dt
                durata_sec = durata_td.total_seconds()
                if durata_sec < 0: durata_sec += 24 * 3600 
                dettagli_per_autista[autista_nome]['tempo_effettivo_sec'] += durata_sec
                tempo_totale_effettivo_sec += durata_sec
                durata_min = math.ceil(durata_sec / 60)
                durata_effettiva_str = f"{durata_min} min"
                # Incrementa contatore per grafico consegne per ora
                if ora_inizio != -1: consegne_per_ora[ora_inizio] += 1
            except (ValueError, TypeError): pass

        order_id = str(ordine.get('numero'))
        status_ordine = app_data_store["statuses"].get(order_id, {})
        
        dettaglio_consegna = {
            'ragione_sociale': ordine.get('ragione_sociale', 'N/D'),
            'indirizzo': ordine.get('indirizzo', '-'), 'localita': ordine.get('localita', '-'),
            'start_time_reale': evento.get('start_time', '-'), 'end_time_reale': evento.get('end_time', '-'),
            'durata_effettiva': durata_effettiva_str, 'colli': status_ordine.get('colli_totali_operatore', 'N/D'),
            'status': status_consegna
        }
        dettagli_per_autista[autista_nome]['consegne'].append(dettaglio_consegna)

    # Formatta tempi totali e calcola km totali
    for autista_nome, dettagli in dettagli_per_autista.items():
         dettagli['summary']['tempo_totale_reale'] = time.strftime("%Hh %Mm", time.gmtime(dettagli['tempo_effettivo_sec']))
         try:
            giro_pianificato = dettagli.get('summary', {})
            km_autista = float(giro_pianificato.get('km_previsti', '0 km').split(' ')[0])
            km_totali_previsti += km_autista
         except ValueError: pass
            
    tempo_medio_consegna_str = "-";
    if consegne_totali_completate > 0:
        tempo_medio_sec = tempo_totale_effettivo_sec / consegne_totali_completate
        tempo_medio_min = math.ceil(tempo_medio_sec / 60); tempo_medio_consegna_str = f"{tempo_medio_min} min"
        
    summary_stats = {'consegne_totali': consegne_totali_completate, 'consegne_in_corso': consegne_totali_in_corso, 'km_totali': f"{km_totali_previsti:.1f} km", 'tempo_medio': tempo_medio_consegna_str}
    
    # Prepara dati per il grafico consegne per ora
    ore = list(range(8, 20)) # Fascia oraria 8-19
    conteggi = [consegne_per_ora.get(h, 0) for h in ore]
    chart_data = {'labels': [f"{h}:00" for h in ore], 'data': conteggi}

    return summary_stats, dettagli_per_autista, chart_data
# --- FINE FUNZIONE HELPER ---

@app.route('/amministrazione')
@login_required
def amministrazione():
    if not current_user.has_role('admin'): return "Accesso non autorizzato", 403
    # Ora riceve anche i dati per il grafico
    summary_stats, dettagli_per_autista, chart_data = _calculate_admin_summary_data() 
    return render_template('amministrazione.html', 
                           summary_stats=summary_stats,
                           dettagli_per_autista=dettagli_per_autista,
                           chart_data=chart_data, # Passa i dati del grafico al template
                           active_page='amministrazione')

@app.route('/order/<sigla>/<serie>/<numero>')
@login_required
def order_detail_view(sigla, serie, numero):
    # ... (logica invariata)
    if not (current_user.has_role('admin') or current_user.has_role('preparatore')): return "Accesso non autorizzato", 403
    if not app_data_store["orders"]: load_all_data()
    order_key = f"{sigla}:{serie}:{numero}"
    order = app_data_store["orders"].get(order_key)
    if not order: return f"Errore: Dettagli ordine {order_key} non trovati.", 404
    order_id = str(order.get('numero'))
    if order_id not in app_data_store["statuses"]: app_data_store["statuses"][order_id] = get_initial_status()
    order_state = app_data_store["statuses"].get(order_id)
    return render_template('order_detail.html', order=order, state=order_state)

@app.route('/order/<sigla>/<serie>/<numero>/action', methods=['POST'])
@login_required
def order_action(sigla, serie, numero):
    if not (current_user.has_role('admin') or current_user.has_role('preparatore')): return "Accesso non autorizzato", 403
    
    action = request.form.get('action')
    order_id = str(numero)
    current_state = app_data_store["statuses"].get(order_id)
    if not current_state: return "Stato dell'ordine non trovato.", 404
    
    order_key = f"{sigla}:{serie}:{numero}"
    order_info = app_data_store["orders"].get(order_key, {})
    order_name = f"#{order_id} ({order_info.get('ragione_sociale', 'N/D')})"

    if action == 'start_picking': current_state['status'] = 'In Picking'
    elif action == 'complete_picking':
        current_state['status'] = 'In Controllo'
        picked_qty = {key.replace('picked_qty_', ''): val for key, val in request.form.items() if key.startswith('picked_qty_')}
        colli_totali = request.form.get('colli_totali_operatore', 0)
        current_state['picked_items'] = picked_qty; current_state['colli_totali_operatore'] = colli_totali
    elif action == 'approve_order':
        current_state['status'] = 'Completato'
        # --- INVIO NOTIFICA ---
        # Invia una notifica a tutti gli utenti "admin"
        admin_users = [user for user, data in users_db.items() if 'admin' in data['roles']]
        for admin in admin_users:
            print(f"Invio notifica ad admin: {admin}")
            send_push_notification(admin, "Ordine Completato!", f"L'ordine {order_name} è pronto per la spedizione.")
        # --- FINE INVIO NOTIFICA ---
    elif action == 'reject_order':
        current_state['status'] = 'In Picking'
        
    app_data_store["statuses"][order_id] = current_state
    return redirect(url_for('order_detail_view', sigla=sigla, serie=serie, numero=numero))



@app.route('/order/<sigla>/<serie>/<numero>/stampa_prelievo')
@login_required
def stampa_lista_prelievo(sigla, serie, numero):
    if not (current_user.has_role('admin') or current_user.has_role('preparatore')):
        return "Accesso non autorizzato", 403

    order_key = f"{sigla}:{serie}:{numero}"
    order = app_data_store["orders"].get(order_key)
    if not order:
        return f"Ordine {order_key} non trovato.", 404

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=16)
    
    # Intestazione
    pdf.cell(0, 10, f"Lista Prelievo - Ordine #{order.get('numero')}", ln=True, align='C')
    pdf.set_font("Helvetica", size=12)
    pdf.cell(0, 10, f"Cliente: {order.get('ragione_sociale', 'N/D')}", ln=True, align='C')
    pdf.ln(10) # Spazio

    # Tabella Articoli
    pdf.set_font("Helvetica", 'B', size=10)
    pdf.cell(30, 8, "Codice", border=1)
    pdf.cell(100, 8, "Descrizione", border=1)
    pdf.cell(30, 8, "Qta Ordinata", border=1)
    pdf.cell(30, 8, "Qta Prel.", border=1, ln=True) # Checkbox vuoto

    pdf.set_font("Helvetica", size=10)
    for item in order.get('righe', []):
        # Calcola la quantità formattata (Colli * Pezzi)
        qta_ordinata_str = str(item.get('quantita', '0'))
        nr_colli = item.get('nr_colli')
        quantita = item.get('quantita')
        if nr_colli and nr_colli > 0 and quantita:
            try:
                pezzi_per_collo = int(quantita / nr_colli)
                qta_ordinata_str = f"{nr_colli} * {pezzi_per_collo}"
            except (ValueError, TypeError, ZeroDivisionError):
                pass # Usa la quantità semplice se il calcolo fallisce

        pdf.cell(30, 8, str(item.get('codice_articolo', '')), border=1)
        # MultiCell per descrizioni lunghe
        descrizione = item.get('descr_articolo', '')
        x = pdf.get_x()
        y = pdf.get_y()
        pdf.multi_cell(100, 8, descrizione, border=1, align='L')
        # Riposiziona X per le celle successive dopo MultiCell
        pdf.set_xy(x + 100, y) 
        pdf.cell(30, 8, qta_ordinata_str, border=1, align='C')
        pdf.cell(30, 8, "[ ]", border=1, ln=True, align='C') # Checkbox vuoto

    # Crea il PDF in memoria
    pdf_output = pdf.output(dest='S') # 'S' ritorna come stringa, encoding per bytes

    # Invia il PDF come file da scaricare
    return Response(
        io.BytesIO(pdf_output),
        mimetype='application/pdf',
        headers={'Content-Disposition': f'attachment;filename=lista_prelievo_{order.get("numero")}.pdf'}
    )

@app.route('/magazzino')
@login_required
def magazzino():
    if not (current_user.has_role('admin') or current_user.has_role('preparatore')):
        return "Accesso non autorizzato", 403
    
    query = request.args.get('q', '')
    articles_list = []
    
    if query:
        articles_data = search_articles(query) # Cerca articoli
        
        for art in articles_data:
            try:
                # Calcola giacenza netta
                esis = (float(art.get('qta_carico', 0)) - float(art.get('qta_scarico', 0)))
                disp_net = (esis - float(art.get('ord_cli_e', 0)) - float(art.get('ord_cli_sps', 0)))
                art['giacenza_netta'] = disp_net
                
                # --- NUOVA CHIAMATA PER IL PREZZO ---
                # Assumiamo listino 4 = RETAIL (come da analisi script Google)
                art['prezzo'] = get_article_price(art.get('codice'), listino_id=4)
                # --- FINE NUOVA CHIAMATA ---

            except Exception as e:
                print(f"Errore calcolo dati per {art.get('codice')}: {e}")
                art['giacenza_netta'] = 0
                art['prezzo'] = 0.0 # Default a 0.0
            
            articles_list.append(art)
    
    return render_template('magazzino.html', 
                           query=query, 
                           articles=articles_list, 
                           active_page='magazzino')

@app.route('/fabbisogno')
@login_required
def fabbisogno():
    if not (current_user.has_role('admin') or current_user.has_role('preparatore')):
        return "Accesso non autorizzato", 403

    giorno_filtro = request.args.get('giorno_filtro')
    fabbisogno_list = []
    data_selezionata_formattata = ''

    if giorno_filtro:
        orders_list = load_all_data() or []
        
        giorno_da_cercare = giorno_filtro.zfill(2)
        
        ordini_del_giorno = [
            order for order in orders_list 
            if order.get('data_documento', '').endswith(giorno_da_cercare)
        ]
        
        # --- LA CORREZIONE È QUI ---
        # Aggrega le quantità degli articoli
        fabbisogno_dict = defaultdict(lambda: {'codice': '', 'descrizione': '', 'quantita_totale': 0.0})
        for order in ordini_del_giorno:
            for item in order.get('righe', []):
                codice = item.get('codice_articolo')
                desc = item.get('descr_articolo')
                try:
                    qta = float(item.get('quantita', 0))
                except (ValueError, TypeError):
                    qta = 0.0
                
                if codice:
                    fabbisogno_dict[codice]['codice'] = codice # <-- Ho aggiunto questa riga
                    fabbisogno_dict[codice]['descrizione'] = desc
                    fabbisogno_dict[codice]['quantita_totale'] += qta
        
        fabbisogno_list = sorted(fabbisogno_dict.values(), key=lambda x: x['descrizione'])
        data_selezionata_formattata = f"Giorno: {giorno_filtro}"
    # --- FINE CORREZIONE ---
        
    return render_template('fabbisogno.html',
                           fabbisogno_list=fabbisogno_list,
                           giorno_selezionato=giorno_filtro,
                           data_selezionata_formattata=data_selezionata_formattata,
                           active_page='fabbisogno')

@app.route('/sw.js')
def service_worker():
    # Invia il file sw.js dalla cartella static
    return send_from_directory('static', 'sw.js', mimetype='application/javascript')

with app.app_context():
    print(f"Percorso database: {db_path}")
    db.create_all()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)