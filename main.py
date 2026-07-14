import urllib.request
import http.cookiejar
import ssl
import json
import logging
import sqlite3
import os
import asyncio
from datetime import datetime
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Body
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("energy-outages-app")

DB_PATH = os.environ.get("DB_PATH", "outages.db")
DISABLE_API_FETCH = os.environ.get("DISABLE_API_FETCH", "false").lower() == "true"

def init_db():
    """Initialize the SQLite database with required tables."""
    logger.info("Initializing SQLite database...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        total_occurrences INTEGER NOT NULL,
        total_affected INTEGER NOT NULL,
        total_teams INTEGER NOT NULL
    );
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS city_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id INTEGER NOT NULL,
        city_id TEXT NOT NULL,
        nome TEXT NOT NULL,
        concessionaria TEXT NOT NULL,
        estado TEXT NOT NULL,
        ocorrencias INTEGER NOT NULL,
        unidades_afetadas INTEGER NOT NULL,
        equipes INTEGER NOT NULL,
        FOREIGN KEY(run_id) REFERENCES runs(id) ON DELETE CASCADE
    );
    """)
    conn.commit()
    conn.close()
    logger.info("Database initialized successfully.")

# Cached data store
cached_data = {
    "timestamp": None,
    "items": []
}

def save_run_to_db(items: List[dict]):
    """Save the current aggregated run and city records to the database."""
    if not items:
        logger.warning("No items to save to database.")
        return
        
    total_occurrences = sum(item["ocorrencias"] for item in items)
    total_affected = sum(item["unidades_afetadas"] for item in items)
    total_teams = sum(item["equipes"] for item in items)
    now_str = datetime.now().isoformat()
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Check last run to prevent double-saving within 2 minutes (e.g. manual spamming)
        cursor.execute("SELECT timestamp FROM runs ORDER BY id DESC LIMIT 1")
        last_run = cursor.fetchone()
        if last_run:
            last_time = datetime.fromisoformat(last_run[0])
            if (datetime.now() - last_time).total_seconds() < 120:
                logger.info("Skipping DB save: last run was less than 2 minutes ago.")
                conn.close()
                return
                
        cursor.execute(
            "INSERT INTO runs (timestamp, total_occurrences, total_affected, total_teams) VALUES (?, ?, ?, ?)",
            (now_str, total_occurrences, total_affected, total_teams)
        )
        run_id = cursor.lastrowid
        
        for item in items:
            # Only save records with outages or active teams
            if item["ocorrencias"] > 0 or item["equipes"] > 0:
                cursor.execute(
                    """INSERT INTO city_records 
                    (run_id, city_id, nome, concessionaria, estado, ocorrencias, unidades_afetadas, equipes) 
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        run_id,
                        item["id"],
                        item["nome"],
                        item["concessionaria"],
                        item["estado"],
                        item["ocorrencias"],
                        item["unidades_afetadas"],
                        item["equipes"]
                    )
                )
                
        conn.commit()
        conn.close()
        logger.info(f"Saved run {run_id} to database. Total outages: {total_occurrences}, affected: {total_affected}, teams: {total_teams}")
    except Exception as e:
        logger.error(f"Failed to save run to database: {e}")

