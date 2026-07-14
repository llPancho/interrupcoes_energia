// State Management
let municipalities = [];
let selectedIds = new Set();
let activeDetailId = null;
let isLoading = false;

// DOM Elements
const searchInput = document.getElementById('search-input');
const filterCeee = document.getElementById('filter-ceee');
const filterCpflRge = document.getElementById('filter-cpfl-rge');

// Stats Widgets
const statsCount = document.getElementById('stats-selected-count');
const statsOutages = document.getElementById('stats-selected-outages');
const statsAffected = document.getElementById('stats-selected-affected');
const statsTeams = document.getElementById('stats-selected-teams');

// List Controls
const btnSelectAll = document.getElementById('btn-select-all');
const btnDeselectAll = document.getElementById('btn-deselect-all');
const cardsContainer = document.getElementById('cards-container');
const outageListCounter = document.getElementById('outage-list-counter');

// Header Meta
const syncIndicator = document.getElementById('sync-indicator');
const syncText = document.getElementById('sync-text');
const btnRefreshData = document.getElementById('btn-refresh-data');

// Tabs & Right Panel
const tabWhatsapp = document.getElementById('tab-whatsapp');
const tabDetails = document.getElementById('tab-details');
const contentWhatsapp = document.getElementById('content-whatsapp');
const contentDetails = document.getElementById('content-details');

const whatsappTextOutput = document.getElementById('whatsapp-text-output');
const btnCopyText = document.getElementById('btn-copy-text');
const btnSendWhatsapp = document.getElementById('btn-send-whatsapp');

// Formatting Config Elements
const cfgIncludeBairros = document.getElementById('cfg-include-bairros');
const cfgDetailedEvents = document.getElementById('cfg-detailed-events');
const cfgIncludeOccurrences = document.getElementById('cfg-include-occurrences');
const cfgCustomHeader = document.getElementById('cfg-custom-header');
const cfgCustomFooter = document.getElementById('cfg-custom-footer');

// Details Container
const detailsPlaceholder = document.getElementById('details-view-placeholder');
const detailsContainer = document.getElementById('details-view-container');
const detMunName = document.getElementById('det-mun-name');
const detMunConcessBadge = document.getElementById('det-mun-concess-badge');
const detValOutages = document.getElementById('det-val-outages');
const detValAffected = document.getElementById('det-val-affected');
const detValTeams = document.getElementById('det-val-teams');
const detBairrosList = document.getElementById('det-bairros-list');

// Toast
const copyToast = document.getElementById('copy-toast');

// Initialize App
document.addEventListener('DOMContentLoaded', () => {
    fetchData();
    setupEventListeners();
});

// Event Listeners
function setupEventListeners() {
    // Refresh Button
    btnRefreshData.addEventListener('click', () => fetchData(true));

    // Filters & Search
    searchInput.addEventListener('input', renderList);
    filterCeee.addEventListener('change', renderList);
    filterCpflRge.addEventListener('change', renderList);

    // List selection shortcuts
    btnSelectAll.addEventListener('click', selectAllFiltered);
    btnDeselectAll.addEventListener('click', deselectAll);

    // Config options auto-regenerate report
    cfgIncludeBairros.addEventListener('change', generateWhatsappReport);
    cfgDetailedEvents.addEventListener('change', generateWhatsappReport);
    cfgIncludeOccurrences.addEventListener('change', generateWhatsappReport);
    cfgCustomHeader.addEventListener('input', debounce(generateWhatsappReport, 500));
    cfgCustomFooter.addEventListener('input', debounce(generateWhatsappReport, 500));

    // Tabs
    tabWhatsapp.addEventListener('click', () => switchTab('whatsapp'));
    tabDetails.addEventListener('click', () => switchTab('details'));

    // Output Actions
    btnCopyText.addEventListener('click', copyReportToClipboard);
    btnSendWhatsapp.addEventListener('click', sendReportToWhatsapp);
}

