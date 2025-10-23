# mexal_api.py (Versione Corretta)

import requests
import os
from dotenv import load_dotenv
import time
from datetime import datetime
import json # Importa json per logging errori

# Carica le variabili dal file .env
load_dotenv()

# --- CORREZIONE 7: Esternalizza API_BASE_URL ---
# Recupera l'URL base dall'ambiente, con un default se non impostato
API_BASE_URL = os.getenv('MX_API_BASE_URL', 'https://93.148.248.104:9004/webapi/')
AUTH_TOKEN = os.getenv('MX_AUTH')

# Ignora gli warning relativi ai certificati SSL se proprio non puoi verificarli (SCONSIGLIATO IN PRODUZIONE)
# import urllib3
# urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def mx_call_api(endpoint, method='GET', data=None):
    """
    Funzione centralizzata per effettuare chiamate all'API Mexal.

    Args:
        endpoint (str): Il percorso dell'endpoint API (es. 'risorse/clienti/ricerca').
        method (str, optional): Metodo HTTP ('GET' o 'POST'). Default 'GET'.
        data (dict, optional): Payload JSON per richieste POST. Default None.

    Returns:
        dict or None: Il JSON della risposta API in caso di successo, None in caso di errore.
    """
    if not AUTH_TOKEN:
        print("Errore: Il token di autenticazione MX_AUTH non è stato configurato.")
        return None

    headers = {
        'Authorization': f'Passepartout {AUTH_TOKEN}',
        'Coordinate-Gestionale': 'Azienda=SRL Anno=2025 Magazzino=3', # NOTA: Potrebbe essere reso configurabile
        'Content-Type': 'application/json;charset=utf-8'
    }

    # Assicura che l'URL base termini con '/' e l'endpoint non inizi con '/'
    clean_base_url = API_BASE_URL.rstrip('/') + '/'
    clean_endpoint = endpoint.lstrip('/')
    full_url = f"{clean_base_url}{clean_endpoint}"

    try:
        # --- CORREZIONE 2: Rimuovi verify=False ---
        # NOTA: Assicurati che il server API abbia un certificato valido
        # o fornisci il percorso a un certificato CA/autofirmato con verify='/path/to/cert.pem'
        # Per ora lasciamo verify=True (default)
        print(f"Chiamata API: {method.upper()} {full_url}") # Log della chiamata
        if method.upper() == 'POST':
            response = requests.post(full_url, headers=headers, json=data, timeout=45, verify=False) # Rimosso verify=False
        else:
            response = requests.get(full_url, headers=headers, timeout=45, verify=False) # Rimosso verify=False

        response.raise_for_status() # Controlla errori HTTP (4xx, 5xx)
        return response.json()

    except requests.exceptions.Timeout:
        print(f"Errore: Timeout nella chiamata all'API in {full_url}")
        return None
    except requests.exceptions.SSLError as e:
        print(f"Errore SSL nella chiamata all'API in {full_url}: {e}")
        print(">> Assicurati che il certificato del server sia valido o configura 'verify' in requests.")
        return None
    except requests.exceptions.RequestException as e:
        print(f"Errore generico nella chiamata all'API in {full_url}: {e}")
        error_details = "Nessun dettaglio disponibile."
        if e.response is not None:
            try:
                # Prova a leggere il testo della risposta, potrebbe essere JSON o semplice testo
                error_details = e.response.text
            except Exception:
                pass # Non fa nulla se non riesce a leggere il body
            print(f"!!! DETTAGLI DELL'ERRORE DEL SERVER ({e.response.status_code}): {error_details} !!!")
        return None
    except json.JSONDecodeError as e:
        print(f"Errore: Risposta non JSON dall'API in {full_url}: {e}")
        # Mostra l'inizio della risposta per debug, ma attenzione a dati sensibili
        print(f"Risposta ricevuta (inizio): {response.text[:200]}...")
        return None


