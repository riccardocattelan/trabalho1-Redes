# Sistema de Monitoramento de Fading Wi-Fi

## Visão Geral

Sistema completo para detecção e análise de fenômenos de fading em redes Wi-Fi, implementando conceitos da camada física do modelo OSI com análise assistida por IA.

## Arquitetura do Sistema

### Estrutura de Classes

#### 1. WiFiDataCollector
Responsável pela coleta de dados do sistema Windows.

**Métodos:**
- `get_wifi_info()`: Coleta RSSI, canal e frequência da interface Wi-Fi ativa

**Dados Coletados:**
- RSSI (Received Signal Strength Indicator) em dBm
- Canal Wi-Fi (1-14 para 2.4GHz, >14 para 5GHz)
- Frequência/Banda (2.4 GHz ou 5 GHz)

#### 2. FadingDetector
Implementa algoritmos de detecção de diferentes tipos de fading.

**Tipos de Fading Detectados:**

1. **Fast Fading**
   - Critério: Variação ≥ 10 dBm entre amostras consecutivas
   - Causa: Multipercurso, reflexões rápidas
   - Fenômeno: Interferência construtiva/destrutiva

2. **Slow Fading / Shadowing**
   - Critério: Queda contínua ≥ 8 dBm ao longo de 5 amostras
   - Causa: Obstáculos físicos (paredes, pessoas, móveis)
   - Fenômeno: Atenuação por bloqueio

3. **Multipath Fading**
   - Critério: 3+ oscilações ≥ 5 dBm em sequência
   - Causa: Múltiplos caminhos de propagação
   - Fenômeno: Padrão "dente de serra" por reflexões

4. **Variação Moderada**
   - Critério: Variação entre 6-9 dBm
   - Causa: Mudanças ambientais menores
   - Fenômeno: Flutuações normais do ambiente

#### 3. AIAnalyzer
Integração com LLM (Groq) para análise técnica dos eventos.

**Funcionalidades:**
- Análise contextual dos eventos de fading
- Explicação dos fenômenos físicos
- Relação com camada física OSI
- Sugestões de mitigação

**Prompt Engineering:**
O prompt é estruturado para fornecer:
- Contexto completo (RSSI, canal, frequência, evento)
- Análise técnica fundamentada
- Sugestões práticas de mitigação

## Interface do Usuário

### Layout em Abas

#### Aba 1: Monitoramento
- Gráfico de linha em tempo real (Plotly)
- Marcadores visuais para eventos de fading
- Métricas principais:
  - Sinal atual (dBm)
  - Média do sinal
  - Número de amostras
  - Total de eventos detectados

#### Aba 2: Análise
- **Relatório de IA**: Análise automática e manual dos eventos

#### Aba 3: Eventos
- Lista histórica dos últimos 15 eventos
- Informações detalhadas:
  - Timestamp
  - Tipo de evento
  - RSSI no momento
  - Canal e frequência

### Painel Lateral (Sidebar)

**Controles:**
- Botão Iniciar/Pausar monitoramento
- Indicador de status em tempo real
- Slider de intervalo de coleta (0.1 - 2.0 segundos)
- Botão de limpeza de dados
- Botão de exportação CSV

## Funcionalidades Implementadas

### 1. Coleta de Dados em Alta Frequência
- Intervalo configurável (padrão: 0.5s = 2 amostras/segundo)
- Coleta assíncrona sem bloquear a interface

### 2. Detecção Automática de Eventos
- Análise em tempo real dos últimos 5 pontos
- Classificação automática do tipo de fading
- Notificações via toast

### 3. Geração Automática de Relatórios
- Acionamento automático ao detectar eventos
- Contexto de 40 amostras para análise
- Inclusão de canal e frequência no contexto

### 4. Visualização Avançada
- Gráficos interativos com Plotly
- Zoom, pan e hover para análise detalhada
- Histogramas para análise estatística

### 5. Exportação de Dados
- Formato CSV com todas as colunas

## Configurações e Thresholds

```python
FAST_FADING_THRESHOLD = 10          # dBm
MODERATE_VARIATION_THRESHOLD = 6    # dBm
SLOW_FADING_THRESHOLD = 8           # dBm 
MULTIPATH_OSCILLATION_COUNT = 3     # número de oscilações
MULTIPATH_OSCILLATION_THRESHOLD = 5 # dBm por oscilação
```

## Instalação

### 1. Pré-requisitos
- Python 3.8 ou superior
- Windows (para coleta de dados Wi-Fi via netsh)
- Conta Groq (para API de IA)

### 2. Clonar o Repositório
```bash
git clone https://github.com/seu-usuario/trabalho1-Redes.git
cd trabalho1-Redes
```

### 3. Instalar Dependências
```bash
pip install -r requirements.txt
```

### 4. Configurar Variáveis de Ambiente

#### Obter API Key do Groq:
1. Acesse [https://console.groq.com/](https://console.groq.com/)
2. Crie uma conta (gratuita)
3. Gere uma API Key

#### Configurar arquivo .env:
1. Copie o arquivo de exemplo:
```bash
copy .env.example .env
```

2. Edite o arquivo `.env` e adicione sua API Key:
```env
GROQ_API_KEY=sua_api_key_aqui
MODELO_AI=llama-3.1-8b-instant
```

## Como Usar

### Inicialização
```bash
streamlit run app.py
```

## Tecnologias Utilizadas

- **Python 3.18**
- **Streamlit**: Framework web para interface
- **Pandas**: Manipulação de dados
- **NumPy**: Operações numéricas
- **Plotly**: Visualização interativa
- **Groq**: API de LLM para análise
- **subprocess**: Integração com sistema Windows
