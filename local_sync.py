#!/usr/bin/env python3
import os
import sys
import json
import urllib.request
from datetime import datetime

# Define variables or load them from environment
API_KEY = os.environ.get("API_KEY")
SERVER_URL = os.environ.get("SERVER_URL") # e.g. "https://sua-app.up.railway.app" or "http://localhost:8555"

# Add current directory to path to import main
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from main import fetch_ceee_data, fetch_cpfl_data
except ImportError as e:
    print(f"[-] Erro ao importar main.py: {e}")
    sys.exit(1)

def run_sync():
    print(f"[{datetime.now().isoformat()}] Iniciando busca de dados local...")
    
    if not API_KEY:
        print("[-] Erro: A variável de ambiente API_KEY não está configurada.")
        print("Defina-a no seu terminal usando: export API_KEY='sua-chave-secreta'")
        return
        
    if not SERVER_URL:
        print("[-] Erro: A variável de ambiente SERVER_URL não está configurada.")
        print("Defina-a no seu terminal usando: export SERVER_URL='https://seu-app.up.railway.app'")
        return

    # Fetch fresh data using local residential IP
    print("[*] Buscando dados da CEEE Equatorial...")
    ceee_items = fetch_ceee_data()
    
    print("[*] Buscando dados da CPFL/RGE...")
    cpfl_items = fetch_cpfl_data()
    
    if ceee_items is None and cpfl_items is None:
        print("[-] Erro: Ambas as APIs falharam na coleta local. Abortando ingestão.")
        return
        
    # Reconstruct combined list using whatever succeeded
    combined = []
    if ceee_items:
        combined += ceee_items
        print(f"[+] Coletados {len(ceee_items)} registros frescos da CEEE.")
    else:
        print("[-] CEEE falhou localmente. Pulando parte da CEEE.")
        
    if cpfl_items:
        combined += cpfl_items
        print(f"[+] Coletados {len(cpfl_items)} registros frescos da CPFL.")
    else:
        print("[-] CPFL falhou localmente. Pulando parte da CPFL.")
        
    if not combined:
        print("[-] Nenhum registro coletado com sucesso. Abortando.")
        return

    # Post data to production server
    url = f"{SERVER_URL.rstrip('/')}/api/ingest"
    payload = {
        "api_key": API_KEY,
        "items": combined
    }
    
    print(f"[*] Enviando {len(combined)} registros para o servidor em {url}...")
    
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode('utf-8'),
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=30) as response:
            res_body = response.read().decode('utf-8')
            res_data = json.loads(res_body)
            print(f"[+] Sincronização concluída com sucesso! Servidor reportou: {res_data}")
    except Exception as e:
        print(f"[-] Falha ao enviar dados para o servidor: {e}")

if __name__ == "__main__":
    run_sync()