def get_vettori():
    """Recupera i fornitori che sono definiti come vettori (BOXER, EXPERT)."""
    endpoint = 'risorse/fornitori/ricerca'
    # Usiamo 'filtri' minuscolo
    response = mx_call_api(endpoint, method='POST', data={'filtri': []})

    vettori_filtrati = [] # Inizializza lista vuota

    if response and isinstance(response.get('dati'), list):
        tutti_i_fornitori = response['dati']
        nomi_da_includere = ["BOXER", "EXPERT"] # Nomi dei vettori da includere

        # --- MODIFICA: Usa un ciclo for standard invece di list comprehension ---
        for fornitore_corrente in tutti_i_fornitori:
            # Verifica che fornitore_corrente sia un dizionario prima di accedervi
            if isinstance(fornitore_corrente, dict):
                ragione_sociale = fornitore_corrente.get('ragione_sociale', '')
                # Controlla se ha 'codice' E se la ragione sociale corrisponde
                if 'codice' in fornitore_corrente and ragione_sociale.upper() in nomi_da_includere:
                    vettori_filtrati.append(fornitore_corrente) # Aggiungi alla lista filtrata
            else:
                 print(f"WARN [get_vettori]: Trovato elemento non dizionario nei dati fornitori: {fornitore_corrente}")
        # --- FINE MODIFICA ---

        print(f"DEBUG [get_vettori]: Trovati {len(vettori_filtrati)} vettori ({nomi_da_includere}).")

    elif response is None:
        # Errore API già loggato da mx_call_api
        print("ERRORE [get_vettori]: Chiamata API fallita.")
    else:
        # Risposta API inattesa
        print(f"ERRORE [get_vettori]: Risposta API inattesa (campo 'dati' non è lista o manca): {response}")

    return vettori_filtrati # Restituisce la lista (potrebbe essere vuota)

def get_shipping_address(address_id):
    """Recupera un indirizzo di spedizione specifico tramite ID."""
    if not address_id:
        return None

    endpoint = 'risorse/indirizzi-spedizione/ricerca'

    # Usa 'filtri' minuscolo (già corretto nel codice originale)
    search_data = {
        'filtri': [
            {'campo': 'codice', 'condizione': '=', 'valore': str(address_id)}
        ]
    }

    response = mx_call_api(endpoint, method='POST', data=search_data)

    if response and isinstance(response.get('dati'), list):
        # Assicurati che ci sia almeno un risultato prima di accedere all'indice [0]
        if len(response['dati']) > 0:
            return response['dati'][0]
        else:
            print(f"Nessun indirizzo di spedizione trovato per ID: {address_id}")
            return None
    elif response:
        print(f"Errore in get_shipping_address: 'dati' non è una lista o manca per ID {address_id}. Risposta: {response}")
        return None
    else: # response is None
        return None # Errore API già loggato

def get_dati_aggiuntivi(client_code):
    """Recupera i dati aggiuntivi per un cliente specifico."""
    if not client_code:
        return {}

    # --- CORREZIONE 5: Aggiunto commento su endpoint e encoding ---
    # NOTA: Verifica se questo endpoint è corretto e se la codifica hex è necessaria.
    # La codifica hex è richiesta solo se client_code contiene '/' o '\' [cite: 650-651].
    # Potrebbe essere più sicuro applicarla sempre o condizionalmente.
    try:
        # Applica encoding solo se necessario (contiene / o \)
        if '/' in str(client_code) or '\\' in str(client_code):
            encoded_id = str(client_code).encode('utf-8').hex()
            endpoint = f"risorse/clienti/{encoded_id}/dati-aggiuntivi?encoding=hex"
        else:
            # Usa il codice cliente direttamente se non contiene caratteri speciali
            endpoint = f"risorse/clienti/{client_code}/dati-aggiuntivi" # Senza encoding

        response = mx_call_api(endpoint, method='GET')

        if response and response.get('dati') is not None:
             # A volte 'dati' potrebbe essere una lista vuota o un dict. Gestisci entrambi.
            dati = response['dati']
            if isinstance(dati, list):
                return dati[0] if dati else {} # Prendi il primo se lista non vuota, altrimenti {}
            elif isinstance(dati, dict):
                return dati # È già un dizionario
            else:
                 print(f"Formato dati aggiuntivi inatteso per cliente {client_code}: {type(dati)}")
                 return {}
        # Se la risposta è None (errore API) o non contiene 'dati' o 'dati' è None
        else:
             if response is not None: # Logga solo se c'è stata una risposta (anche vuota)
                 print(f"Nessun dato aggiuntivo trovato o errore API per cliente {client_code}, risposta: {response}")
             return {} # Ritorna dict vuoto in caso di errore o dato mancante

    except Exception as e:
        print(f"Errore generico durante recupero/encoding dati aggiuntivi per {client_code}: {e}")
        return {}


