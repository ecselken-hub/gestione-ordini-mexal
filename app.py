from flask import Flask, render_template, request, redirect, url_for
from mexal_api import mx_call_api, get_vettori, get_shipping_address, get_dati_aggiuntivi, get_payment_methods
import time
import os
import googlemaps
from datetime import datetime, timedelta

app = Flask(__name__)

# gmaps = googlemaps.Client(key=os.getenv('GOOGLE_MAPS_API_KEY'))

app_data_store = {
    "orders": {}, "statuses": {}, "logistics": {}, "delivery_events": {}, "calculated_routes": {}
}

def get_initial_status():
    """Cria um dicionário de status padrão para um novo pedido."""
    return {'status': 'Da Lavorare', 'picked_items': {}, 'colli_totali_operatore': 0}

def load_all_data():
    if app_data_store.get("orders"): return list(app_data_store["orders"].values())
    
    print("--- Início do carregamento em massa de dados da API ---")
    
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
        order['valore_merci'] = order.get('totale_doc', 0.0)
        
        order['righe'] = rows_map.get(order_key, [])
        app_data_store["orders"][order_key] = order

    return orders

@app.route('/')
def dashboard():
    return redirect(url_for('ordini_list'))

@app.route('/ordini')
def ordini_list():
    orders_list = load_all_data() or []
    giorno_filtro = request.args.get('giorno_filtro')
    if giorno_filtro:
        giorno_da_cercare = giorno_filtro.zfill(2)
        orders_list = [order for order in orders_list if order.get('data_documento', '').endswith(giorno_da_cercare)]
    
    orders_list.sort(key=lambda order: order.get('data_documento', ''), reverse=True)
    for order in orders_list:
        order_id = str(order.get('numero'))
        if order_id not in app_data_store["statuses"]:
            app_data_store["statuses"][order_id] = get_initial_status()
        order['local_status'] = app_data_store["statuses"].get(order_id, {}).get('status', 'Da Lavorare')
        date_str = order.get('data_documento')
        if date_str and len(date_str) == 8:
            order['data_formattata'] = f"{date_str[6:8]}/{date_str[4:6]}/{date_str[0:4]}"
        else:
            order['data_formattata'] = "N/D"
    return render_template('orders.html', orders=orders_list, giorno_selezionato=giorno_filtro, active_page='ordini')

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
    return render_template('trasporto.html', orders=orders_list, vettori=vettori, active_page='trasporto')
    
@app.route('/assign_all_vettori', methods=['POST'])
def assign_all_vettori():
    for order_key, vettore_codice in request.form.items():
        if vettore_codice: 
            app_data_store["logistics"][order_key] = vettore_codice
        else: 
            if order_key in app_data_store["logistics"]:
                del app_data_store["logistics"][order_key]
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
            tappe_ordinate_oggetti = [ordini_assegnati[i] for i in route['waypoint_order']]
            distanza_complessiva_km = sum(leg['distance']['value'] for leg in route['legs']) / 1000
            durata_complessiva_sec = sum(leg['duration']['value'] for leg in route['legs'])
            rientro_previsto = partenza_prevista + timedelta(seconds=durata_complessiva_sec)
            
            orario_tappa_corrente = partenza_prevista
            for i, leg in enumerate(route['legs'][:-1]):
                orario_tappa_corrente += timedelta(seconds=leg['duration']['value'])
                tappa_attuale = tappe_ordinate_oggetti[i]
                tappa_attuale['orario_previsto'] = orario_tappa_corrente.strftime('%H:%M')
            
            app_data_store["calculated_routes"][vettore] = {
                'data': datetime.now().strftime('%d/%m/%Y'),
                'partenza_max': (partenza_prevista - timedelta(minutes=30)).strftime('%H:%M'),
                'num_consegne': len(tappe_ordinate_oggetti),
                'km_previsti': f"{distanza_complessiva_km:.1f} km",
                'tempo_previsto': time.strftime("%Hh %Mm", time.gmtime(durata_complessiva_sec)),
                'rientro_previsto': rientro_previsto.strftime('%H:%M'),
                'tappe': tappe_ordinate_oggetti,
                'efficienza': 'N/D', 'consumo_carburante': 'N/D'
            }
        except Exception as e:
            print(f"Errore durante o cálculo da rota para {vettore}: {e}")
    
    return redirect(url_for('autisti'))

