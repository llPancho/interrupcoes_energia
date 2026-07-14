# ⚡ Monitoramento de Interrupções de Energia & Relatórios para WhatsApp

Este projeto é uma ferramenta web interativa desenvolvida com **FastAPI** e **Vanilla Frontend (HTML/CSS/JS)** que automatiza o monitoramento de interrupções de fornecimento de energia elétrica. Ela consome dados de APIs públicas de duas grandes concessionárias brasileiras, consolida os dados de municípios afetados e gera relatórios otimizados para compartilhamento direto via **WhatsApp**.

---

## 🚀 Principais Funcionalidades

- **Consumo de APIs em Tempo Real**:
  - **CEEE Equatorial**: Monitoramento de bairros no Rio Grande do Sul (bypassa a proteção do WAF Incapsula via gestão de cookies).
  - **CPFL / RGE**: Cobertura nacional das distribuidoras do Grupo CPFL (RGE no RS, CPFL Paulista, Piratininga e Santa Cruz em SP/PR).
- **Interface Gráfica Premium**:
  - Design moderno em **Dark Mode** com efeitos de *glassmorphism* (vidro fosco).
  - Animações fluidas de carregamento e transições responsivas.
- **Filtros e Pesquisas Inteligentes**:
  - Busca em tempo real de municípios.
  - Filtros rápidos por concessionária e estado (**RS, SP, PR**).
  - Exibição de estatísticas consolidadas da seleção ativa (soma de ocorrências, clientes sem energia e equipes).
- **Visualização de Detalhes Granulares**:
  - Painel lateral interativo que lista bairros afetados por município.
  - Detalhamento de ordens de serviço (OS), status da ocorrência (Em Execução, Em Preparação), tipo (Programada/Não Programada) e contagem de clientes afetados por evento (conforme disponibilidade da distribuidora).
- **Gerador Automatizado de Mensagens para WhatsApp**:
  - Criação instantânea de mensagens com formatação rica do WhatsApp (`*negrito*`, `_itálico_`, marcadores, emojis).
  - Customização de cabeçalhos e rodapés.
  - Opções para incluir/omitir o total de ocorrências, bairros afetados e detalhes de eventos.
  - Botão de **Copiar Texto** com feedback visual instantâneo e botão de **Enviar via WhatsApp Web**.
- **Banco de Dados & Coleta Histórica**:
  - Banco de dados **SQLite** local (`outages.db`) que armazena os dados de interrupção de energia de forma persistente.
  - Coleta automática rodada **uma vez por hora** em segundo plano pelo servidor FastAPI.
  - Gravação automática de dados também a cada consulta manual (com debounce de 2 minutos para evitar spam).
- **Dashboard de Estatísticas Integrado**:
  - Aba de estatísticas com painel de indicadores (Leituras executadas, pico histórico de ocorrências e pico histórico de afetados).
  - **Gráfico de Evolução Temporal**: Linha temporal com eixo duplo (Y-esquerdo: Ocorrências, Y-direito: Clientes afetados) mostrando a evolução nas últimas 48h.
  - **Gráfico de Impacto**: Comparação visual (Doughnut) de impacto entre as concessionárias e distribuidoras.
  - **Ranking de Cidades**: Top 5 cidades com maior volume de ocorrências ativas.

---

## 🛠️ Stack Tecnológica

- **Backend**: Python 3, FastAPI, Uvicorn, SQLite3, Pydantic, HTTP Cookie Jar (`urllib`).
- **Frontend**: HTML5 Semântico, CSS3 (glassmorphism, flexbox/grid, animações), JavaScript Moderno (ES6, Fetch API), Chart.js (CDN para renderização dos gráficos).

---

## 📂 Estrutura do Projeto

```text
Dados_interruptacao_energia/
├── main.py               # Servidor FastAPI & APIs de raspagem de dados
├── static/               # Arquivos públicos do Frontend
│   ├── index.html        # Estrutura principal da página web
│   ├── style.css         # Folha de estilo CSS (Design & Efeitos)
│   └── app.js            # Lógica cliente JS (Filtros, Renderização & API)
├── README.md             # Documentação do projeto (este arquivo)
└── venv/                 # Ambiente virtual do Python (opcional)
```

---

## 🔧 Instalação e Execução

### 1. Pré-requisitos
Certifique-se de ter o **Python 3** instalado em sua máquina.

### 2. Instalação de Dependências
Crie um ambiente virtual e instale o FastAPI e o Uvicorn executando os seguintes comandos no terminal:

```bash
# Criar o ambiente virtual (caso ainda não possua)
python3 -m venv venv

# Instalar dependências necessárias
./venv/bin/pip install fastapi uvicorn
```

### 3. Sincronização e Inicialização do Servidor
Inicie a aplicação executando o servidor:

```bash
./venv/bin/python main.py
```

O servidor iniciará automaticamente na porta **8555**. Caso queira alterar a porta, você pode configurar a variável de ambiente `PORT` ou editá-la em `main.py`.

### 4. Acesso à Interface
Abra o navegador e navegue até:
[http://localhost:8555](http://localhost:8555)

---

## 🔗 Referência das APIs de Origem

Os links brutos fornecidos originalmente para o monitoramento estão documentados abaixo:

1. **CEEE Equatorial API**:
   - **URL**: [https://ceee.equatorialenergia.com.br/api-etr/resumo?nivel=bairro&estado=RS](https://ceee.equatorialenergia.com.br/api-etr/resumo?nivel=bairro&estado=RS)
   - *Nota*: Requer controle de cabeçalhos e persistência de cookies para responder status `200 OK` sem loop de redirecionamento.
   
2. **CPFL Energia API**:
   - **URL**: [https://www.cpfl.com.br/monitoramento-interrupcoes-fornecimento/dados](https://www.cpfl.com.br/monitoramento-interrupcoes-fornecimento/dados)
   - *Nota*: Retorna a lista geral de cidades atendidas pelas distribuidoras RGE, Paulista, Piratininga e Santa Cruz com as respectivas ordens de serviço ativas.