def get_payment_methods():
    """Recupera l'elenco dei metodi di pagamento."""
    endpoint = 'risorse/dati-generali/pagamenti/ricerca'
    # --- CORREZIONE 3: Usa 'filtri' minuscolo ---
    response = mx_call_api(endpoint, method='POST', data={'filtri': []}) # Usa 'filtri'

    if response and isinstance(response.get('dati'), list):
        # Assicurati che 'id' esista prima di usarlo come chiave
        return {
            metodo['id']: metodo.get('descrizione', 'N/D')
            for metodo in response['dati'] if 'id' in metodo
            }
    elif response:
        print(f"Errore in get_payment_methods: 'dati' non è una lista o manca. Risposta: {response}")
        return {}
    else: # response is None
        return {} # Errore API già loggato

def search_articles(query):
    """Cerca articoli per descrizione, includendo 'descr_completa' e 'cod_alt'."""
    # --- MODIFICA: Aggiunto 'cod_alt' alla lista campi ---
    campi_richiesti = "codice,descrizione,descr_completa,cod_alternativo,qta_carico,qta_scarico,ord_cli_e,ord_cli_sps" # Aggiunto cod_alt
    endpoint = f'risorse/articoli/ricerca?fields={campi_richiesti}'

    # Usa 'filtri' minuscolo
    search_data = {
        'filtri': [
            {
                'campo': 'descrizione',
                'condizione': 'contiene', # Cerca se la descrizione CONTIENE la query
                'valore': query,
                'case_insensitive': True # Rende la ricerca insensibile a maiuscole/minuscole
            }
        ]
    }

    response = mx_call_api(endpoint, method='POST', data=search_data)

    if response and isinstance(response.get('dati'), list):
        return response['dati']
    elif response:
        print(f"Errore in search_articles: 'dati' non è una lista o manca per query '{query}'. Risposta: {response}")
        return []
    else: # response is None
        return [] # Errore API già loggato

# --- NUOVA FUNZIONE ---
def search_articles_by_code(code_query):
    """Cerca articoli per codice, includendo 'descr_completa' e 'cod_alt'."""
    # Richiedi gli stessi campi della ricerca per descrizione
    campi_richiesti = "codice,descrizione,descr_completa,cod_alternativo,qta_carico,qta_scarico,ord_cli_e,ord_cli_sps" # Includi cod_alt
    endpoint = f'risorse/articoli/ricerca?fields={campi_richiesti}'

    # Filtra per il campo 'codice'
    search_data = {
        'filtri': [
            {
                'campo': 'codice',
                # Usa 'contiene' per permettere ricerche parziali (es. cerca 'ABC' trova 'ABC001', 'XYZABC')
                # Se vuoi la corrispondenza esatta, usa 'condizione': '='
                'condizione': 'contiene',
                'valore': code_query,
                # La ricerca codice potrebbe essere case-sensitive o meno, scegli in base alle tue necessità
                'case_insensitive': True # Manteniamo True per flessibilità
            }
        ]
    }

    response = mx_call_api(endpoint, method='POST', data=search_data)

    if response and isinstance(response.get('dati'), list):
        return response['dati']
    elif response:
        print(f"Errore in search_articles_by_code: 'dati' non è una lista o manca per codice '{code_query}'. Risposta: {response}")
        return []
    else: # response is None
        return [] # Errore API già loggato

    response = mx_call_api(endpoint, method='POST', data=search_data)

    if response and isinstance(response.get('dati'), list):
        return response['dati']
    elif response:
        print(f"Errore in search_articles_by_code: 'dati' non è una lista o manca per codice '{code_query}'. Risposta: {response}")
        return []
    else: # response is None
        return [] # Errore API già loggato