@app.route('/autisti')
def autisti():
    return render_template('autisti.html', active_page='autisti')

@app.route('/consegne/<autista_nome>')
def consegne_autista(autista_nome):
    giro_calcolato = app_data_store["calculated_routes"].get(autista_nome)
    tappe_da_mostrare = []
    if giro_calcolato:
        tappe_da_mostrare = giro_calcolato.get('tappe', [])
    else:
        for order_key, logistic_info in app_data_store["logistics"].items():
            if isinstance(logistic_info, dict) and logistic_info.get('nome') == autista_nome:
                ordine_completo = app_data_store["orders"].get(order_key)
                if ordine_completo:
                    tappe_da_mostrare.append(ordine_completo)
    
    for tappa in tappe_da_mostrare:
        order_key = f"{tappa['sigla']}:{tappa['serie']}:{tappa['numero']}"
        order_id = str(tappa.get('numero'))
        eventi = app_data_store["delivery_events"].get(order_key, {})
        status = app_data_store["statuses"].get(order_id, {})
        tappa['start_time'] = eventi.get('start_time')
        tappa['end_time'] = eventi.get('end_time')
        tappa['colli_da_consegnare'] = status.get('colli_totali_operatore', 'N/D')
            
    return render_template('consegna_autista.html', autista_nome=autista_nome, giro=giro_calcolato, tappe=tappe_da_mostrare)

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
                dettaglio_evento = {
                    'ragione_sociale': ordine.get('ragione_sociale', 'N/D'),
                    'indirizzo': ordine.get('indirizzo', '-'), 'localita': ordine.get('localita', '-'),
                    'start_time': evento.get('start_time', '-'), 'end_time': evento.get('end_time', '-')
                }
                eventi_per_autista[autista_nome].append(dettaglio_evento)
    return render_template('amministrazione.html', eventi_per_autista=eventi_per_autista, active_page='amministrazione')

@app.route('/order/<sigla>/<serie>/<numero>')
def order_detail_view(sigla, serie, numero):
    if not app_data_store["orders"]: load_all_data()
    order_key = f"{sigla}:{serie}:{numero}"
    order = app_data_store["orders"].get(order_key)
    if not order: return f"Erro: Detalhes do pedido {order_key} não encontrados.", 404
    order_id = str(order.get('numero'))
    if order_id not in app_data_store["statuses"]:
        app_data_store["statuses"][order_id] = get_initial_status()
    order_state = app_data_store["statuses"].get(order_id)
    return render_template('order_detail.html', order=order, state=order_state)

@app.route('/order/<sigla>/<serie>/<numero>/action', methods=['POST'])
def order_action(sigla, serie, numero):
    action = request.form.get('action')
    order_id = str(numero)
    current_state = app_data_store["statuses"].get(order_id)
    if not current_state: return "Status do pedido não encontrado.", 404
    if action == 'start_picking':
        current_state['status'] = 'In Picking'
    elif action == 'complete_picking':
        current_state['status'] = 'In Controllo'
        picked_qty = {key.replace('picked_qty_', ''): value for key, value in request.form.items() if key.startswith('picked_qty_')}
        colli_totali = request.form.get('colli_totali_operatore', 0)
        current_state['picked_items'] = picked_qty
        current_state['colli_totali_operatore'] = colli_totali
    elif action == 'approve_order':
        current_state['status'] = 'Completato'
    elif action == 'reject_order':
        current_state['status'] = 'In Picking'
    app_data_store["statuses"][order_id] = current_state
    return redirect(url_for('order_detail_view', sigla=sigla, serie=serie, numero=numero))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)