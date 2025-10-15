import requests
import os
from dotenv import load_dotenv
import time
from urllib.parse import quote 

load_dotenv()

API_BASE_URL = 'https://93.148.248.104:9004/webapi/'
AUTH_TOKEN = os.getenv('MX_AUTH')

def mx_call_api(endpoint, method='GET', data=None):
    """Funzione generica per chiamare l'API Mexal."""
    if not AUTH_TOKEN: return None
    headers = {
        'Authorization': f'Passepartout {AUTH_TOKEN}',
        'Coordinate-Gestionale': 'Azienda=SRL Anno=2025 Magazzino=3',
        'Content-Type': 'application/json;charset=utf-8'
    }
    # Assicuriamoci che il path inizi sempre con 'risorse/'
    full_url = f"{API_BASE_URL}risorse/{endpoint}"
    try:
        if method.upper() == 'POST':
            response = requests.post(full_url, headers=headers, json=data, timeout=45, verify=False)
        else:
            response = requests.get(full_url, headers=headers, timeout=45, verify=False)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException:
        return None

def get_client_details(client_code):
    """
    Recupera i dettagli di un cliente usando il metodo GET diretto, come da documentazione.
    Questo metodo risolve il problema del caching.
    """
    # Usiamo quote() per codificare correttamente eventuali caratteri speciali nel codice cliente
    encoded_client_code = quote(client_code)
    endpoint = f"risorse/clienti/{encoded_client_code}"
    
    response = mx_call_api(endpoint, method='GET')
    
    # La risposta per un singolo elemento ha i dati direttamente sotto la chiave 'dati'
    if response and 'dati' in response:
        return response['dati']
    
    print(f"AVVISO: Cliente non trovato con il metodo GET per il codice {client_code}.")
    return None

def get_order_rows(sigla, serie, numero):
    """
    Recupera solo le righe di un ordine specifico tramite ricerca.
    """
    endpoint = 'documenti/ordini-clienti/righe/ricerca'
    
    search_data = {
        'Filtri': [
            {'Campo': 'sigla', 'Operatore': '=', 'Valore': str(sigla)},
            {'Campo': 'serie', 'Operatore': '=', 'Valore': int(serie)},
            {'Campo': 'numero', 'Operatore': '=', 'Valore': int(numero)}
        ]
    }
    
    response = mx_call_api(endpoint, method='POST', data=search_data)
    
    if response and 'dati' in response:
        return response['dati']
        
    return []