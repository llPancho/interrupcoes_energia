import streamlit as st
import pandas as pd
import sqlite3
import os
import sys
import urllib.parse
from datetime import datetime
from typing import List, Optional

# Set page config
st.set_page_config(
    page_title="Painel de Interrupções de Energia",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for rich aesthetics and modern dark mode styling
st.markdown("""
<style>
    /* Metric styling */
    .stMetric {
        background-color: rgba(28, 33, 40, 0.5);
        border: 1px solid rgba(240, 246, 252, 0.1);
        border-radius: 8px;
        padding: 12px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    }
    
    /* Concessionaire badge custom style */
    .badge {
        padding: 2px 8px;
        border-radius: 12px;
        font-size: 0.75rem;
        font-weight: bold;
        color: white;
        display: inline-block;
        margin-left: 5px;
    }
    .badge-ceee {
        background-color: #3b82f6;
    }
    .badge-cpfl {
        background-color: #10b981;
    }
    .badge-state {
        background-color: #6b7280;
        border-radius: 4px;
        padding: 2px 6px;
    }
</style>
""", unsafe_allow_html=True)

# Add current directory to python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import the core logic from main.py
try:
    from main import (
        fetch_ceee_data,
        fetch_cpfl_data,
        save_run_to_db,
        init_db,
        DB_PATH,
        get_latest_provider_records_from_db,
        get_latest_run_from_db
    )
except ImportError as e:
    st.error(f"Erro ao importar funções do main.py: {e}")
    st.stop()

# Helper: Load and aggregate data with session caching
def load_data(refresh: bool = False):
    init_db()
    now = datetime.now()
    
    if "municipalities" not in st.session_state or refresh:
        ceee_items = None
        cpfl_items = None
        
        # Streamlit doesn't require async, fetch synchronously
        try:
            ceee_items = fetch_ceee_data()
        except Exception as e:
            st.sidebar.error(f"Erro CEEE API: {e}")
            
        try:
            cpfl_items = fetch_cpfl_data()
        except Exception as e:
            st.sidebar.error(f"Erro CPFL API: {e}")
            
        is_ceee_fresh = ceee_items is not None
        is_cpfl_fresh = cpfl_items is not None
        
        # Fallback to DB for whichever failed
        if ceee_items is None:
            ceee_items = get_latest_provider_records_from_db("CEEE")
        if cpfl_items is None:
            cpfl_items = get_latest_provider_records_from_db("CPFL")
            
        combined = ceee_items + cpfl_items
        
        # Save run if we have fresh data
        if is_ceee_fresh or is_cpfl_fresh:
            save_run_to_db(combined)
            
        combined.sort(key=lambda x: (-x["ocorrencias"], x["nome"]))
        
        st.session_state.municipalities = combined
        st.session_state.last_update = now
        
        if not is_ceee_fresh and not is_cpfl_fresh:
            st.session_state.sync_status = "fallback"
        elif not is_ceee_fresh or not is_cpfl_fresh:
            st.session_state.sync_status = "partial"
        else:
            st.session_state.sync_status = "fresh"
            
    return st.session_state.municipalities, st.session_state.last_update, st.session_state.sync_status

# Helper: Database queries for statistics
def get_historical_evolution(limit: int = 48) -> pd.DataFrame:
    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql_query(
            "SELECT timestamp, total_occurrences, total_affected, total_teams FROM runs ORDER BY timestamp DESC LIMIT ?",
            conn,
            params=(limit,)
        )
        if not df.empty:
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            # Reverse for chronological display
            df = df.iloc[::-1].reset_index(drop=True)
        return df
    except Exception as e:
        st.error(f"Erro ao carregar evolução histórica: {e}")
        return pd.DataFrame()
    finally:
        conn.close()

def get_stats_summary():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT COUNT(*) FROM runs")
        total_runs = cursor.fetchone()[0]
        
        cursor.execute("SELECT MAX(total_occurrences) FROM runs")
        max_occurrences = cursor.fetchone()[0] or 0
        
        cursor.execute("SELECT MAX(total_affected) FROM runs")
        max_affected = cursor.fetchone()[0] or 0
        
        return total_runs, max_occurrences, max_affected
    except Exception:
        return 0, 0, 0
    finally:
        conn.close()

def get_concessionaire_impact_data() -> pd.DataFrame:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id FROM runs ORDER BY id DESC LIMIT 1")
        row = cursor.fetchone()
        if not row:
            return pd.DataFrame()
        run_id = row[0]
        df = pd.read_sql_query(
            """SELECT concessionaria, SUM(ocorrencias) as ocorrencias, SUM(unidades_afetadas) as unidades_afetadas, SUM(equipes) as equipes
               FROM city_records WHERE run_id = ? GROUP BY concessionaria""",
            conn,
            params=(run_id,)
        )
        return df
    except Exception:
        return pd.DataFrame()
    finally:
        conn.close()

def get_top_cities_active() -> pd.DataFrame:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id FROM runs ORDER BY id DESC LIMIT 1")
        row = cursor.fetchone()
        if not row:
            return pd.DataFrame()
        run_id = row[0]
        df = pd.read_sql_query(
            """SELECT nome, concessionaria, ocorrencias, unidades_afetadas, equipes
               FROM city_records WHERE run_id = ? ORDER BY ocorrencias DESC, unidades_afetadas DESC LIMIT 5""",
            conn,
            params=(run_id,)
        )
        return df
    except Exception:
        return pd.DataFrame()
    finally:
        conn.close()

# Helper: WhatsApp text formatter
def generate_whatsapp_text(
    selected_items: List[dict],
    custom_header: Optional[str] = None,
    custom_footer: Optional[str] = None,
    include_bairros: bool = True,
    include_events_details: bool = False,
    include_occurrences: bool = True
) -> str:
    if not selected_items:
        return "Nenhum município selecionado ou dados indisponíveis."
        
    now_str = datetime.now().strftime("%d/%m/%Y às %H:%M")
    
    text_lines = []
    if custom_header:
        text_lines.append(custom_header)
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
        if include_occurrences:
            text_lines.append(f"  • Ocorrências: {ocorrencias}")
        text_lines.append(f"  • Afetados: {unidades:,} u.c.".replace(",", "."))
        text_lines.append(f"  • Equipes em Campo: {equipes}")
        
        if include_bairros and item.get("bairros"):
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
                        if include_events_details:
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
    if include_occurrences:
        text_lines.append(f"  • Total Ocorrências: {total_ocorrencias}")
    text_lines.append(f"  • Total Clientes Sem Luz: {total_afetadas:,} u.c.".replace(",", "."))
    text_lines.append(f"  • Total Equipes Ativas: {total_equipes}")
    
    if custom_footer:
        text_lines.append(f"\n{custom_footer}")
        
    return "\n".join(text_lines)

# --- APPLICATION STATE ---
if "selected_ids" not in st.session_state:
    st.session_state.selected_ids = set()
if "active_detail_id" not in st.session_state:
    st.session_state.active_detail_id = None

# --- INITIAL DATA LOAD ---
municipalities, last_update, sync_status = load_data()

# --- SIDEBAR FILTERS ---
st.sidebar.markdown("## ⚡ Filtros & Configurações")

search_query = st.sidebar.text_input("🔍 Buscar Município", placeholder="Digite para filtrar...")

st.sidebar.markdown("### Concessionárias")
show_ceee = st.sidebar.checkbox("CEEE Equatorial", value=True)
show_cpfl = st.sidebar.checkbox("CPFL (RGE)", value=True)

st.sidebar.markdown("### Estados")
selected_state = st.sidebar.selectbox("Filtrar por Estado", options=["Todos", "RS", "SP", "PR"], index=0)

st.sidebar.markdown("---")
st.sidebar.markdown("### 📋 Opções do Relatório")
cfg_include_bairros = st.sidebar.checkbox("Incluir bairros no texto", value=True)
cfg_detailed_events = st.sidebar.checkbox("Detalhes de eventos (CPFL)", value=False)
cfg_include_occurrences = st.sidebar.checkbox("Incluir total de ocorrências", value=True)

cfg_custom_header = st.sidebar.text_area("Cabeçalho Personalizado", placeholder="Padrão: 🚨 RELATÓRIO DE INTERRUPÇÃO...")
cfg_custom_footer = st.sidebar.text_area("Rodapé Personalizado", placeholder="Mensagem adicional ou assinatura...")

st.sidebar.markdown("---")
if st.sidebar.button("🔄 Atualizar Dados das APIs", width="stretch"):
    # Clear selections to avoid mismatch on refresh
    st.session_state.selected_ids.clear()
    load_data(refresh=True)
    st.rerun()

# Display Sync Status alert in sidebar
if sync_status == "fresh":
    st.sidebar.success(f"✅ Sincronizado às {last_update.strftime('%H:%M:%S')}")
elif sync_status == "partial":
    st.sidebar.warning(f"⚠️ Sincronizado com dados parciais às {last_update.strftime('%H:%M:%S')}")
else:
    st.sidebar.error(f"❌ Offline (Usando Histórico)")

# --- MAIN APP LAYOUT ---
# Header
col_header_logo, col_header_title = st.columns([1, 15])
with col_header_logo:
    st.write("# ⚡")
with col_header_title:
    st.title("Painel de Interrupções de Energia")

st.markdown("---")

# Main Columns (Left: Interactive Panel / Right: WhatsApp Text Preview)
col_main, col_report = st.columns([3, 2])

# Filtering logic
filtered_mun = []
for mun in municipalities:
    if search_query and search_query.lower() not in mun["nome"].lower():
        continue
    
    concess = mun["concessionaria"]
    if "CEEE" in concess and not show_ceee:
        continue
    if ("CPFL" in concess or "RGE" in concess) and not show_cpfl:
        continue
        
    if selected_state != "Todos" and mun["estado"] != selected_state:
        continue
        
    filtered_mun.append(mun)

# Left Interactive Column
with col_main:
    tabs = st.tabs(["📍 Municípios Afetados", "📝 Detalhamento de Cidade", "📊 Estatísticas & Histórico"])
    
    # --- TAB 1: LIST & SELECTION ---
    with tabs[0]:
        st.subheader("📍 Municípios Afetados")
        st.markdown(f"Exibindo **{len(filtered_mun)}** municípios afetados.")
        
        # Calculate selected items statistics
        selected_items = [m for m in municipalities if m["id"] in st.session_state.selected_ids]
        s_mun = len(selected_items)
        s_ocor = sum(m["ocorrencias"] for m in selected_items)
        s_afet = sum(m["unidades_afetadas"] for m in selected_items)
        s_teams = sum(m["equipes"] for m in selected_items)
        
        # Selected Summary Widgets
        st.markdown("#### Resumo da Seleção")
        m_col1, m_col2, m_col3, m_col4 = st.columns(4)
        m_col1.metric("Municípios", s_mun)
        m_col2.metric("Ocorrências", s_ocor)
        m_col3.metric("Clientes Sem Luz", f"{s_afet:,}".replace(",", "."))
        m_col4.metric("Equipes Ativas", s_teams)
        
        st.markdown("")
        
        # Selection action buttons
        btn_col1, btn_col2 = st.columns(2)
        if btn_col1.button("✅ Selecionar Todos os Filtrados", width="stretch"):
            for m in filtered_mun:
                st.session_state.selected_ids.add(m["id"])
            st.rerun()
            
        if btn_col2.button("❌ Limpar Seleção", width="stretch"):
            st.session_state.selected_ids.clear()
            st.rerun()
            
        st.markdown("---")
        
        # Cards Container Grid
        if not filtered_mun:
            st.info("Nenhum município com interrupção corresponde aos filtros.")
        else:
            # 2 Columns grid for cards
            grid_cols = st.columns(2)
            for idx, mun in enumerate(filtered_mun):
                col_idx = idx % 2
                with grid_cols[col_idx]:
                    # Card Container
                    with st.container(border=True):
                        # Line 1: Checkbox and Title Row
                        c1, c2 = st.columns([1, 6])
                        with c1:
                            is_selected = st.checkbox(
                                "Selecionar",
                                value=mun["id"] in st.session_state.selected_ids,
                                key=f"chk_{mun['id']}",
                                label_visibility="collapsed"
                            )
                            if is_selected:
                                st.session_state.selected_ids.add(mun["id"])
                            else:
                                st.session_state.selected_ids.discard(mun["id"])
                        with c2:
                            badge_class = "badge-ceee" if "CEEE" in mun["concessionaria"] else "badge-cpfl"
                            st.markdown(
                                f"**{mun['nome']}** <span class='badge badge-state'>{mun['estado']}</span>"
                                f"<span class='badge {badge_class}'>{mun['concessionaria']}</span>",
                                unsafe_allow_html=True
                            )
                            
                        # Line 2: Card Metrics
                        st.markdown(
                            f"📌 **{mun['ocorrencias']}** ocor. | "
                            f"👥 **{mun['unidades_afetadas']:,}** u.c. | "
                            f"🛠️ **{mun['equipes']}** equipes".replace(",", "."),
                            unsafe_allow_html=True
                        )
                        
                        # Line 3: Detail trigger button
                        if st.button("🔎 Detalhes", key=f"det_btn_{mun['id']}", width="stretch"):
                            st.session_state.active_detail_id = mun["id"]
                            st.success(f"Detalhes de {mun['nome']} carregados. Clique na aba '📝 Detalhamento de Cidade'!")

    # --- TAB 2: GRANULAR DETAILS VIEW ---
    with tabs[1]:
        st.subheader("📝 Detalhamento de Bairros & Eventos")
        
        # Create a selectbox linked to selected city details
        city_names = [m["nome"] for m in municipalities]
        
        default_index = 0
        if st.session_state.active_detail_id:
            for idx, m in enumerate(municipalities):
                if m["id"] == st.session_state.active_detail_id:
                    default_index = idx
                    break
                    
        if city_names:
            selected_city_name = st.selectbox(
                "Escolha um município para ver informações detalhadas:",
                options=city_names,
                index=default_index
            )
            
            selected_city = next((m for m in municipalities if m["nome"] == selected_city_name), None)
            
            if selected_city:
                st.session_state.active_detail_id = selected_city["id"]
                
                badge_class = "badge-ceee" if "CEEE" in selected_city["concessionaria"] else "badge-cpfl"
                st.markdown(
                    f"### 📍 {selected_city['nome']} ({selected_city['estado']}) "
                    f"<span class='badge {badge_class}'>{selected_city['concessionaria']}</span>",
                    unsafe_allow_html=True
                )
                
                c_col1, c_col2, c_col3 = st.columns(3)
                c_col1.metric("Total Ocorrências", selected_city["ocorrencias"])
                c_col2.metric("Unidades Consumidoras Afetadas", f"{selected_city['unidades_afetadas']:,}".replace(",", "."))
                c_col3.metric("Equipes em Campo", selected_city["equipes"])
                
                st.markdown("#### Bairros Afetados")
                bairros = selected_city.get("bairros", [])
                
                if not bairros:
                    st.info("Nenhum bairro com detalhes disponível para esta cidade.")
                else:
                    for b in bairros:
                        with st.container(border=True):
                            st.markdown(f"##### 📍 Bairro: {b['nome']}")
                            st.markdown(
                                f"📌 **{b['ocorrencias']}** ocorrências | "
                                f"👥 **{b['unidades_afetadas']:,}** u.c. afetadas".replace(",", ".")
                            )
                            
                            # CEEE status breakdowns
                            if "CEEE" in selected_city["concessionaria"]:
                                status_map = b.get("status", {})
                                if status_map:
                                    active_statuses = [f"{k}: **{v}** ocor." for k, v in status_map.items() if v > 0]
                                    if active_statuses:
                                        st.markdown("🔍 **Status:** " + ", ".join(active_statuses))
                            else: # CPFL details
                                events = b.get("eventos", [])
                                if events:
                                    st.markdown("**Ordens de Serviço Ativas:**")
                                    for ev in events:
                                        st.markdown(
                                            f"- 🛠️ **OS {ev.get('numero', 'N/A')}** ({ev.get('tipo', 'N/A')}) — "
                                            f"Status: **{ev.get('status', 'N/A')}** | "
                                            f"Clientes: **{ev.get('clientes', 0)}** | "
                                            f"Duração: **{ev.get('duracao', 'N/A')}** | "
                                            f"Início: *{ev.get('hora', 'N/A')}*"
                                        )
        else:
            st.info("Nenhum município carregado.")

    # --- TAB 3: STATS & HISTORY DASHBOARD ---
    with tabs[2]:
        st.subheader("📊 Estatísticas & Dashboard Histórico")
        
        total_runs, max_occurrences, max_affected = get_stats_summary()
        
        if total_runs == 0:
            st.info("Sem registros históricos salvos no banco de dados. "
                    "Clique em 'Atualizar Dados das APIs' no menu lateral para registrar a primeira rodada.")
        else:
            # Historical Stats Summary
            st.markdown("#### Histórico Geral de Coletas")
            h_col1, h_col2, h_col3 = st.columns(3)
            h_col1.metric("Leituras Executadas", total_runs)
            h_col2.metric("Pico Histórico (Ocorrências)", max_occurrences)
            h_col3.metric("Pico Histórico (Clientes sem Luz)", f"{max_affected:,}".replace(",", "."))
            
            # Evolution charts
            st.markdown("---")
            st.subheader("📈 Evolução Temporal (Últimas 48 Leituras)")
            df_history = get_historical_evolution(48)
            
            if not df_history.empty:
                chart_col1, chart_col2 = st.columns(2)
                
                with chart_col1:
                    st.write("**Ocorrências Totais em Aberto**")
                    df_occurrences = df_history.set_index('timestamp')[['total_occurrences']]
                    st.line_chart(df_occurrences, color="#eab308")
                    
                with chart_col2:
                    st.write("**Clientes Sem Fornecimento (u.c.)**")
                    df_affected = df_history.set_index('timestamp')[['total_affected']]
                    st.line_chart(df_affected, color="#3b82f6")
            
            # Impact Chart (Latest read)
            st.markdown("---")
            st.subheader("📊 Impacto por Concessionária (Leitura Atual)")
            df_impact = get_concessionaire_impact_data()
            if not df_impact.empty:
                df_impact_plot = df_impact.set_index('concessionaria')[['unidades_afetadas']]
                st.bar_chart(df_impact_plot, color="#10b981")
                
                st.dataframe(
                    df_impact.rename(columns={
                        "concessionaria": "Concessionária",
                        "ocorrencias": "Ocorrências",
                        "unidades_afetadas": "Clientes Afetados",
                        "equipes": "Equipes"
                    }),
                    width="stretch",
                    hide_index=True
                )
            
            # Ranking Top 5
            st.markdown("---")
            st.subheader("Municípios Mais Afetados (Ativos)")
            df_top = get_top_cities_active()
            if not df_top.empty:
                st.dataframe(
                    df_top.rename(columns={
                        "nome": "Cidade",
                        "concessionaria": "Concessionária",
                        "ocorrencias": "Ocorrências",
                        "unidades_afetadas": "Clientes Afetados",
                        "equipes": "Equipes em Campo"
                    }),
                    width="stretch",
                    hide_index=True
                )

# Right Column - WhatsApp Text Preview & Copy Features
with col_report:
    st.subheader("💬 Relatório WhatsApp")
    
    # Generate current raw report
    report_text = generate_whatsapp_text(
        selected_items=selected_items,
        custom_header=cfg_custom_header if cfg_custom_header.strip() else None,
        custom_footer=cfg_custom_footer if cfg_custom_footer.strip() else None,
        include_bairros=cfg_include_bairros,
        include_events_details=cfg_detailed_events,
        include_occurrences=cfg_include_occurrences
    )
    
    # Sync with session state for user-editable text area
    # This prevents the user's manual edits from getting wiped during minor reruns (like typing),
    # but updates the report text immediately when selection changes.
    if "user_report" not in st.session_state or st.session_state.get("prev_report_text") != report_text:
        st.session_state.user_report = report_text
        st.session_state.prev_report_text = report_text

    st.write("Copie ou edite o relatório abaixo:")
    report_editor = st.text_area(
        "Texto do Relatório (Editável)",
        value=st.session_state.user_report,
        height=350,
        label_visibility="collapsed"
    )
    st.session_state.user_report = report_editor
    
    # Quick Copy helper codeblock
    st.write("📋 **Cópia Rápida (Clique no botão no canto superior direito)**:")
    st.code(report_editor, language="text")
    
    # Universal WhatsApp Web Send Button
    encoded_text = urllib.parse.quote(report_editor)
    whatsapp_url = f"https://api.whatsapp.com/send?text={encoded_text}"
    st.link_button("📲 Enviar para WhatsApp", url=whatsapp_url, width="stretch", type="primary")
    
    st.markdown("""
    ---
    💡 **Como usar o Relatório**:
    1. Marque ou desmarque os municípios no painel **📍 Municípios Afetados**.
    2. O relatório consolidado é gerado automaticamente.
    3. Edite o texto se quiser acrescentar detalhes manuais.
    4. Copie o texto ou envie diretamente no WhatsApp clicando no botão verde.
    """)