async def hourly_background_worker():
    """Background worker that runs every hour to fetch and persist data."""
    # Delay first execution by 5 seconds to let server start up smoothly
    await asyncio.sleep(5)
    while True:
        try:
            logger.info("Hourly background worker: starting data synchronization...")
            ceee_items = fetch_ceee_data()
            cpfl_items = fetch_cpfl_data()
            
            is_ceee_fresh = ceee_items is not None
            is_cpfl_fresh = cpfl_items is not None
            
            if ceee_items is None:
                logger.warning("CEEE fetch failed; falling back to DB.")
                ceee_items = get_latest_provider_records_from_db("CEEE")
            if cpfl_items is None:
                logger.warning("CPFL fetch failed; falling back to DB.")
                cpfl_items = get_latest_provider_records_from_db("CPFL")
                
            combined = ceee_items + cpfl_items
            
            # Save to database only if we got fresh data from at least one API
            if is_ceee_fresh or is_cpfl_fresh:
                save_run_to_db(combined)
            
            # Update Cache
            combined.sort(key=lambda x: (-x["ocorrencias"], x["nome"]))
            cached_data["timestamp"] = datetime.now()
            cached_data["items"] = combined
            logger.info("Hourly background worker: data synchronization completed successfully.")
        except Exception as e:
            logger.error(f"Error in hourly background worker: {e}")
            
        # Wait for 1 hour (3600 seconds)
        await asyncio.sleep(3600)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown lifespan events."""
    # Startup actions
    init_db()
    
    # Start background scheduler only if API fetch is enabled
    bg_task = None
    if not DISABLE_API_FETCH:
        bg_task = asyncio.create_task(hourly_background_worker())
    else:
        logger.info("Background worker disabled (DISABLE_API_FETCH=true). Server is in ingestion-only mode.")
    
    yield
    
    # Shutdown actions
    if bg_task:
        logger.info("Shutting down background task...")
        bg_task.cancel()
        try:
            await bg_task
        except asyncio.CancelledError:
            logger.info("Background task cancelled.")

app = FastAPI(title="Painel de Interrupções de Energia", lifespan=lifespan)

# SSL Context to bypass validation if necessary
ssl_ctx = ssl.create_default_context()
ssl_ctx.check_hostname = False
ssl_ctx.verify_mode = ssl.CERT_NONE

# Cookie jar for CEEE to handle Incapsula cookies
ceee_cookie_jar = http.cookiejar.CookieJar()
ceee_opener = urllib.request.build_opener(
    urllib.request.HTTPCookieProcessor(ceee_cookie_jar),
    urllib.request.HTTPSHandler(context=ssl_ctx)
)

def map_ibge_to_state(ibge_code: int) -> str:
    """Map IBGE code prefix to Brazilian State abbreviation."""
    if not ibge_code:
        return "Desconhecido"
    prefix = str(ibge_code)[:2]
    states = {
        "11": "RO", "12": "AC", "13": "AM", "14": "RR", "15": "PA", "16": "AP", "17": "TO",
        "21": "MA", "22": "PI", "23": "CE", "24": "RN", "25": "PB", "26": "PE", "27": "AL",
        "28": "SE", "29": "BA", "31": "MG", "32": "ES", "33": "RJ", "35": "SP", "41": "PR",
        "42": "SC", "43": "RS", "50": "MS", "51": "MT", "52": "GO", "53": "DF"
    }
    return states.get(prefix, "Desconhecido")

def fetch_ceee_data() -> List[dict]:
    """Fetch and aggregate CEEE Equatorial data."""
    url = "https://ceee.equatorialenergia.com.br/api-etr/resumo?nivel=bairro&estado=RS"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7',
        'Referer': 'https://ceee.equatorialenergia.com.br/',
    }
    
    logger.info("Fetching CEEE Equatorial data...")
    try:
        req = urllib.request.Request(url, headers=headers)
        with ceee_opener.open(req, timeout=15) as response:
            content = response.read()
            data = json.loads(content)
            
            grupos = data.get('grupos', [])
            logger.info(f"CEEE returned {len(grupos)} neighborhood-level records.")
            
            # Aggregate by municipality
            mun_dict = {}
            for item in grupos:
                mun_name = item.get('municipio_nome', '').strip().title()
                if not mun_name:
                    continue
                    
                bairro_name = item.get('bairro', '').strip().title()
                estado = item.get('estado', 'RS')
                ocorrencias = item.get('ocorrencias', 0)
                unidades_afetadas = item.get('unidades_afetadas', 0)
                equipes = item.get('equipes_em_campo', 0)
                
                statuses = {}
                por_status = item.get('por_status', {})
                if isinstance(por_status, dict):
                    for st_name, st_info in por_status.items():
                        if isinstance(st_info, dict):
                            statuses[st_name] = st_info.get('ocorrencias', 0)
                
                bairro_data = {
                    "nome": bairro_name,
                    "ocorrencias": ocorrencias,
                    "unidades_afetadas": unidades_afetadas,
                    "equipes": equipes,
                    "status": statuses
                }
                
                if mun_name not in mun_dict:
                    mun_dict[mun_name] = {
                        "id": f"ceee-{item.get('municipio_ibge', mun_name.lower().replace(' ', '_'))}",
                        "nome": mun_name,
                        "concessionaria": "CEEE Equatorial",
                        "estado": estado,
                        "ocorrencias": 0,
                        "unidades_afetadas": 0,
                        "equipes": 0,
                        "bairros": []
                    }
                
                mun_dict[mun_name]["ocorrencias"] += ocorrencias
                mun_dict[mun_name]["unidades_afetadas"] += unidades_afetadas
                mun_dict[mun_name]["equipes"] += equipes
                mun_dict[mun_name]["bairros"].append(bairro_data)
                
            result = list(mun_dict.values())
            logger.info(f"CEEE aggregated to {len(result)} municipalities.")
            return result
    except Exception as e:
        logger.error(f"Failed to fetch/parse CEEE: {e}")
        return None

def fetch_cpfl_data() -> List[dict]:
    """Fetch and aggregate CPFL / RGE data."""
    url = "https://www.cpfl.com.br/monitoramento-interrupcoes-fornecimento/dados"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }
    
    logger.info("Fetching CPFL data...")
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, context=ssl_ctx, timeout=15) as response:
            content = response.read()
            data = json.loads(content)
            
            dados = data.get('dados', [])
            if not dados:
                logger.warning("CPFL response does not contain 'dados'.")
                return []
                
            cities = dados[0].get('cidades', [])
            logger.info(f"CPFL returned {len(cities)} total cities.")
            
            result = []
            for city in cities:
                mun_name = city.get('nome', '').strip().title()
                if not mun_name:
                    continue
                    
                distribuidora = city.get('idDistribuidora', '').upper()
                cod_ibge = city.get('codIbge')
                estado = map_ibge_to_state(cod_ibge)
                
                teams = city.get('quantidadeEquipesEmAtendimento', 0)
                ocorrencias = 0
                unidades_afetadas = 0
                bairros_list = []
                
                for b in city.get('bairros', []):
                    b_name = b.get('nome', '').strip().title()
                    b_events = b.get('eventos', [])
                    
                    b_ocorrencias = len(b_events)
                    b_afetadas = sum(e.get('quantidadeClientes', 0) for e in b_events)
                    
                    ocorrencias += b_ocorrencias
                    unidades_afetadas += b_afetadas
                    
                    eventos_list = []
                    for e in b_events:
                        eventos_list.append({
                            "numero": e.get('numeroEvento'),
                            "status": e.get('status'),
                            "tipo": e.get('tipo'),
                            "duracao": e.get('duracaoOcorrencia'),
                            "clientes": e.get('quantidadeClientes'),
                            "hora": e.get('dataHoraEvento')
                        })
                        
                    bairros_list.append({
                        "nome": b_name,
                        "ocorrencias": b_ocorrencias,
                        "unidades_afetadas": b_afetadas,
                        "eventos": eventos_list
                    })
                
                if (ocorrencias > 0 or teams > 0) and estado == "RS":
                    result.append({
                        "id": f"cpfl-{cod_ibge or mun_name.lower().replace(' ', '_')}",
                        "nome": mun_name,
                        "concessionaria": "CPFL (RGE)" if distribuidora == "RGE" else f"CPFL ({distribuidora})",
                        "estado": estado,
                        "ocorrencias": ocorrencias,
                        "unidades_afetadas": unidades_afetadas,
                        "equipes": teams,
                        "bairros": bairros_list
                    })
            
            logger.info(f"CPFL filtered to {len(result)} cities with active outages/teams.")
            return result
    except Exception as e:
        logger.error(f"Failed to fetch/parse CPFL: {e}")
        return None

# Data models
class WhatsappRequest(BaseModel):
    selected_ids: List[str]
    custom_header: Optional[str] = None
    custom_footer: Optional[str] = None
    include_bairros: bool = True
    include_events_details: bool = False
    include_occurrences: bool = True  # Added: toggle occurrences output

def get_latest_provider_records_from_db(provider_prefix: str) -> List[dict]:
    """Retrieve the latest records for a specific provider from the database."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Find the latest run ID that has records for this provider prefix
        cursor.execute(
            "SELECT DISTINCT run_id FROM city_records WHERE concessionaria LIKE ? ORDER BY run_id DESC LIMIT 1",
            (f"{provider_prefix}%",)
        )
        row = cursor.fetchone()
        if not row:
            conn.close()
            return []
        run_id = row[0]
        
        cursor.execute(
            """SELECT city_id, nome, concessionaria, estado, ocorrencias, unidades_afetadas, equipes 
            FROM city_records WHERE run_id = ? AND concessionaria LIKE ?""",
            (run_id, f"{provider_prefix}%")
        )
        rows = cursor.fetchall()
        conn.close()
        
        fallback_items = []
        for r in rows:
            if r[3] == "RS":
                fallback_items.append({
                    "id": r[0],
                    "nome": r[1],
                    "concessionaria": r[2],
                    "estado": r[3],
                    "ocorrencias": r[4],
                    "unidades_afetadas": r[5],
                    "equipes": r[6],
                    "bairros": []  # Historical detailed neighborhoods are not stored in database
                })
        return fallback_items
    except Exception as e:
        logger.error(f"Failed to fetch fallback data for {provider_prefix} from DB: {e}")
        return []

