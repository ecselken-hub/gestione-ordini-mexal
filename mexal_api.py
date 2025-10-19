import requests
import os
from dotenv import load_dotenv
import time
from datetime import datetime

# Carrega as variáveis do arquivo .env
load_dotenv()

API_BASE_URL = 'https://93.148.248.104:9004/webapi/'
AUTH_TOKEN = os.getenv('MX_AUTH')

def mx_call_api(endpoint, method='GET', data=None):
    if not AUTH_TOKEN:
        print("Errore: Il token di autenticazione MX_AUTH non è stato configurato.")
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
        print(f"Errore nella chiamata all'API in {full_url}: {e}")
        if e.response is not None:
            print(f"!!! DETTAGLI DELL'ERRORE DEL SERVER: {e.response.text} !!!")
        return None

def get_vettori():
    endpoint = 'risorse/fornitori/ricerca'
    response = mx_call_api(endpoint, method='POST', data={'Filtri': []})
    
    if response and response.get('dati'):
        todos_os_fornecedores = response['dati']
        nomes_a_incluir = ["BOXER", "EXPERT"]
        vetores_filtrados = [
            fornecedor for fornecedor in todos_os_fornecedores 
            if fornecedor.get('ragione_sociale', '').upper() in nomes_a_incluir
        ]
        return vetores_filtrados
        
    return []

def get_shipping_address(address_id):
    if not address_id:
        return None
    encoded_id = str(address_id).encode('utf-8').hex()
    endpoint = f"risorse/indirizzi-spedizione/{encoded_id}?encoding=hex"
    response = mx_call_api(endpoint, method='GET')
    if response and response.get('dati'):
        return response['dati']
    return None

def get_dati_aggiuntivi(client_code):
    if not client_code:
        return {} 
    encoded_id = str(client_code).encode('utf-8').hex()
    endpoint = f"risorse/clienti/{encoded_id}/dati-aggiuntivi?encoding=hex"
    response = mx_call_api(endpoint, method='GET')
    if response and response.get('dati'):
        return response['dati']
    return {}

def get_payment_methods():
    endpoint = 'risorse/dati-generali/pagamenti/ricerca'
    response = mx_call_api(endpoint, method='POST', data={'Filtri': []})
    if response and response.get('dati'):
        return {metodo['id']: metodo.get('descrizione', 'N/D') for metodo in response['dati']}
    return {}

def search_articles(query):
    """
    Cerca gli articoli tramite API usando un termine di ricerca,
    richiedendo anche la 'descr_completa'.
    """
    # --- LA CORREZIONE: Aggiunto 'descr_completa' alla lista campi ---
    campi_richiesti = "codice,descrizione,descr_completa,qta_carico,qta_scarico,ord_cli_e,ord_cli_sps"
    endpoint = f'risorse/articoli/ricerca?fields={campi_richiesti}'
    
    search_data = {
        'filtri': [
            {
                'campo': 'descrizione', 
                'condizione': 'contiene', 
                'valore': query,
                'case_insensitive': True
            }
        ]
    }
    
    response = mx_call_api(endpoint, method='POST', data=search_data)
    
    if response and response.get('dati'):
        return response['dati']
        
    return []

def get_article_price(codice_articolo, listino_id=4):
    """
    Recupera il prezzo di un articolo usando il SERVIZIO 'condizioni_documento',
    come documentato in ManWebAPI.pdf (pag. 52).
    """
    endpoint = 'servizi' # Si tratta di un SERVIZIO, non una RISORSA
    
    # Il servizio richiede una data e un cliente fittizio per il calcolo
    today_date = datetime.now().strftime('%Y%m%d')
    # Usiamo un codice cliente di default, come da documentazione (pag. 52, [2051])
    default_client = "501.00085" 
    
    search_data = {
        "cmd": "condizioni_documento",
        "dati": {
            "tipo": 1, # 1: prezzo, sconto e provvigione
            "cod_conto": 501.00085,
            "codice_articolo": codice_articolo, # <-- Il nome campo corretto
            "data_documento": today_date,
            "sigla_documento": "OC",
            "quantita": 1,
            "id_listino": listino_id
        }
    }
    
    response = mx_call_api(endpoint, method='POST', data=search_data)
    
    # La risposta di un servizio è diversa, non ha 'dati'
    # ManWebAPI.pdf (pag. 52, sorgente [2075])
    if response and response.get('prezzo') is not None:
        return float(response.get('prezzo', 0.0))
        
    print(f"Prezzo non trovato per {codice_articolo}, risposta: {response}")
    return 0.0