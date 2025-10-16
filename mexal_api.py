import requests
import os
from dotenv import load_dotenv
import time

# Carica le variabili dal file .env
load_dotenv()

API_BASE_URL = 'https://93.148.248.104:9004/webapi/'
AUTH_TOKEN = os.getenv('MX_AUTH')

def mx_call_api(endpoint, method='GET', data=None):
    """
    Funzione generica per chiamare l'API Mexal.
    """
    if not AUTH_TOKEN:
        print("Errore: Il token di autenticazione MX_AUTH non è stato impostato.")
        return None

    headers = {
        'Authorization': f'Passepartout {AUTH_TOKEN}',
        'Coordinate-Gestionale': 'Azienda=SRL Anno=2025 Magazzino=3',
        'Content-Type': 'application/json;charset=utf-8'
    }

    full_url = f"{API_BASE_URL}{endpoint}"

    try:
        if method.upper() == 'POST':
            response = requests.post(full_url, headers=headers, json=data, timeout=45, verify=False)
        else:
            response = requests.get(full_url, headers=headers, timeout=45, verify=False)

        response.raise_for_status()
        return response.json()

    except requests.exceptions.RequestException as e:
        print(f"Errore durante la chiamata API a {full_url}: {e}")
        if e.response is not None:
            print(f"!!! DETTAGLIO ERRORE DAL SERVER: {e.response.text} !!!")
        return None

def get_vettori():
    """
    Recupera la lista di tutti i fornitori (che usiamo come vettori)
    e la filtra per includere solo 'BOXER' e 'EXPERT'.
    """
    endpoint = 'risorse/fornitori/ricerca'
    
    # 1. Scarichiamo l'intera lista di fornitori, come prima.
    response = mx_call_api(endpoint, method='POST', data={'Filtri': []})
    
    if response and response.get('dati'):
        tutti_i_fornitori = response['dati']
        vettori_filtrati = []
        
        # 2. Creiamo una lista dei nomi che vogliamo includere.
        nomi_da_includere = ["BOXER", "EXPERT"]
        
        # 3. Iteriamo sulla lista completa e selezioniamo solo quelli che ci servono.
        for fornitore in tutti_i_fornitori:
            # Controlliamo se la 'ragione_sociale' del fornitore è nella nostra lista.
            # Usiamo .upper() per ignorare differenze tra maiuscole e minuscole.
            if fornitore.get('ragione_sociale', '').upper() in nomi_da_includere:
                vettori_filtrati.append(fornitore)
                
        return vettori_filtrati
        
    return []

def get_shipping_address(address_id):
    """
    Recupera un singolo indirizzo di spedizione usando il suo ID codificato in HEX,
    come richiesto dalla documentazione e dalla logica di Google Sheets.
    """
    if not address_id:
        return None
    
    # 1. Codifichiamo l'ID in esadecimale (HEX).
    encoded_id = str(address_id).encode('utf-8').hex()
    
    # 2. Costruiamo l'URL per l'accesso diretto, specificando l'encoding.
    endpoint = f"risorse/indirizzi-spedizione/{encoded_id}?encoding=hex"
    
    # 3. Eseguiamo una semplice chiamata GET.
    response = mx_call_api(endpoint, method='GET')
    
    if response and response.get('dati'):
        return response['dati']
        
    return None

def get_dati_aggiuntivi(client_code):
    """
    Recupera i dati aggiuntivi di un cliente (inclusi gli orari di consegna)
    usando l'accesso diretto con ID codificato.
    """
    if not client_code:
        return None
        
    encoded_id = str(client_code).encode('utf-8').hex()
    
    # L'endpoint per i dati aggiuntivi è una "sotto-risorsa" del cliente
    endpoint = f"risorse/clienti/{encoded_id}/dati-aggiuntivi?encoding=hex"
    
    response = mx_call_api(endpoint, method='GET')
    
    if response and response.get('dati'):
        return response['dati']
        
    return {}

def get_payment_methods():
    """
    Recupera la lista di tutti i metodi di pagamento.
    """
    endpoint = 'risorse/dati-generali/pagamenti/ricerca'
    response = mx_call_api(endpoint, method='POST', data={'Filtri': []})
    if response and response.get('dati'):
        # Trasforma la lista in un dizionario per un accesso rapido: {id: descrizione}
        return {metodo['id']: metodo.get('descrizione', 'N/D') for metodo in response['dati']}
    return {}