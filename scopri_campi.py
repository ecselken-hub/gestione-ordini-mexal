from flask import Flask, render_template, request, redirect, url_for
from mexal_api import mx_call_api, get_client_details
import time

app = Flask(__name__)
order_statuses = {}

@app.route('/')
def home():
    """Pagina principale che mostra la lista degli ordini."""
    response_data = mx_call_api('risorse/documenti/ordini-clienti')

    if not response_data or 'dati' not in response_data:
        return "Errore: Impossibile recuperare gli ordini dall'API.", 500

    orders = response_data['dati']
    
    for order in orders:
        client_details = get_client_details(order['cod_conto'])
        if client_details:
            order['ragione_sociale'] = client_details.get('ragione_sociale', 'N/D')
        else:
            order['ragione_sociale'] = 'Cliente non trovato'

        order_id = str(order.get('numero')) 
        if order_id not in order_statuses:
            order_statuses[order_id] = {'status': 'Da Lavorare', 'picked_items': {}}
        order['local_status'] = order_statuses[order_id]['status']

    return render_template('orders.html', orders=orders)

@app.route('/order/<sigla>/<serie>/<numero>')
def order_detail_view(sigla, serie, numero):
    """Pagina di dettaglio che usa l'endpoint corretto dalla documentazione."""
    
    # --- LA SOLUZIONE: Costruiamo l'URL con '+' come separatore ---
    order_key = f"{sigla}+{serie}+{numero}"
    endpoint = f"risorse/documenti/ordini-clienti/{order_key}"
    # -----------------------------------------------------------------
    
    response = mx_call_api(endpoint)

    if not response or 'dati' not in response:
        return f"Errore: Impossibile recuperare i dettagli per l'ordine {order_key}. Endpoint non funzionante.", 404
    
    # La risposta ora contiene l'ordine completo, incluse le righe
    order = response['dati']

    # Arricchisci con i dettagli del cliente (la logica non cambia)
    client_details = get_client_details(order['cod_conto'])
    if client_details:
        order['ragione_sociale'] = client_details.get('ragione_sociale', 'N/D')
        order['indirizzo'] = client_details.get('indirizzo', 'N/D')
    else:
        order['ragione_sociale'] = 'Cliente non trovato'
        order['indirizzo'] = ''

    status_id = str(order.get('numero'))
    order_state = order_statuses.get(status_id, {'status': 'Da Lavorare', 'picked_items': {}})
    return render_template('order_detail.html', order=order, state=order_state)

@app.route('/order/<sigla>/<serie>/<numero>/action', methods=['POST'])
def order_action(sigla, serie, numero):
    """Gestisce le azioni (es. avvia picking, completa ordine)."""
    action = request.form.get('action')
    status_id = request.form.get('order_numero')
    current_state = order_statuses.get(status_id)

    if not current_state:
        return "Stato dell'ordine non trovato.", 404

    # Logica per aggiornare lo stato (invariata)
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

    order_statuses[status_id] = current_state
    return redirect(url_for('order_detail_view', sigla=sigla, serie=serie, numero=numero))

if __name__ == '__main__':
    app.run(debug=True, port=5001)