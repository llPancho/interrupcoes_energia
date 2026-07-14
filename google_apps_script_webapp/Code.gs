/**
 * Código Principal para o Google Apps Script (Code.gs)
 * 
 * Este arquivo contém as funções do backend do seu Web App no Google Apps Script.
 */

function doGet() {
  return HtmlService.createHtmlOutputFromFile('index')
      .setTitle('Painel de Interrupções de Energia')
      .addMetaTag('viewport', 'width=device-width, initial-scale=1');
}

// Auxiliar para obter a planilha ativa (funciona em scripts vinculados ou autônomos com ID)
function getSpreadsheet() {
  try {
    var ss = SpreadsheetApp.getActiveSpreadsheet();
    if (ss) return ss;
  } catch (e) {}
  
  var scriptProperties = PropertiesService.getScriptProperties();
  var sheetId = scriptProperties.getProperty("SPREADSHEET_ID");
  if (sheetId) {
    return SpreadsheetApp.openById(sheetId);
  }
  
  throw new Error(
    "Não foi possível encontrar a Planilha ativa. " +
    "Certifique-se de que o script foi aberto a partir de uma Planilha (Extensões > Apps Script) " +
    "ou configure a propriedade SPREADSHEET_ID nas configurações do projeto."
  );
}

// Auxiliares de Tratamento
function cleanName(str) {
  if (!str) return "";
  return str.trim().toLowerCase().replace(/\b\w/g, function(l) { return l.toUpperCase(); });
}

function mapIbgeToState(ibgeCode) {
  if (!ibgeCode) return "Desconhecido";
  var prefix = String(ibgeCode).substring(0, 2);
  var states = {
    "11": "RO", "12": "AC", "13": "AM", "14": "RR", "15": "PA", "16": "AP", "17": "TO",
    "21": "MA", "22": "PI", "23": "CE", "24": "RN", "25": "PB", "26": "PE", "27": "AL",
    "28": "SE", "29": "BA", "31": "MG", "32": "ES", "33": "RJ", "35": "SP", "41": "PR",
    "42": "SC", "43": "RS", "50": "MS", "51": "MT", "52": "GO", "53": "DF"
  };
  return states[prefix] || "Desconhecido";
}

// Raspador CEEE
function fetchCeeeData() {
  var url = "https://ceee.equatorialenergia.com.br/api-etr/resumo?nivel=bairro&estado=RS";
  var options = {
    "muteHttpExceptions": true,
    "headers": {
      "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
      "Accept": "application/json, text/plain, */*",
      "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
      "Referer": "https://ceee.equatorialenergia.com.br/"
    }
  };
  try {
    var response = UrlFetchApp.fetch(url, options);
    if (response.getResponseCode() == 200) {
      var data = JSON.parse(response.getContentText());
      var grupos = data.grupos || [];
      var munDict = {};
      
      grupos.forEach(function(item) {
        var munName = cleanName(item.municipio_nome || "");
        if (!munName) return;
        
        var bairroName = cleanName(item.bairro || "");
        var estado = item.estado || "RS";
        var ocorrencias = item.ocorrencias || 0;
        var unidadesAfetadas = item.unidades_afetadas || 0;
        var equipes = item.equipes_em_campo || 0;
        
        var statuses = {};
        var porStatus = item.por_status || {};
        for (var key in porStatus) {
          if (porStatus[key] && typeof porStatus[key] === 'object') {
            statuses[key] = porStatus[key].ocorrencias || 0;
          }
        }
        
        var bairroData = {
          "nome": bairroName,
          "ocorrencias": ocorrencias,
          "unidades_afetadas": unidadesAfetadas,
          "equipes": equipes,
          "status": statuses
        };
        
        if (!munDict[munName]) {
          munDict[munName] = {
            "id": "ceee-" + (item.municipio_ibge || munName.toLowerCase().replace(/ /g, "_")),
            "nome": munName,
            "concessionaria": "CEEE Equatorial",
            "estado": estado,
            "ocorrencias": 0,
            "unidades_afetadas": 0,
            "equipes": 0,
            "bairros": []
          };
        }
        
        munDict[munName].ocorrencias += ocorrencias;
        munDict[munName].unidades_afetadas += unidadesAfetadas;
        munDict[munName].equipes += equipes;
        munDict[munName].bairros.push(bairroData);
      });
      
      return Object.keys(munDict).map(function(k) { return munDict[k]; });
    }
  } catch (e) {
    Logger.log("Erro ao buscar CEEE: " + e);
  }
  return null;
}

