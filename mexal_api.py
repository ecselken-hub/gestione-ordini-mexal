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