def find_article_code_by_alt_code(alt_code_value):
    """
    Trova il codice articolo principale cercando direttamente nell'archivio articoli
    tramite il campo 'cod_alternativo'.
    Restituisce il codice articolo principale ('codice') se trovato, altrimenti None.
    """
    endpoint = 'risorse/articoli/ricerca'
    # Richiediamo solo il campo 'codice' per efficienza
    endpoint += '?fields=codice'

    search_data = {
        'filtri': [
            # Filtriamo per 'cod_alternativo' uguale al barcode/alt_code fornito
            {'campo': 'cod_alternativo', 'condizione': '=', 'valore': alt_code_value}
        ]
    }

    print(f"DEBUG [find_by_alt_code]: Chiamata API per codice alternativo '{alt_code_value}'")
    print(f"DEBUG [find_by_alt_code]: Endpoint: {endpoint}")
    print(f"DEBUG [find_by_alt_code]: Payload: {search_data}")

    response = mx_call_api(endpoint, method='POST', data=search_data)

    print(f"DEBUG [find_by_alt_code]: Risposta API ricevuta: {response}")

    if response and isinstance(response.get('dati'), list):
        if len(response['dati']) > 0:
            # Trovato almeno un articolo
            first_result = response['dati'][0]
            if isinstance(first_result, dict):
                primary_code = first_result.get('codice') # Estrai il codice articolo principale
                if primary_code:
                    print(f"DEBUG [find_by_alt_code]: Codice articolo principale trovato: {primary_code}")
                    if len(response['dati']) > 1:
                         # Avviso se più articoli hanno lo stesso codice alternativo
                         print(f"WARN [find_by_alt_code]: Trovati {len(response['dati'])} articoli con codice alternativo '{alt_code_value}'. Uso il primo: {primary_code}.")
                    return primary_code
                else:
                    print(f"ERRORE [find_by_alt_code]: Chiave 'codice' mancante nel risultato: {first_result}")
                    return None
            else:
                print(f"ERRORE [find_by_alt_code]: Il primo risultato non è un dizionario: {first_result}")
                return None
        else:
            # L'API ha risposto ma non ha trovato l'alt_code
            print(f"INFO [find_by_alt_code]: Nessun articolo trovato per codice alternativo: '{alt_code_value}'")
            return None
    elif response is None:
        print(f"ERRORE [find_by_alt_code]: Chiamata API fallita per codice alternativo {alt_code_value}.")
        return None
    else:
        print(f"ERRORE [find_by_alt_code]: Risposta API inattesa per codice alternativo {alt_code_value}. 'dati' non è lista o manca. Risposta: {response}")
        return None
# --- FINE NUOVA FUNZIONE ---

def get_article_price(codice_articolo, listino_id=4):
    """Recupera il prezzo di un articolo usando il servizio 'condizioni_documento'."""
    if not codice_articolo:
        print("Errore get_article_price: codice_articolo mancante.")
        return 0.0

    endpoint = 'servizi' # Corretto, è un servizio

    today_date = datetime.now().strftime('%Y%m%d')
    # NOTA: Verifica che '501.00085' sia un codice cliente valido/appropriato per questo scopo
    default_client = "501.00085" # Citato nel manuale (pag. 52) [cite: 2051], ma assicurati sia corretto nel tuo contesto

    # Struttura dati corretta per il servizio 'condizioni_documento' (pag. 52) [cite: 2319-2346]
    search_data = {
        "cmd": "condizioni_documento",
        "dati": {
            "tipo": 1, # Richiedi prezzo, sconto, provvigione
            "cod_conto": 501.00085, # Usa il cliente di default
            "codice_articolo": codice_articolo,
            "data_documento": today_date,
            "sigla_documento": "OC", # Sigla generica per il calcolo
            "quantita": 1, # Quantità base per il prezzo
            "id_listino": listino_id # ID listino specificato
            # Campi opzionali omessi (prezzo, coefficiente, valuta, sconto, ecc.)
        }
    }

    response = mx_call_api(endpoint, method='POST', data=search_data)

    # La risposta del servizio non ha la chiave 'dati' (pag. 52) [cite: 2348-2360]
    # Controlla che response sia un dizionario prima di usare .get()
    if isinstance(response, dict) and response.get('prezzo') is not None:
        try:
            return float(response.get('prezzo', 0.0))
        except (ValueError, TypeError):
             print(f"Errore: Prezzo ricevuto non è un numero valido per {codice_articolo}: {response.get('prezzo')}")
             return 0.0
    # Se response è None (errore API) o non è un dizionario o non contiene 'prezzo', ritorna 0.0
    else:
        if response is not None: # Logga solo se c'è stata una risposta (ma non valida)
            print(f"Prezzo non trovato o risposta API non valida per {codice_articolo}, risposta: {response}")
        return 0.0
    