def get_latest_run_from_db() -> List[dict]:
    """Retrieve the latest records from the database if APIs are down/blocked."""
    return get_latest_provider_records_from_db("CEEE") + get_latest_provider_records_from_db("CPFL")

@app.get("/api/data")
def get_data(refresh: bool = False):
    """Retrieve combined energy outage data from CEEE and CPFL."""
    now = datetime.now()
    
    # Cache for 2 minutes
    if not refresh and cached_data["timestamp"] and (now - cached_data["timestamp"]).total_seconds() < 120:
        return {
            "status": "cached",
            "timestamp": cached_data["timestamp"].isoformat(),
            "data": cached_data["items"]
        }
        
    if DISABLE_API_FETCH:
        # Ingestion-only mode: serve cached data or fallback to DB if cache is empty
        if not cached_data["items"]:
            cached_data["items"] = get_latest_run_from_db()
            # Try to get the latest run timestamp from the DB
            try:
                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()
                cursor.execute("SELECT timestamp FROM runs ORDER BY id DESC LIMIT 1")
                row = cursor.fetchone()
                if row:
                    cached_data["timestamp"] = datetime.fromisoformat(row[0])
                else:
                    cached_data["timestamp"] = now
                conn.close()
            except Exception:
                cached_data["timestamp"] = now
        
        return {
            "status": "fresh",
            "timestamp": cached_data["timestamp"].isoformat() if cached_data["timestamp"] else now.isoformat(),
            "data": cached_data["items"]
        }
        
    ceee_items = fetch_ceee_data()
    cpfl_items = fetch_cpfl_data()
    
    is_ceee_fresh = ceee_items is not None
    is_cpfl_fresh = cpfl_items is not None
    
    if ceee_items is None:
        logger.warning("CEEE fetch failed during API call; falling back to DB.")
        ceee_items = get_latest_provider_records_from_db("CEEE")
    if cpfl_items is None:
        logger.warning("CPFL fetch failed during API call; falling back to DB.")
        cpfl_items = get_latest_provider_records_from_db("CPFL")
        
    combined = ceee_items + cpfl_items
    
    if is_ceee_fresh or is_cpfl_fresh:
        # Save to SQLite database only if we got fresh data from at least one API
        save_run_to_db(combined)
        
    combined.sort(key=lambda x: (-x["ocorrencias"], x["nome"]))
    
    cached_data["timestamp"] = now
    cached_data["items"] = combined
    
    status_str = "fresh" if (is_ceee_fresh and is_cpfl_fresh) else "partial_fallback"
    if not is_ceee_fresh and not is_cpfl_fresh:
        status_str = "fallback"
        
    return {
        "status": status_str,
        "timestamp": now.isoformat(),
        "data": combined
    }