// Raspador CPFL
function fetchCpflData() {
  var url = "https://www.cpfl.com.br/monitoramento-interrupcoes-fornecimento/dados";
  var options = {
    "muteHttpExceptions": true,
    "headers": {
      "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
  };
  try {
    var response = UrlFetchApp.fetch(url, options);
    var content = response.getContentText();
    
    if (content.indexOf("Waiting Room") !== -1 || content.indexOf("waitingroom") !== -1) {
      Logger.log("CPFL caiu na sala de espera do Cloudflare.");
      return null;
    }
    
    if (response.getResponseCode() == 200) {
      var data = JSON.parse(content);
      var dados = data.dados || [];
      if (dados.length == 0) return [];
      
      var cities = dados[0].cidades || [];
      var result = [];
      
      cities.forEach(function(city) {
        var munName = cleanName(city.nome || "");
        if (!munName) return;
        
        var distribuidora = (city.idDistribuidora || "").toUpperCase();
        var codIbge = city.codIbge;
        var estado = mapIbgeToState(codIbge);
        
        var teams = city.quantidadeEquipesEmAtendimento || 0;
        var ocorrencias = 0;
        var unidadesAfetadas = 0;
        var bairrosList = [];
        
        var bairros = city.bairros || [];
        bairros.forEach(function(b) {
          var bName = cleanName(b.nome || "");
          var bEvents = b.eventos || [];
          
          var bOcorrencias = bEvents.length;
          var bAfetadas = 0;
          var eventosList = [];
          
          bEvents.forEach(function(e) {
            bAfetadas += (e.quantidadeClientes || 0);
            eventosList.push({
              "numero": e.numeroEvento,
              "status": e.status,
              "tipo": e.tipo,
              "duracao": e.duracaoOcorrencia,
              "clientes": e.quantidadeClientes,
              "hora": e.dataHoraEvento
            });
          });
          
          ocorrencias += bOcorrencias;
          unidadesAfetadas += bAfetadas;
          
          bairrosList.push({
            "nome": bName,
            "ocorrencias": bOcorrencias,
            "unidades_afetadas": bAfetadas,
            "eventos": eventosList
          });
        });
        
        if ((ocorrencias > 0 || teams > 0) && estado === "RS") {
          result.push({
            "id": "cpfl-" + (codIbge || munName.toLowerCase().replace(/ /g, "_")),
            "nome": munName,
            "concessionaria": distribuidora === "RGE" ? "CPFL (RGE)" : "CPFL (" + distribuidora + ")",
            "estado": estado,
            "ocorrencias": ocorrencias,
            "unidades_afetadas": unidadesAfetadas,
            "equipes": teams,
            "bairros": bairrosList
          });
        }
      });
      return result;
    }
  } catch (e) {
    Logger.log("Erro ao buscar CPFL: " + e);
  }
  return null;
}

// Leitura da Planilha em caso de Falha
function getLatestFromSheet() {
  try {
    var ss = getSpreadsheet();
    var sheet = ss.getSheetByName("Atual");
    if (!sheet) return [];
    
    var lastRow = sheet.getLastRow();
    if (lastRow <= 1) return [];
    
    var values = sheet.getRange(2, 1, lastRow - 1, 7).getValues();
    var items = [];
    
    values.forEach(function(row) {
      var concessionaria = row[1];
      var nome = row[2];
      var estado = row[3];
      var ocorrencias = Number(row[4]) || 0;
      var unidadesAfetadas = Number(row[5]) || 0;
      var equipes = Number(row[6]) || 0;
      
      items.push({
        "id": (concessionaria === "CEEE Equatorial" ? "ceee-" : "cpfl-") + nome.toLowerCase().replace(/ /g, "_"),
        "nome": nome,
        "concessionaria": concessionaria,
        "estado": estado,
        "ocorrencias": ocorrencias,
        "unidades_afetadas": unidadesAfetadas,
        "equipes": equipes,
        "bairros": [] // Bairros detalhados não são armazenados na planilha resumida
      });
    });
    return items;
  } catch (e) {
    Logger.log("Erro ao ler da planilha: " + e);
    return [];
  }
}

// Chamada Principal do Frontend com cache de 2 minutos
function getEnergyData(forceRefresh) {
  var cache = CacheService.getScriptCache();
  var cached = cache.get("energy_data_json");
  
  if (!forceRefresh && cached) {
    Logger.log("Retornando dados do CacheService...");
    return JSON.parse(cached);
  }
  
  var now = new Date();
  Logger.log("Buscando dados frescos das APIs...");
  var ceeeItems = fetchCeeeData();
  var cpflItems = fetchCpflData();
  
  var isCeeeFresh = ceeeItems !== null;
  var isCpflFresh = cpflItems !== null;
  
  if (ceeeItems === null) {
    ceeeItems = getLatestFromSheet().filter(function(x) { return x.concessionaria === "CEEE Equatorial"; });
  }
  if (cpflItems === null) {
    cpflItems = getLatestFromSheet().filter(function(x) { return x.concessionaria !== "CEEE Equatorial"; });
  }
  
  var combined = ceeeItems.concat(cpflItems);
  
  // Salva na planilha se pelo menos uma API funcionou
  if (isCeeeFresh || isCpflFresh) {
    saveToSheet(combined);
  }
  
  combined.sort(function(a, b) {
    if (b.ocorrencias !== a.ocorrencias) {
      return b.ocorrencias - a.ocorrencias;
    }
    return a.nome.localeCompare(b.nome);
  });
  
  var statusStr = "fresh";
  if (!isCeeeFresh || !isCpflFresh) {
    statusStr = "partial_fallback";
  }
  if (!isCeeeFresh && !isCpflFresh) {
    statusStr = "fallback";
  }
  
  var response = {
    "status": statusStr,
    "timestamp": now.toISOString(),
    "data": combined
  };
  
  // Salva no cache por 2 minutos (120 segundos)
  try {
    cache.put("energy_data_json", JSON.stringify(response), 120);
  } catch (e) {
    Logger.log("Erro ao salvar no CacheService: " + e);
  }
  
  return response;
}

// Gravação em Planilha
function saveToSheet(items) {
  try {
    var ss = getSpreadsheet();
    
    var sheetAtual = ss.getSheetByName("Atual");
    if (!sheetAtual) {
      sheetAtual = ss.insertSheet("Atual");
    }
    sheetAtual.clear();
    sheetAtual.appendRow(["Atualizado Em", "Concessionária", "Município", "Estado", "Ocorrências", "Clientes Afetados", "Equipes"]);
    
    var sheetHistorico = ss.getSheetByName("Histórico");
    if (!sheetHistorico) {
      sheetHistorico = ss.insertSheet("Histórico");
      sheetHistorico.appendRow(["Timestamp", "Concessionária", "Município", "Estado", "Ocorrências", "Clientes Afetados", "Equipes"]);
    }
    
    var timestamp = new Date();
    var rowsData = [];
    
    items.forEach(function(item) {
      rowsData.push([
        timestamp,
        item.concessionaria,
        item.nome,
        item.estado,
        item.ocorrencias,
        item.unidades_afetadas,
        item.equipes
      ]);
    });
    
    if (rowsData.length > 0) {
      sheetAtual.getRange(2, 1, rowsData.length, rowsData[0].length).setValues(rowsData);
      
      var lastRow = sheetHistorico.getLastRow();
      sheetHistorico.getRange(lastRow + 1, 1, rowsData.length, rowsData[0].length).setValues(rowsData);
    }
  } catch (e) {
    Logger.log("Erro ao salvar na planilha: " + e);
  }
}

// Gatilho de tempo para rodar em background
function syncData() {
  Logger.log("Iniciando Sincronização em Background...");
  getEnergyData(true);
  Logger.log("Sincronização em Background concluída!");
}
