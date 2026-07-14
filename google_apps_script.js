/**
 * Google Apps Script para Coleta e Ingestão de Dados de Falta de Energia (CEEE / CPFL)
 * 
 * Este script roda nos servidores da Google. Ele:
 * 1. Coleta dados frescos da CEEE e CPFL/RGE (que não são bloqueados pelos WAFs devido aos IPs da Google).
 * 2. Atualiza uma planilha do Google Sheets com o histórico e estado atual de ocorrências.
 * 3. Envia os dados consolidados para o seu servidor da Railway usando o endpoint seguro de ingestão (/api/ingest).
 */

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
      
      // Agrega por município
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
    } else {
      Logger.log("CEEE respondeu com status: " + response.getResponseCode());
    }
  } catch (e) {
    Logger.log("Erro ao buscar CEEE: " + e);
  }
  return null;
}

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
      Logger.log("CPFL caiu no Cloudflare Waiting Room.");
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
    } else {
      Logger.log("CPFL respondeu com status: " + response.getResponseCode());
    }
  } catch (e) {
    Logger.log("Erro ao buscar CPFL: " + e);
  }
  return null;
}

function saveToSheet(items) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  
  // Aba 1: Atual (Limpa e reescreve os dados ativos no momento)
  var sheetAtual = ss.getSheetByName("Atual");
  if (!sheetAtual) {
    sheetAtual = ss.insertSheet("Atual");
  }
  sheetAtual.clear();
  sheetAtual.appendRow(["Atualizado Em", "Concessionária", "Município", "Estado", "Ocorrências", "Clientes Afetados", "Equipes"]);
  
  // Aba 2: Histórico (Adiciona novas linhas para fins de log e auditoria)
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
    // Escreve na aba Atual
    sheetAtual.getRange(2, 1, rowsData.length, rowsData[0].length).setValues(rowsData);
    
    // Escreve na aba Histórico
    var lastRow = sheetHistorico.getLastRow();
    sheetHistorico.getRange(lastRow + 1, 1, rowsData.length, rowsData[0].length).setValues(rowsData);
  }
}

function postToSystem(items) {
  var scriptProperties = PropertiesService.getScriptProperties();
  var serverUrl = scriptProperties.getProperty("SERVER_URL");
  var apiKey = scriptProperties.getProperty("API_KEY");
  
  if (!serverUrl || !apiKey) {
    Logger.log("Erro: SERVER_URL ou API_KEY não estão configurados nas propriedades do script.");
    return;
  }
  
  var url = serverUrl.replace(/\/$/, "") + "/api/ingest";
  var payload = {
    "api_key": apiKey,
    "items": items
  };
  
  var options = {
    "method": "post",
    "contentType": "application/json",
    "payload": JSON.stringify(payload),
    "muteHttpExceptions": true
  };
  
  try {
    var response = UrlFetchApp.fetch(url, options);
    Logger.log("Resposta do Servidor Ingestion: " + response.getContentText());
  } catch (e) {
    Logger.log("Erro ao enviar dados para o servidor: " + e);
  }
}

function syncData() {
  Logger.log("Iniciando Sincronização...");
  
  var ceeeItems = fetchCeeeData();
  var cpflItems = fetchCpflData();
  
  if (ceeeItems === null && cpflItems === null) {
    Logger.log("Ambas as APIs falharam.");
    return;
  }
  
  var combined = [];
  if (ceeeItems) combined = combined.concat(ceeeItems);
  if (cpflItems) combined = combined.concat(cpflItems);
  
  if (combined.length === 0) {
    Logger.log("Nenhum registro ativo encontrado.");
    return;
  }
  
  // 1. Salva na Planilha do Google
  try {
    saveToSheet(combined);
    Logger.log("Salvo nas planilhas 'Atual' e 'Histórico' com sucesso.");
  } catch (e) {
    Logger.log("Erro ao salvar na planilha: " + e);
  }
  
  // 2. Envia para a API na Railway
  try {
    postToSystem(combined);
    Logger.log("Dados enviados para a API do sistema com sucesso.");
  } catch (e) {
    Logger.log("Erro ao enviar para o sistema: " + e);
  }
}