@app.post("/api/generate_whatsapp")
def generate_whatsapp(req: WhatsappRequest):
    """Generate a WhatsApp-formatted report for the selected municipalities."""
    if not cached_data["items"]:
        get_data()
        
    items_by_id = {item["id"]: item for item in cached_data["items"]}
    selected_items = [items_by_id[sid] for sid in req.selected_ids if sid in items_by_id]
    
    if not selected_items:
        return {"text": "Nenhum município selecionado ou dados indisponíveis."}
        
    now_str = datetime.now().strftime("%d/%m/%Y às %H:%M")
    
    text_lines = []
    if req.custom_header:
        text_lines.append(req.custom_header)
    else:
        text_lines.append("🚨 *RELATÓRIO DE INTERRUPÇÃO DE ENERGIA* 🚨")
        text_lines.append(f"📅 _Atualizado em: {now_str}_\n")
        
    total_ocorrencias = 0
    total_afetadas = 0
    total_equipes = 0
    
    for item in selected_items:
        nome = item["nome"]
        concess = item["concessionaria"]
        estado = item["estado"]
        ocorrencias = item["ocorrencias"]
        unidades = item["unidades_afetadas"]
        equipes = item["equipes"]
        
        total_ocorrencias += ocorrencias
        total_afetadas += unidades
        total_equipes += equipes
        
        text_lines.append(f"📍 *{nome} - {estado}* ({concess})")
        if req.include_occurrences:
            text_lines.append(f"  • Ocorrências: {ocorrencias}")
        text_lines.append(f"  • Afetados: {unidades:,} u.c.".replace(",", "."))
        text_lines.append(f"  • Equipes em Campo: {equipes}")
        
        if req.include_bairros and item.get("bairros"):
            bairros_text = []
            for b in item["bairros"]:
                b_name = b["nome"]
                
                details_parts = []
                if "CEEE" in concess:
                    st_map = b.get("status", {})
                    st_str = ", ".join(f"{k} ({v})" for k, v in st_map.items() if v > 0)
                    if st_str:
                        details_parts.append(st_str)
                else: # CPFL
                    events = b.get("eventos", [])
                    st_list = []
                    for e in events:
                        ev_desc = f"{e.get('status', '')}"
                        if req.include_events_details:
                            ev_desc += f" [{e.get('tipo', '')}, OS: {e.get('numero', '')}, Clientes: {e.get('clientes', 0)}]"
                        st_list.append(ev_desc)
                    if st_list:
                        details_parts.append(", ".join(set(st_list)))
                
                details_suffix = f" ({', '.join(details_parts)})" if details_parts else ""
                bairros_text.append(f"{b_name}{details_suffix}")
                
            text_lines.append(f"  • Bairros afetados: {', '.join(bairros_text)}")
        text_lines.append("")
        
    text_lines.append("📊 *Consolidado Selecionado:*")
    text_lines.append(f"  • Municípios: {len(selected_items)}")
    if req.include_occurrences:
        text_lines.append(f"  • Total Ocorrências: {total_ocorrencias}")
    text_lines.append(f"  • Total Clientes Sem Luz: {total_afetadas:,} u.c.".replace(",", "."))
    text_lines.append(f"  • Total Equipes Ativas: {total_equipes}")
    
    if req.custom_footer:
        text_lines.append(f"\n{req.custom_footer}")
        
    return {"text": "\n".join(text_lines)}

class IngestRequest(BaseModel):
    api_key: str
    items: List[dict]

@app.post("/api/ingest")
def ingest_data(req: IngestRequest):
    """Ingest fresh data from a local script to bypass WAF IP block."""
    api_key_env = os.environ.get("API_KEY")
    if not api_key_env or req.api_key != api_key_env:
        raise HTTPException(status_code=401, detail="Chave de API inválida ou não configurada.")
        
    combined = req.items
    
    # Save to SQLite database
    save_run_to_db(combined)
    
    # Update Cache
    combined.sort(key=lambda x: (-x["ocorrencias"], x["nome"]))
    cached_data["timestamp"] = datetime.now()
    cached_data["items"] = combined
    
    logger.info(f"Ingested {len(combined)} records successfully via API.")
    return {"status": "success", "count": len(combined)}

@app.get("/")
def read_root():
    """Serve the index.html page."""
    return FileResponse("static/index.html")

# Mount static folder
app.mount("/static", StaticFiles(directory="static"), name="static")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8555))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