// Fetch Data from API
async function fetchData(forceRefresh = false) {
    if (isLoading) return;
    setLoadingState(true);

    try {
        const url = `/api/data?refresh=${forceRefresh}`;
        const response = await fetch(url);
        if (!response.ok) throw new Error("Erro de rede ao buscar dados.");
        
        const resData = await response.json();
        municipalities = resData.data;

        // Display sync update time and status indicator
        const updateTime = new Date(resData.timestamp);
        const formattedTime = updateTime.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
        
        if (resData.status === "partial_fallback") {
            syncIndicator.className = "sync-dot warning";
            syncText.textContent = `Atualizado às ${formattedTime} (Dados Parciais)`;
            syncText.style.color = "var(--accent-orange)";
        } else if (resData.status === "fallback") {
            syncIndicator.className = "sync-dot error";
            syncText.textContent = `Offline (Usando Histórico)`;
            syncText.style.color = "var(--accent-red)";
        } else {
            syncIndicator.className = "sync-dot";
            syncText.textContent = `Atualizado às ${formattedTime}`;
            syncText.style.color = "";
        }
        
        // Retain selection if the items still exist, otherwise clear obsolete ones
        const validIds = new Set(municipalities.map(m => m.id));
        selectedIds = new Set([...selectedIds].filter(id => validIds.has(id)));

        renderList();
        updateStats();
        generateWhatsappReport();
        
        // Update detail panel if active
        if (activeDetailId && validIds.has(activeDetailId)) {
            showDetails(activeDetailId);
        } else {
            resetDetailsView();
        }

    } catch (error) {
        console.error("Error fetching data:", error);
        cardsContainer.innerHTML = `<div class="no-data-msg" style="color: var(--accent-red)">❌ Falha ao carregar dados: ${error.message}</div>`;
        syncText.textContent = "Erro na sincronização";
    } finally {
        setLoadingState(false);
    }
}

// Set Loading UI States
function setLoadingState(loading) {
    isLoading = loading;
    if (loading) {
        syncIndicator.classList.add('loading');
        btnRefreshData.classList.add('loading');
        btnRefreshData.disabled = true;
    } else {
        syncIndicator.classList.remove('loading');
        btnRefreshData.classList.remove('loading');
        btnRefreshData.disabled = false;
    }
}

// Filter and Render Municipality Cards
function renderList() {
    const query = searchInput.value.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
    
    // Read filter states
    const showCeee = filterCeee.checked;
    const showCpflRge = filterCpflRge.checked;

    // Filter municipalities array
    const filtered = municipalities.filter(mun => {
        // Name Search Filter
        const nameNormalized = mun.nome.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
        if (query && !nameNormalized.includes(query)) return false;

        // Concessionaire Filter
        const concess = mun.concessionaria;
        if (concess === "CEEE Equatorial") {
            if (!showCeee) return false;
        } else if (concess.includes("CPFL (RGE)") || concess.includes("RGE")) {
            if (!showCpflRge) return false;
        } else {
            return false;
        }

        return true;
    });

    // Update Counter text
    outageListCounter.textContent = `${filtered.length} municípios exibidos`;

    // Clear Container
    cardsContainer.innerHTML = '';

    if (filtered.length === 0) {
        cardsContainer.innerHTML = `<div class="no-data-msg">Nenhum município com interrupção corresponde aos filtros.</div>`;
        return;
    }

    // Build Cards
    filtered.forEach(mun => {
        const isSelected = selectedIds.has(mun.id);
        const card = document.createElement('div');
        card.className = `municipality-card ${isSelected ? 'selected' : ''}`;
        card.setAttribute('data-id', mun.id);

        // Classify concessionaire for badge
        const badgeClass = mun.concessionaria === "CEEE Equatorial" ? "badge-ceee" : "badge-cpfl";

        // Card HTML
        card.innerHTML = `
            <input type="checkbox" class="card-select-checkbox" ${isSelected ? 'checked' : ''} aria-label="Selecionar ${mun.nome}">
            <div class="card-body">
                <div class="card-title-row">
                    <span class="card-title">${mun.nome}</span>
                    <span class="badge badge-state">${mun.estado}</span>
                    <span class="badge ${badgeClass}">${mun.concessionaria}</span>
                </div>
                <div class="card-metrics">
                    <span class="metric-item ${mun.ocorrencias > 5 ? 'critical' : ''}">
                        <span class="metric-icon">📌</span> ${mun.ocorrencias} ocor.
                    </span>
                    <span class="metric-item ${mun.unidades_afetadas > 1000 ? 'critical' : mun.unidades_afetadas > 100 ? 'warning' : ''}">
                        <span class="metric-icon">👥</span> ${mun.unidades_afetadas.toLocaleString('pt-BR')} u.c.
                    </span>
                    <span class="metric-item">
                        <span class="metric-icon">🛠️</span> ${mun.equipes} equipes
                    </span>
                </div>
            </div>
            <div class="card-actions">
                <button class="btn-details" data-detail-id="${mun.id}">Detalhes</button>
            </div>
        `;

        // Card Click Handling (selecting / details)
        card.addEventListener('click', (e) => {
            // If details button is clicked, show details
            if (e.target.classList.contains('btn-details') || e.target.closest('.btn-details')) {
                const id = mun.id;
                showDetails(id);
                switchTab('details');
                e.stopPropagation();
                return;
            }

            // If checkbox or card body clicked, toggle selection
            if (e.target.type !== 'checkbox') {
                const cb = card.querySelector('.card-select-checkbox');
                cb.checked = !cb.checked;
            }

            toggleSelection(mun.id, card);
        });

        cardsContainer.appendChild(card);
    });
}

