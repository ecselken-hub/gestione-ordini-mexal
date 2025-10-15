from flask import Flask, render_template, request, redirect, url_for
from mexal_api import mx_call_api
import time

app = Flask(__name__)

# Usiamo un dizionario in memoria per conservare lo stato e i dati completi degli ordini.
app_data_store = {}

def load_all_data():
    """
    Questa funzione replica la logica di Google Sheets: carica tutto in memoria.
    """
    print("--- Inizio caricamento di massa dei dati ---")
    
    # 1. Carica tutti i clienti
    clients_response = mx_call_api('risorse/clienti/ricerca', method='POST', data={'Filtri': []})
    client_map = {}
    if clients_response and clients_response.get('dati'):
        for client in clients_response['dati']:
            client_map[client['codice']] = client
    print(f"Caricati {len(client_map)} clienti.")

    # 2. Carica tutte le testate degli ordini
    orders_response = mx_call_api('risorse/documenti/ordini-clienti/ricerca', method='POST', data={'Filtri': []})
    if not orders_response or not orders_response.get('dati'):
        print("!!! Fallito caricamento testate ordini.")
        return None
    orders = orders_response['dati']
    print(f"Caricate {len(orders)} testate ordini.")

    # 3. Carica tutte le righe degli ordini (ipotizzando l'endpoint corretto)
    rows_response = mx_call_api('risorse/documenti/ordini-clienti/righe/ricerca', method='POST', data={'Filtri': []})
    rows_map = {}
    if rows_response and rows_response.get('dati'):
        for row in rows_response['dati']:
            order_key = f"{row['sigla']}:{row['serie']}:{row['numero']}"
            if order_key not in rows_map:
                rows_map[order_key] = []
            rows_map[order_key].append(row)
    print(f"Caricate righe per {len(rows_map)} ordini.")

    # 4. Combina tutti i dati in un unico posto
    for order in orders:
        order_key = f"{order['sigla']}:{order['serie']}:{order['numero']}"
        client_code = order.get('cod_conto')
        
        # Aggiungi i dettagli del cliente
        client_data = client_map.get(client_code)
        order['ragione_sociale'] = client_data.get('ragione_sociale', 'N/D') if client_data else 'N/D'
        order['indirizzo'] = client_data.get('indirizzo', 'N/D') if client_data else 'N/D'
        
        # Aggiungi le righe degli articoli
        order['righe'] = rows_map.get(order_key, [])
        
        # Salva l'ordine completo nel nostro store
        app_data_store[order_key] = order

    print("--- Caricamento di massa completato ---")
    return orders

@app.route('/')
def home():
    """Pagina principale che mostra la lista degli ordini."""
    orders_list = load_all_data()
    if orders_list is None:
        return "Errore: Impossibile recuperare i dati dall'API.", 500
    
    # Prepara i dati per il template (aggiungendo lo stato locale)
    for order in orders_list:
        order_id = str(order.get('numero')) 
        if order_id not in app_data_store:
            app_data_store[order_id] = {'status': 'Da Lavorare', 'picked_items': {}}
        order['local_status'] = app_data_store.get(order_id, {}).get('status', 'Da Lavorare')

    return render_template('orders.html', orders=orders_list)

@app.route('/order/<sigla>/<serie>/<numero>')
def order_detail_view(sigla, serie, numero):
    """Pagina di dettaglio che recupera i dati pre-caricati."""
    order_key = f"{sigla}:{serie}:{numero}"
    order = app_data_store.get(order_key)

    if not order:
        return f"Errore: Dettagli per l'ordine {order_key} non trovati. Prova a ricaricare la home page.", 404

    order_id = str(order.get('numero'))
    order_state = app_data_store.get(order_id, {'status': 'Da Lavorare', 'picked_items': {}})
    
    return render_template('order_detail.html', order=order, state=order_state)

@app.route('/order/<sigla>/<serie>/<numero>/action', methods=['POST'])
def order_action(sigla, serie, numero):
    """Gestisce le azioni (es. avvia picking, completa ordine)."""
    action = request.form.get('action')
    order_id = str(numero)
    current_state = app_data_store.get(order_id)

    if not current_state:
        return "Stato dell'ordine non trovato.", 404

    if action == 'start_picking':
        current_state['status'] = 'In Picking'
    elif action == 'complete_picking':
        current_state['status'] = 'In Controllo'
        picked = {}
        for key, value in request.form.items():
            if key.startswith('picked_'):
                codice_articolo = key.replace('picked_', '')
                picked[codice_articolo] = value
        current_state['picked_items'] = picked
    elif action == 'approve_order':
        current_state['status'] = 'Completato'
    elif action == 'reject_order':
        current_state['status'] = 'In Picking'

    app_data_store[order_id] = current_state
    return redirect(url_for('order_detail_view', sigla=sigla, serie=serie, numero=numero))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)