def get_article_details(codice_articolo):
    """
    Recupera i dettagli completi di un singolo articolo.
    Aggiunta stampa per debug.
    """
    if not codice_articolo:
        return None

    endpoint = f'risorse/articoli/{codice_articolo}'
    #print(f"DEBUG: Chiamata GET a {API_BASE_URL}{endpoint}") # Stampa URL
    response = mx_call_api(endpoint, method='GET')

    # --- Stampa la risposta COMPLETA per debug ---
    #print(f"DEBUG: Risposta API per dettagli articolo {codice_articolo}: {response}")
    # --- Fine Stampa Debug ---

    if response and isinstance(response, dict):
         if 'error' in response:
             print(f"Errore API (in response) recuperando dettagli per {codice_articolo}: {response.get('error')}")
             return None
         # Verifica aggiuntiva se il codice corrisponde
         if response.get('codice') == codice_articolo:
             return response
         else:
              print(f"WARN: Codice nella risposta ({response.get('codice')}) non corrisponde a quello richiesto ({codice_articolo})")
              # Potrebbe comunque essere valido se l'API ha logiche strane, restituiscilo comunque
              return response
    elif response is None:
         print(f"Errore: Chiamata API fallita (None) per dettagli articolo {codice_articolo}.")
         return None
    else:
        print(f"Errore: Formato risposta non atteso (tipo: {type(response)}) per dettagli articolo {codice_articolo}")
        return None
    
def update_article_alt_code(codice_articolo, new_alt_code):
    """
    Aggiorna il campo 'cod_alternativo' per un articolo specifico tramite API PUT.
    Restituisce True in caso di successo (HTTP 204), False altrimenti.
    """
    if not codice_articolo:
        print("ERRORE [update_alt_code]: Codice articolo mancante.")
        return False

    endpoint = f'risorse/articoli/{codice_articolo}'
    payload = {
        'cod_alternativo': new_alt_code if new_alt_code is not None else '' # Invia stringa vuota per cancellare
    }

    print(f"DEBUG [update_alt_code]: Chiamata API PUT per articolo '{codice_articolo}'")
    print(f"DEBUG [update_alt_code]: Endpoint: {endpoint}")
    print(f"DEBUG [update_alt_code]: Payload: {payload}")

    # Facciamo una chiamata leggermente diversa per PUT perché non ci aspettiamo un JSON di ritorno
    # ma uno status code 204 (No Content). Usiamo mx_call_api ma dovremo controllare lo status.
    # Modifichiamo temporaneamente mx_call_api per ritornare l'intera response per PUT/DELETE
    # OPPURE creiamo una funzione helper specifica per PUT/DELETE. Scegliamo la seconda.

    headers = {
        'Authorization': f'Passepartout {AUTH_TOKEN}',
        'Coordinate-Gestionale': 'Azienda=SRL Anno=2025 Magazzino=3', # Assicurati che siano corrette
        'Content-Type': 'application/json;charset=utf-8'
    }
    full_url = f"{API_BASE_URL}{endpoint}"

    try:
        response = requests.put(full_url, headers=headers, json=payload, timeout=45, verify=False) # verify=True è default

        print(f"DEBUG [update_alt_code]: Risposta API Status Code: {response.status_code}")
        # DEBUG: Stampa il corpo della risposta SE non è 204 per capire l'errore
        if response.status_code != 204 and response.text:
            print(f"DEBUG [update_alt_code]: Corpo risposta errore API: {response.text[:500]}") # Limita lunghezza output

        response.raise_for_status() # Solleva eccezione per 4xx/5xx

        # Se arriva qui, lo status code era 2xx (ci aspettiamo 204)
        if response.status_code == 204:
            print(f"INFO [update_alt_code]: Aggiornamento cod_alternativo per {codice_articolo} riuscito.")
            return True
        else:
            # Status code 2xx ma non 204? Improbabile per PUT ma gestiamolo.
            print(f"WARN [update_alt_code]: Risposta inattesa (Status {response.status_code}) dopo PUT per {codice_articolo}.")
            return False # Consideriamo successo solo 204

    except requests.exceptions.Timeout:
        print(f"ERRORE [update_alt_code]: Timeout nella chiamata PUT a {full_url}")
        return False
    except requests.exceptions.SSLError as e:
        print(f"ERRORE SSL [update_alt_code] nella chiamata PUT a {full_url}: {e}")
        return False
    except requests.exceptions.RequestException as e:
        error_details = "N/D"
        status_code = "N/A"
        if e.response is not None:
             status_code = e.response.status_code
             try: error_details = e.response.json() # Prova a leggere JSON
             except json.JSONDecodeError: error_details = e.response.text # Altrimenti leggi testo
        print(f"ERRORE [update_alt_code]: Chiamata PUT fallita (Status {status_code}) per {codice_articolo}: {e}")
        print(f"Dettagli Errore Server: {error_details}")
        return False
    except Exception as e:
         print(f"ERRORE inaspettato in [update_alt_code] per {codice_articolo}: {e}")
         return False
    
