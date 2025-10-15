from flask import Flask, render_template, request, redirect, url_for
from mexal_api import mx_call_api, get_vettori
import time
import os
import googlemaps
from datetime import datetime

app = Flask(__name__)

# Inizializza il client di Google Maps con la chiave API dal file .env
# gmaps = googlemaps.Client(key=os.getenv('GOOGLE_MAPS_API_KEY'))

app_data_store = {
    "orders": {},
    "statuses": {},
    "logistics": {},
    "delivery_events": {}
}

def load_all_data():
    if app_data_store.get("orders"):
        return list(app_data_store["orders"].values())
    print("--- Inizio caricamento di massa dei dati dall'API ---")
    
    clients_response = mx_call_api('risorse/clienti/ricerca', method='POST', data={'Filtri': []})
    client_map = {client['codice']: client for client in (clients_response.get('dati') or [])}

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
        order['indirizzo'] = client_data.get('indirizzo', 'N/D')
        order['localita'] = client_data.get('localita', 'N/D')
        order['righe'] = rows_map.get(order_key, [])
        
        app_data_store["orders"][order_key] = order

    return orders

@app.route('/')
def dashboard():
    return render_template('dashboard.html')

@app.route('/ordini')
def ordini_list():
    orders_list = load_all_data() or []
    
    # --- NUOVA LOGICA PER IL FILTRO GIORNO ---
    giorno_filtro = request.args.get('giorno_filtro') # Legge il giorno dall'URL (es: '15')
    
    if giorno_filtro:
        # Formatta il giorno a due cifre (es: '5' diventa '05') per un confronto corretto
        giorno_da_cercare = giorno_filtro.zfill(2)
        
        filtered_list = []
        for order in orders_list:
            data_documento = order.get('data_documento', '') # es: '20251015'
            # Estrae solo gli ultimi due caratteri, che rappresentano il giorno
            if data_documento.endswith(giorno_da_cercare):
                filtered_list.append(order)
        orders_list = filtered_list
    # --- FINE NUOVA LOGICA ---

    # Ordina la lista (filtrata o completa) per data, dal più recente al più vecchio
    orders_list.sort(key=lambda order: order.get('data_documento', ''), reverse=True)

    # Prepara i dati per la visualizzazione (formattazione data, stato locale)
    for order in orders_list:
        order_id = str(order.get('numero'))
        if order_id not in app_data_store["statuses"]:
            app_data_store["statuses"][order_id] = {'status': 'Da Lavorare', 'picked_items': {}}
        order['local_status'] = app_data_store["statuses"].get(order_id, {}).get('status', 'Da Lavorare')

        date_str = order.get('data_documento')
        if date_str and len(date_str) == 8:
            year, month, day = date_str[0:4], date_str[4:6], date_str[6:8]
            order['data_formattata'] = f"{day}/{month}/{year}"
        else:
            order['data_formattata'] = "N/D"

    return render_template('orders.html', orders=orders_list, giorno_selezionato=giorno_filtro)

@app.route('/trasporto')
def trasporto():
    orders_list = load_all_data() or []
    vettori = get_vettori()
    vettori_map = {v['codice']: v.get('ragione_sociale') or v.get('descrizione') for v in vettori}
    
    for key, value in app_data_store["logistics"].items():
        if isinstance(value, str):
            app_data_store["logistics"][key] = {'codice': value, 'nome': vettori_map.get(value)}

    for order in orders_list:
        order_key = f"{order['sigla']}:{order['serie']}:{order['numero']}"
        logistic_info = app_data_store["logistics"].get(order_key)
        if logistic_info:
            order['vettore_assegnato'] = logistic_info.get('codice')

    return render_template('trasporto.html', orders=orders_list, vettori=vettori)
    
# ... (tutte le altre funzioni rimangono invariate) ...

@app.route('/assign_vettore', methods=['POST'])
def assign_vettore():
    order_key = request.form.get('order_key')
    vettore_codice = request.form.get('vettore_codice')
    if order_key:
        app_data_store["logistics"][order_key] = vettore_codice
    return redirect(url_for('trasporto'))