// Toggle Selection State
function toggleSelection(id, cardElement) {
    if (selectedIds.has(id)) {
        selectedIds.delete(id);
        cardElement.classList.remove('selected');
        cardElement.querySelector('.card-select-checkbox').checked = false;
    } else {
        selectedIds.add(id);
        cardElement.classList.add('selected');
        cardElement.querySelector('.card-select-checkbox').checked = true;
    }

    updateStats();
    generateWhatsappReport();
}

// Select All Filtered Municipalities
function selectAllFiltered() {
    const cards = cardsContainer.querySelectorAll('.municipality-card');
    cards.forEach(card => {
        const id = card.getAttribute('data-id');
        if (!selectedIds.has(id)) {
            selectedIds.add(id);
            card.classList.add('selected');
            card.querySelector('.card-select-checkbox').checked = true;
        }
    });
    updateStats();
    generateWhatsappReport();
}

// Deselect All Municipalities
function deselectAll() {
    selectedIds.clear();
    const cards = cardsContainer.querySelectorAll('.municipality-card');
    cards.forEach(card => {
        card.classList.remove('selected');
        const cb = card.querySelector('.card-select-checkbox');
        if (cb) cb.checked = false;
    });
    updateStats();
    generateWhatsappReport();
}

// Update Selected statistics summary widgets
function updateStats() {
    let munCount = selectedIds.size;
    let outagesCount = 0;
    let affectedCount = 0;
    let teamsCount = 0;

    municipalities.forEach(mun => {
        if (selectedIds.has(mun.id)) {
            outagesCount += mun.ocorrencias;
            affectedCount += mun.unidades_afetadas;
            teamsCount += mun.equipes;
        }
    });

    statsCount.textContent = munCount;
    statsOutages.textContent = outagesCount;
    statsAffected.textContent = affectedCount.toLocaleString('pt-BR');
    statsTeams.textContent = teamsCount;
}

// Request and Render generated WhatsApp Report
async function generateWhatsappReport() {
    if (selectedIds.size === 0) {
        whatsappTextOutput.value = '';
        whatsappTextOutput.placeholder = 'Selecione municípios na lista ao lado para gerar o texto do relatório do WhatsApp...';
        return;
    }

    whatsappTextOutput.value = 'Gerando relatório...';

    try {
        const response = await fetch('/api/generate_whatsapp', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                selected_ids: Array.from(selectedIds),
                custom_header: cfgCustomHeader.value.trim() || null,
                custom_footer: cfgCustomFooter.value.trim() || null,
                include_bairros: cfgIncludeBairros.checked,
                include_events_details: cfgDetailedEvents.checked,
                include_occurrences: cfgIncludeOccurrences.checked
            })
        });

        if (!response.ok) throw new Error("Falha na geração do texto.");
        
        const data = await response.json();
        whatsappTextOutput.value = data.text;
    } catch (error) {
        console.error("Error generating report:", error);
        whatsappTextOutput.value = `❌ Erro ao gerar relatório: ${error.message}`;
    }
}

// Copy WhatsApp Text to Clipboard
async function copyReportToClipboard() {
    const text = whatsappTextOutput.value;
    if (!text || text.startsWith('Gerando') || text.startsWith('❌')) return;

    try {
        await navigator.clipboard.writeText(text);
        showToast();
    } catch (err) {
        console.error('Failed to copy text: ', err);
        // Fallback copy
        whatsappTextOutput.select();
        document.execCommand('copy');
        showToast();
    }
}