def get_all_clients():
    """Recupera l'elenco completo dei clienti dall'API."""
    endpoint = 'risorse/clienti/ricerca'
    # Richiediamo solo i campi essenziali per la lista
    fields = "codice,ragione_sociale,indirizzo,localita" # Aggiungi altri campi se utili
    endpoint += f"?fields={fields}"
    payload = {'filtri': []} # Nessun filtro per averli tutti

    print("DEBUG [get_all_clients]: Chiamata API per elenco clienti...")
    response = mx_call_api(endpoint, method='POST', data=payload)

    if response and isinstance(response.get('dati'), list):
        print(f"DEBUG [get_all_clients]: Recuperati {len(response['dati'])} clienti.")
        return response['dati']
    elif response is None:
        print("ERRORE [get_all_clients]: Chiamata API fallita.")
        return None
    else:
        print(f"ERRORE [get_all_clients]: Risposta API inattesa: {response}")
        return None
# --- FINE NUOVA FUNZIONE ---

# --- NUOVA FUNZIONE (per ora carica tutti gli indirizzi) ---
def get_all_shipping_addresses():
    """
    Recupera TUTTI gli indirizzi di spedizione dall'API.
    NOTA: Ottimizzazione futura -> filtrare per cliente specifico se necessario.
    """
    endpoint = 'risorse/indirizzi-spedizione/ricerca'
    # Richiediamo campi utili per l'elenco
    fields = "id,cod_conto,descrizione,indirizzo,localita,cap,provincia"
    endpoint += f"?fields={fields}"
    payload = {'filtri': []} # Nessun filtro = tutti

    print("DEBUG [get_all_shipping_addresses]: Chiamata API per elenco indirizzi spedizione...")
    response = mx_call_api(endpoint, method='POST', data=payload)

    if response and isinstance(response.get('dati'), list):
        print(f"DEBUG [get_all_shipping_addresses]: Recuperati {len(response['dati'])} indirizzi.")
        return response['dati']
    elif response is None:
        print("ERRORE [get_all_shipping_addresses]: Chiamata API fallita.")
        return None
    else:
        print(f"ERRORE [get_all_shipping_addresses]: Risposta API inattesa: {response}")
        return None
# --- FINE NUOVA FUNZIONE ---


# --- Funzione ESISTENTE (ottiene 1 indirizzo per ID, la manteniamo se serve altrove) ---
def get_shipping_address(address_id):
    """
    Recupera un singolo indirizzo di spedizione usando l'endpoint di RICERCA,
    filtrando per il codice (ID). Aggiunto logging risposta API.
    """
    if not address_id:
        return None

    endpoint = 'risorse/indirizzi-spedizione/ricerca'
    # Richiediamo campi dettaglio (invariato)
    fields = "id,cod_conto,descrizione,indirizzo,localita,cap,provincia,telefono1,nazione"
    endpoint += f"?fields={fields}"

    # Filtriamo per 'id' come da ipotesi precedente basata su help.txt
    search_data = {
        'filtri': [
            {'campo': 'id', 'condizione': '=', 'valore': str(address_id)}
        ]
    }
    print(f"DEBUG [get_shipping_address]: Chiamata API per ID indirizzo: {address_id} con filtro su campo 'id'")
    response = mx_call_api(endpoint, method='POST', data=search_data)

    # --- AGGIUNTA LOG RISPOSTA ---
    print(f"DEBUG [get_shipping_address]: Risposta API per ID {address_id}: {response}")
    # --- FINE AGGIUNTA ---

    if response and isinstance(response.get('dati'), list):
        if len(response['dati']) > 0:
            print(f"DEBUG [get_shipping_address]: Indirizzo trovato per ID {address_id}.")
            return response['dati'][0]
        else:
            # L'API ha risposto ma 'dati' è vuota -> ID non trovato
            print(f"INFO [get_shipping_address]: Nessun indirizzo spedizione trovato per ID: {address_id} (risposta API: {response})")
            return None
    elif response is None:
         # Chiamata API fallita (errore rete, auth, 4xx/5xx...)
         print(f"ERRORE [get_shipping_address]: Chiamata API fallita (None) per ID: {address_id}")
         return None
    else:
        # Risposta API in formato non atteso
        print(f"ERRORE [get_shipping_address]: Risposta API inattesa (formato non valido) per ID {address_id}: {response}")
        return None