@app.route('/calcola-giri')
def calcola_giri():
    giri_per_vettore = {}
    for order_key, logistic_info in app_data_store["logistics"].items():
        if isinstance(logistic_info, dict):
            vettore_nome = logistic_info.get('nome', 'Sconosciuto')
            if vettore_nome not in giri_per_vettore: giri_per_vettore[vettore_nome] = []
            ordine_completo = app_data_store["orders"].get(order_key)
            if ordine_completo: giri_per_vettore[vettore_nome].append(ordine_completo)
    giri_calcolati = {}
    for vettore, ordini in giri_per_vettore.items():
        if not ordini: continue
        origin = "Japlab, Via Ferraris, 3, 84018 Scafati SA"
        waypoints = [f"{o['indirizzo']}, {o['localita']}" for o in ordini if o.get('indirizzo') and o.get('localita')]
        if not waypoints: continue
        try:
            gmaps = googlemaps.Client(key=os.getenv('GOOGLE_MAPS_API_KEY'))
            directions_result = gmaps.directions(origin=origin, destination=origin, waypoints=waypoints, optimize_waypoints=True)
            if not directions_result: continue
            route = directions_result[0]
            distanza_totale_metri = sum(leg['distance']['value'] for leg in route['legs'])
            durata_totale_secondi = sum(leg['duration']['value'] for leg in route['legs'])
            ordine_ottimizzato = [ordini[i] for i in route['waypoint_order']]
            giri_calcolati[vettore] = {'distanza_totale': f"{distanza_totale_metri / 1000:.1f} km", 'durata_totale': time.strftime("%Hh %Mm", time.gmtime(durata_totale_secondi)), 'tappe_ordinate': ordine_ottimizzato}
        except Exception as e:
            print(f"Errore durante il calcolo del percorso per {vettore}: {e}")
    return render_template('consegne.html', giri_calcolati=giri_calcolati)

@app.route('/autisti')
def autisti():
    return render_template('autisti.html')

@app.route('/consegne/<autista_nome>')
def consegne_autista(autista_nome):
    ordini_assegnati = []
    for order_key, logistic_info in app_data_store["logistics"].items():
        if isinstance(logistic_info, dict) and logistic_info.get('nome') == autista_nome:
            ordine_completo = app_data_store["orders"].get(order_key)
            if ordine_completo: ordini_assegnati.append(ordine_completo)
    tappe_ordinate = ordini_assegnati
    for tappa in tappe_ordinate:
        order_key = f"{tappa['sigla']}:{tappa['serie']}:{tappa['numero']}"
        eventi = app_data_store["delivery_events"].get(order_key, {})
        tappa['start_time'] = eventi.get('start_time')
        tappa['end_time'] = eventi.get('end_time')
    return render_template('consegna_autista.html', autista_nome=autista_nome, tappe=tappe_ordinate)

@app.route('/consegna/start', methods=['POST'])
def start_consegna():
    order_key = request.form.get('order_key')
    autista_nome = request.form.get('autista_nome')
    if order_key:
        app_data_store["delivery_events"].setdefault(order_key, {})['start_time'] = datetime.now().strftime('%H:%M:%S')
    return redirect(url_for('consegne_autista', autista_nome=autista_nome))

@app.route('/consegna/end', methods=['POST'])
def end_consegna():
    order_key = request.form.get('order_key')
    autista_nome = request.form.get('autista_nome')
    if order_key:
        app_data_store["delivery_events"].setdefault(order_key, {})['end_time'] = datetime.now().strftime('%H:%M:%S')
    return redirect(url_for('consegne_autista', autista_nome=autista_nome))

@app.route('/amministrazione')
def amministrazione():
    eventi_per_autista = {}
    for order_key, logistic_info in app_data_store["logistics"].items():
        if isinstance(logistic_info, dict):
            autista_nome = logistic_info.get('nome')
            evento = app_data_store["delivery_events"].get(order_key)
            if autista_nome and evento and 'end_time' in evento:
                if autista_nome not in eventi_per_autista: eventi_per_autista[autista_nome] = []
                ordine = app_data_store["orders"].get(order_key)
                dettaglio_evento = {'ragione_sociale': ordine.get('ragione_sociale', 'N/D'), 'start_time': evento.get('start_time', '-'), 'end_time': evento.get('end_time', '-')}
                eventi_per_autista[autista_nome].append(dettaglio_evento)
    return render_template('amministrazione.html', eventi_per_autista=eventi_per_autista)

@app.route('/order/<sigla>/<serie>/<numero>')
def order_detail_view(sigla, serie, numero):
    if not app_data_store["orders"]: load_all_data()
    order_key = f"{sigla}:{serie}:{numero}"
    order = app_data_store["orders"].get(order_key)
    if not order: return f"Errore: Dettagli per l'ordine {order_key} non trovati.", 404
    order_id = str(order.get('numero'))
    order_state = app_data_store["statuses"].get(order_id, {'status': 'Da Lavorare', 'picked_items': {}})
    return render_template('order_detail.html', order=order, state=order_state)

@app.route('/order/<sigla>/<serie>/<numero>/action', methods=['POST'])
def order_action(sigla, serie, numero):
    action = request.form.get('action')
    order_id = str(numero)
    current_state = app_data_store["statuses"].get(order_id)
    if not current_state: return "Stato dell'ordine non trovato.", 404
    if action == 'start_picking': current_state['status'] = 'In Picking'
    elif action == 'complete_picking':
        current_state['status'] = 'In Controllo'
        picked = {key.replace('picked_', ''): value for key, value in request.form.items() if key.startswith('picked_')}
        current_state['picked_items'] = picked
    elif action == 'approve_order': current_state['status'] = 'Completato'
    elif action == 'reject_order': current_state['status'] = 'In Picking'
    app_data_store["statuses"][order_id] = current_state
    return redirect(url_for('order_detail_view', sigla=sigla, serie=serie, numero=numero))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)