// Share text on WhatsApp Web
function sendReportToWhatsapp() {
    const text = whatsappTextOutput.value;
    if (!text || text.startsWith('Gerando') || text.startsWith('❌')) return;

    const encodedText = encodeURIComponent(text);
    // Detect mobile device to choose the best WhatsApp sharing URL
    const isMobile = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
    const whatsappUrl = isMobile 
        ? `https://api.whatsapp.com/send?text=${encodedText}`
        : `https://web.whatsapp.com/send?text=${encodedText}`;
    window.open(whatsappUrl, '_blank');
}

// Show Toast Notification
function showToast() {
    copyToast.classList.add('show');
    setTimeout(() => {
        copyToast.classList.remove('show');
    }, 3000);
}

// Tab Switching Logic
function switchTab(tab) {
    if (tab === 'whatsapp') {
        tabWhatsapp.classList.add('active');
        tabDetails.classList.remove('active');
        contentWhatsapp.classList.add('active');
        contentDetails.classList.remove('active');
    } else if (tab === 'details') {
        tabWhatsapp.classList.remove('active');
        tabDetails.classList.add('active');
        contentWhatsapp.classList.remove('active');
        contentDetails.classList.add('active');
    }
}

// Show Detailed view of a Municipality
function showDetails(id) {
    activeDetailId = id;
    const mun = municipalities.find(m => m.id === id);
    if (!mun) return;

    // Display container
    detailsPlaceholder.style.display = 'none';
    detailsContainer.style.display = 'flex';

    // Populate Headers & stats
    detMunName.textContent = `${mun.nome} [${mun.estado}]`;
    detMunConcessBadge.textContent = mun.concessionaria;
    detMunConcessBadge.className = `badge ${mun.concessionaria === "CEEE Equatorial" ? "badge-ceee" : "badge-cpfl"}`;
    
    detValOutages.textContent = mun.ocorrencias;
    detValAffected.textContent = mun.unidades_afetadas.toLocaleString('pt-BR');
    detValTeams.textContent = mun.equipes;

    // Populate Bairros List
    detBairrosList.innerHTML = '';
    
    if (!mun.bairros || mun.bairros.length === 0) {
        detBairrosList.innerHTML = '<div class="no-data-msg">Nenhum bairro listado com detalhes.</div>';
        return;
    }

    mun.bairros.forEach(b => {
        const card = document.createElement('div');
        card.className = 'bairro-detail-card';

        // Check if CEEE (aggregates status dict) or CPFL (has list of events)
        let eventsHtml = '';
        if (b.eventos && b.eventos.length > 0) {
            // CPFL Events
            b.eventos.forEach(ev => {
                eventsHtml += `
                    <div class="event-item-detail">
                        <div class="event-header">
                            <span>OS: ${ev.numero || 'N/A'}</span>
                            <span style="color: ${ev.status === 'Em Execução' ? '#4ade80' : '#facc15'}">${ev.status || 'N/A'}</span>
                        </div>
                        <div>Tipo: ${ev.tipo || 'N/A'}</div>
                        <div>Clientes afetados: ${ev.clientes || 0}</div>
                        <div>Duração: ${ev.duracao || 'N/A'}</div>
                        <div style="color: var(--text-muted); font-size: 0.7rem;">Início: ${ev.hora || 'N/A'}</div>
                    </div>
                `;
            });
        } else if (b.status && Object.keys(b.status).length > 0) {
            // CEEE Status summaries
            const stParts = Object.entries(b.status)
                .filter(([_, count]) => count > 0)
                .map(([name, count]) => `<span>${name}: <strong>${count} ocor.</strong></span>`);
            if (stParts.length > 0) {
                eventsHtml += `
                    <div class="event-item-detail" style="border-left-color: var(--accent-teal)">
                        <div style="display:flex; flex-direction:column; gap: 0.25rem;">
                            ${stParts.join('')}
                        </div>
                    </div>
                `;
            }
        }

        card.innerHTML = `
            <div class="bairro-detail-name">
                <span>📍 ${b.nome}</span>
            </div>
            <div class="bairro-detail-stats">
                <span>📌 ${b.ocorrencias} ocorrência(s)</span>
                <span>👥 ${b.unidades_afetadas.toLocaleString('pt-BR')} u.c. afetadas</span>
                ${b.equipes > 0 ? `<span>🛠️ ${b.equipes} equipes</span>` : ''}
            </div>
            ${eventsHtml}
        `;

        detBairrosList.appendChild(card);
    });
}

// Reset Details View
function resetDetailsView() {
    activeDetailId = null;
    detailsPlaceholder.style.display = 'block';
    detailsContainer.style.display = 'none';
}

// Helper: Debounce function for inputs
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}
