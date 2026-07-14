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
├── google_apps_script.js # Código JavaScript para o Google Apps Script
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

## 📊 Hospedagem 100% Gratuita no Google Apps Script (Web App)

Caso você prefira rodar o sistema de forma **totalmente independente e gratuita**, sem a necessidade de servidores externos como a Railway, Vercel ou bancos de dados locais, você pode hospedar o painel inteiro dentro do **Google Apps Script** como um **Web App**. 

Nesta arquitetura, a Google hospeda a interface visual e executa as buscas de APIs de forma nativa e sem bloqueios (usando os IPs do próprio ecossistema do Google), salvando e recuperando o histórico em uma **Planilha do Google Sheets**.

Todos os arquivos compilados e prontos para implantação estão disponíveis na pasta [google_apps_script_webapp/](file:///home/erick/Documentos/Projetos/Dados_interruptacao_energia/google_apps_script_webapp).

### Passo 1: Criar a Planilha do Google
1. Crie uma nova planilha vazia no seu Google Drive.
2. O script criará automaticamente duas abas:
   - **`Atual`**: Mostra apenas o snapshot ativo e atualizado do momento.
   - **`Histórico`**: Registra o histórico cumulativo de todas as coletas feitas ao longo do tempo.

### Passo 2: Configurar o Apps Script
1. Na sua planilha, acesse **Extensões** > **Apps Script**.
2. No menu lateral do editor do Apps Script, crie exatamente dois arquivos:
   * **Arquivo de Script (`Code.gs`)**: Crie um arquivo chamado `Code` e cole as instruções de [Code.gs](file:///home/erick/Documentos/Projetos/Dados_interruptacao_energia/google_apps_script_webapp/Code.gs).
   * **Arquivo HTML (`index.html`)**: Crie um arquivo HTML chamado `index` e cole o código contido no arquivo compilado [index.html](file:///home/erick/Documentos/Projetos/Dados_interruptacao_energia/google_apps_script_webapp/index.html).
3. Salve o projeto do script clicando no ícone de disquete.

### Passo 3: Configurar o Disparador Automático (Trigger)
Para garantir que as informações sejam coletadas e salvas na planilha em segundo plano:
1. No menu lateral esquerdo do Apps Script, clique no ícone de relógio ⏰ (**Acionadores**).
2. Clique em **Adicionar acionador** no canto inferior direito.
3. Escolha a função a ser executada: **`syncData`**.
4. Selecione a origem do evento: **`Baseado no tempo`**.
5. Selecione o tipo de acionador baseado no tempo: **`Temporizador de hora em hora`** ou **`Temporizador de minutos`** (ex: a cada 30 minutos).
6. Clique em **Salvar** e conceda as permissões de acesso solicitadas para que o script possa modificar a planilha.

### Passo 4: Publicar o Web App
1. No topo direito do editor do Apps Script, clique em **Implantar** > **Nova implantação**.
2. Clique no ícone de engrenagem ⚙️ e selecione **Web App** (Aplicativo Web).
3. Configure os campos:
   * **Descrição**: `Painel de Energia`
   * **Executar como**: `Eu` (sua conta do Google)
   * **Quem tem acesso**: `Qualquer pessoa` (isso permite que você e outras pessoas acessem o painel)
4. Clique em **Implantar**.
5. Copie a **URL do web app** gerada. Abra esta URL no seu navegador e o seu painel estará online e funcionando!

---


## 🔗 Referência das APIs de Origem

Os links brutos fornecidos originalmente para o monitoramento estão documentados abaixo:

1. **CEEE Equatorial API**:
   - **URL**: [https://ceee.equatorialenergia.com.br/api-etr/resumo?nivel=bairro&estado=RS](https://ceee.equatorialenergia.com.br/api-etr/resumo?nivel=bairro&estado=RS)
   - *Nota*: Requer controle de cabeçalhos e persistência de cookies para responder status `200 OK` sem loop de redirecionamento.
   
2. **CPFL Energia API**:
   - **URL**: [https://www.cpfl.com.br/monitoramento-interrupcoes-fornecimento/dados](https://www.cpfl.com.br/monitoramento-interrupcoes-fornecimento/dados)
   - *Nota*: Retorna a lista geral de cidades atendidas pelas distribuidoras RGE, Paulista, Piratininga e Santa Cruz com as respectivas ordens de serviço ativas.