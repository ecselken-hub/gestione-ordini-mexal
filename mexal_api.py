import requests
import os
from dotenv import load_dotenv
import time

# Carrega as variáveis do arquivo .env
load_dotenv()

API_BASE_URL = 'https://93.148.248.104:9004/webapi/'
AUTH_TOKEN = os.getenv('MX_AUTH')

def mx_call_api(endpoint, method='GET', data=None):
    """
    Função genérica para chamar a API Mexal.
    """
    if not AUTH_TOKEN:
        print("Erro: O token de autenticação MX_AUTH não foi configurado.")
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
        print(f"Erro ao chamar a API em {full_url}: {e}")
        if e.response is not None:
            print(f"!!! DETALHE DO ERRO DO SERVIDOR: {e.response.text} !!!")
        return None

def get_vettori():
    """
    Recupera a lista de todos os vetores (motoristas) que são gerenciados como fornecedores
    e filtra para incluir apenas 'BOXER' e 'EXPERT'.
    """
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
    """
    Recupera um único endereço de entrega usando seu ID codificado em HEX.
    """
    if not address_id:
        return None
    encoded_id = str(address_id).encode('utf-8').hex()
    endpoint = f"risorse/indirizzi-spedizione/{encoded_id}?encoding=hex"
    response = mx_call_api(endpoint, method='GET')
    if response and response.get('dati'):
        return response['dati']
    return None

def get_dati_aggiuntivi(client_code):
    """
    Recupera os dados adicionais de um cliente (incluindo horários de entrega).
    """
    if not client_code:
        return {} # Retorna um dicionário vazio para segurança
    encoded_id = str(client_code).encode('utf-8').hex()
    endpoint = f"risorse/clienti/{encoded_id}/dati-aggiuntivi?encoding=hex"
    response = mx_call_api(endpoint, method='GET')
    if response and response.get('dati'):
        return response['dati']
    return {}

def get_payment_methods():
    """
    Recupera a lista de todos os métodos de pagamento.
    """
    endpoint = 'risorse/dati-generali/pagamenti/ricerca'
    response = mx_call_api(endpoint, method='POST', data={'Filtri': []})
    if response and response.get('dati'):
        return {metodo['id']: metodo.get('descrizione', 'N/D') for metodo in response['dati']}
    return {}