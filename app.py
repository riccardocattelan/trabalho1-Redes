import streamlit as st
import subprocess
import re
import time
import pandas as pd
import numpy as np
from datetime import datetime
from groq import Groq
import plotly.express as px
import plotly.graph_objects as go
from dotenv import load_dotenv
import os

# ============================================================================
# CONFIGURAÇÃO INICIAL
# ============================================================================

# Carrega variáveis de ambiente do arquivo .env
load_dotenv()

# Configuração da página do Streamlit
st.set_page_config(
    page_title="Sistema de Monitoramento de Fading Wi-Fi",
    layout="wide",  
    initial_sidebar_state="expanded"  
)

# Credenciais da API Groq carregadas do arquivo .env
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MODELO_AI = os.getenv("MODELO_AI", "llama-3.1-8b-instant")  # Valor padrão se não estiver no .env

FAST_FADING_THRESHOLD = 10              # Variação mínima em dBm para Fast Fading
MODERATE_VARIATION_THRESHOLD = 6        # Variação mínima em dBm para Variação Moderada
SLOW_FADING_THRESHOLD = 8               # Queda total mínima em dBm para Slow Fading
MULTIPATH_OSCILLATION_COUNT = 3         # Número mínimo de oscilações para Multipath
MULTIPATH_OSCILLATION_THRESHOLD = 5     # Variação mínima por oscilação em dBm



# ============================================================================
# CLASSE: COLETOR DE DADOS WI-FI
# ============================================================================

class WiFiDataCollector:
    """Gerencia a coleta de dados Wi-Fi do sistema Windows."""
    
    @staticmethod
    def get_wifi_info():
        """
        Coleta informações do sinal Wi-Fi incluindo RSSI, canal e frequência.
        
        Funcionamento:
        1. Executa comando 'netsh wlan show interfaces' do Windows
        2. Extrai RSSI (força do sinal) convertendo de % para dBm
        3. Extrai número do canal Wi-Fi
        4. Determina frequência (2.4 ou 5 GHz) baseado no tipo de rádio ou canal
        
        Retorna:
            dict: Dicionário contendo rssi, canal e frequencia, ou None se falhar.
        """
        try:
            # Configuração para ocultar janela do console ao executar comando
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            
            # Executa comando netsh para obter informações da interface Wi-Fi
            result = subprocess.check_output(
                ["netsh", "wlan", "show", "interfaces"],
                startupinfo=startupinfo,
                encoding='cp850',  
                errors='ignore'   
            )
            
            # Extrai RSSI 
            match_rssi = re.search(r"(Sinal|Signal)\s*:\s*(\d+)%", result)
            # Converte de porcentagem (0-100) para dBm (-100 a -50)
            rssi = (int(match_rssi.group(2)) / 2) - 100 if match_rssi else None
            
            # Extrai Canal Wi-Fi
            match_canal = re.search(r"(Canal|Channel)\s*:\s*(\d+)", result)
            canal = int(match_canal.group(2)) if match_canal else None
            
            # Extrai tipo de rádio 
            match_radio = re.search(r"(Radio type|Tipo de r.dio)\s*:\s*(.+)", result)
            radio_type = match_radio.group(2).strip() if match_radio else ""
            
            # Determina frequência baseado no tipo de rádio ou número do canal
            if "802.11a" in radio_type or "802.11ac" in radio_type or "802.11ax" in radio_type:
                frequencia = "5 GHz"
            elif canal and canal > 14:
                frequencia = "5 GHz"
            else:
                frequencia = "2.4 GHz"
            
            return {
                'rssi': rssi,
                'canal': canal,
                'frequencia': frequencia
            }
        except Exception as e:
            return None


# ============================================================================
# CLASSE: DETECTOR DE FADING
# ============================================================================

class FadingDetector:
    """Detecta diferentes tipos de padrões de fading em sinais Wi-Fi."""
    
    @staticmethod
    def detect_fading(novo_rssi, historico):
        """
        Analisa histórico de sinal para detectar padrões de fading.
        
        Funcionamento:
        1. Verifica se há amostras suficientes (mínimo 5)
        2. Testa Fast Fading (variação brusca)
        3. Testa Slow Fading (queda contínua)
        4. Testa Multipath Fading (oscilações repetitivas)
        5. Testa Variação Moderada
        
        Args:
            novo_rssi: Valor RSSI atual
            historico: DataFrame com dados históricos de RSSI
            
        Retorna:
            str: Tipo de fading detectado, ou None se nenhum
        """
        # Precisa de pelo menos 5 amostras para análise confiável
        if len(historico) < 5:
            return None
        
        # Pega as últimas 5 amostras para análise
        ultimos_5 = historico['rssi'].tail(5).tolist()
        
        # Calcula variação absoluta entre amostra atual e anterior
        delta_atual = abs(novo_rssi - ultimos_5[-1])
        
        # TESTE 1: Fast Fading - Variação brusca e grande
        # Exemplo: sinal muda de -50 para -60 dBm (10 dBm de diferença)
        if delta_atual >= FAST_FADING_THRESHOLD:
            return "Fast Fading"
        
        # TESTE 2: Slow Fading / Shadowing - Queda contínua
        if len(ultimos_5) >= 5:
            # Verifica se todas as amostras estão em queda (ou estáveis)
            # Ex: [-50, -52, -54, -56, -58] = queda contínua
            is_declining = all(ultimos_5[i] >= ultimos_5[i+1] for i in range(len(ultimos_5)-1))
            
            # Calcula queda total (primeira - última amostra)
            queda_total = ultimos_5[0] - ultimos_5[-1]
            
            # Se está em queda contínua E a queda total é significativa
            if is_declining and queda_total >= SLOW_FADING_THRESHOLD:
                return "Slow Fading / Shadowing"
        
        # TESTE 3: Multipath Fading - Oscilações repetitivas
        # Conta quantas vezes o sinal oscilou significativamente
        # Ex: [-50, -55, -51, -56, -52] = 4 oscilações
        oscilacoes = sum(
            1 for i in range(len(ultimos_5)-1)
            if abs(ultimos_5[i] - ultimos_5[i+1]) >= MULTIPATH_OSCILLATION_THRESHOLD
        )
        
        # Se houve 3 ou mais oscilações, é Multipath Fading
        if oscilacoes >= MULTIPATH_OSCILLATION_COUNT:
            return "Multipath Fading"
        
        # TESTE 4: Variação Moderada - Mudança significativa mas não extrema
        # Entre 6 e 9 dBm de variação
        if delta_atual >= MODERATE_VARIATION_THRESHOLD:
            return "Variacao Moderada"
        
        # Nenhum padrão de fading detectado
        return None


# ============================================================================
# CLASSE: ANALISADOR COM IA
# ============================================================================

class AIAnalyzer:
    """Gerencia análise de eventos de fading usando IA (Groq LLM)."""
    
    def __init__(self, api_key, model):
        """
        Inicializa o analisador de IA.
        
        Args:
            api_key: Chave da API Groq
            model: Nome do modelo de IA a usar
        """
        self.api_key = api_key
        self.model = model
       
        self.client = Groq(api_key=api_key) if api_key else None
    
    def analyze_fading(self, contexto_rssi, evento, canal, frequencia):
        """
        Gera análise de IA para um evento de fading.
        
        Funcionamento:
        1. Monta prompt com dados do evento
        2. Envia para API Groq
        3. Retorna análise técnica gerada
        
        Args:
            contexto_rssi: Lista com valores recentes de RSSI
            evento: Tipo de evento de fading detectado
            canal: Número do canal Wi-Fi
            frequencia: Banda de frequência Wi-Fi
            
        Retorna:
            str: Relatório de análise gerado pela IA
        """
        if not self.client:
            return "Erro: API Key ausente."
        
        # Define foco da análise 
        evento_foco = evento if evento else "Analise de Tendencia"
        
        # Monta prompt estruturado para a IA
        prompt = f"""
Atue como um Engenheiro de Telecomunicacoes especialista em Camada Fisica do modelo OSI.

DADOS COLETADOS:
- Sequencia de RSSI (dBm): {contexto_rssi}
- Canal Wi-Fi: {canal if canal else 'Nao disponivel'}
- Frequencia: {frequencia if frequencia else 'Nao disponivel'}
- Evento Detectado: {evento_foco}

ANALISE SOLICITADA:
1. Descreva o comportamento do sinal (estavel, oscilando, queda, subida).
2. Explique o fenomeno fisico provavel:
   - Multipercurso (reflexoes)
   - Shadowing (obstaculos)
   - Interferencia
   - Movimento de pessoas/objetos
3. Relacione com conceitos da camada fisica do modelo OSI.
4. Sugira acoes de mitigacao (ex: mudar canal, reposicionar antena, trocar banda).

Seja tecnico mas direto. Use no maximo 5 paragrafos curtos.
"""
        
        try:
            # Envia requisição para API Groq
            chat_completion = self.client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=self.model,
                temperature=0.6 
            )
            # Retorna conteúdo da resposta
            return chat_completion.choices[0].message.content
        except Exception as e:
            return f"Erro na IA: {e}"


# ============================================================================
# FUNÇÕES DE INICIALIZAÇÃO E INTERFACE
# ============================================================================

def initialize_session_state():
    """
    Inicializa variáveis de estado da sessão Streamlit.
    
    Session state mantém dados entre reruns do Streamlit.
    Funciona como variáveis globais persistentes.
    """
    # DataFrame para armazenar todos os dados coletados
    if 'data' not in st.session_state:
        st.session_state.data = pd.DataFrame(
            columns=['timestamp', 'rssi', 'canal', 'frequencia', 'evento']
        )
    
    # Flag indicando se monitoramento está ativo
    if 'monitoring' not in st.session_state:
        st.session_state.monitoring = False
    
    # Último relatório gerado pela IA
    if 'ultimo_relatorio' not in st.session_state:
        st.session_state.ultimo_relatorio = ""
    
    # Intervalo entre coletas em segundos
    if 'intervalo_coleta' not in st.session_state:
        st.session_state.intervalo_coleta = 0.5


def render_sidebar():
    """Renderiza barra lateral com controles e configurações."""
    with st.sidebar:
        st.header("Painel de Controle")
        
        # Botão para iniciar/pausar monitoramento
        if st.button('Iniciar / Pausar Monitoramento', type="primary", use_container_width=True):
            st.session_state.monitoring = not st.session_state.monitoring
        
        # Indicador visual de status
        status = "Coletando Dados" if st.session_state.monitoring else "Parado"
        status_color = "🟢" if st.session_state.monitoring else "🔴"
        st.markdown(f"**Status:** {status_color} {status}")
        
        st.divider()
        
        # Seção de configurações
        st.subheader("Configuracoes")
        
        # Slider para ajustar intervalo de coleta
        st.session_state.intervalo_coleta = st.slider(
            "Intervalo de Coleta (segundos)",
            min_value=0.1,
            max_value=2.0,
            value=0.5,
            step=0.1
        )
        
        st.divider()
        
        # Botão para limpar todos os dados coletados
        if st.button("Limpar Todos os Dados", use_container_width=True):
            # Reinicia DataFrame e relatório
            st.session_state.data = pd.DataFrame(
                columns=['timestamp', 'rssi', 'canal', 'frequencia', 'evento']
            )
            st.session_state.ultimo_relatorio = ""
            st.rerun()  # Recarrega a página
        
        # Botão de exportação 
        if not st.session_state.data.empty:
            st.divider()
            # Converte DataFrame para CSV
            csv = st.session_state.data.to_csv(index=False)
            # Botão de download
            st.download_button(
                label="Exportar Dados (CSV)",
                data=csv,
                file_name=f"fading_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
                use_container_width=True
            )


def render_realtime_chart():
    """Renderiza gráfico de RSSI em tempo real e visualizações adicionais."""
    st.subheader("Monitoramento em Tempo Real")
    
    if not st.session_state.data.empty:
        # ====================================================================
        # GRÁFICO PRINCIPAL: RSSI EM TEMPO REAL
        # ====================================================================
        
        fig = go.Figure()
        
        # Cria cópia do DataFrame e adiciona índice numérico para eixo X
        df = st.session_state.data.copy()
        df['timestamp_num'] = range(len(df))
        
        # Adiciona linha principal do RSSI
        fig.add_trace(go.Scatter(
            x=df['timestamp_num'],
            y=df['rssi'],
            mode='lines+markers', 
            name='RSSI',
            line=dict(color='#1f77b4', width=2),
            marker=dict(size=4)
        ))
        
        # Destaca eventos de fading com marcadores vermelhos
        eventos_df = df[df['evento'].notna()]  
        if not eventos_df.empty:
            fig.add_trace(go.Scatter(
                x=eventos_df['timestamp_num'],
                y=eventos_df['rssi'],
                mode='markers',
                name='Eventos de Fading',
                marker=dict(size=10, color='red', symbol='x') 
            ))
        
        # Configurações do layout do gráfico
        fig.update_layout(
            xaxis_title="Tempo",
            yaxis_title="RSSI (dBm)",
            height=400,
            hovermode='x unified',  
            showlegend=True,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        
        st.plotly_chart(fig, use_container_width=True)
        
        # ====================================================================
        # MÉTRICAS PRINCIPAIS
        # ====================================================================
        
        col1, col2, col3, col4, col5, col6 = st.columns(6)
        
        # Calcula métricas
        atual = st.session_state.data.iloc[-1]['rssi']  # Última amostra
        media = st.session_state.data['rssi'].mean()    # Média de todas
        eventos_count = st.session_state.data['evento'].notna().sum()  # Total de eventos
        canal = st.session_state.data.iloc[-1]['canal']
        frequencia = st.session_state.data.iloc[-1]['frequencia']        
        # Exibe métricas em cards
        col1.metric("Sinal Atual", f"{atual:.1f} dBm")
        col2.metric("Media", f"{media:.1f} dBm")
        col3.metric("Canal", f"{canal if pd.notna(canal) else 'N/A'}")
        col5.metric("Frequencia", f"{frequencia if pd.notna(frequencia) else 'N/A'}")
        col6.metric("Eventos", eventos_count)
        
        st.divider()
        
        # ====================================================================
        # GRÁFICOS ADICIONAIS 
        # ====================================================================
        
        col_left, col_right = st.columns(2)
        
        # GRÁFICO ESQUERDO: Estabilidade do Sinal
        with col_left:
            st.subheader("Estabilidade do Sinal")
            if len(st.session_state.data) > 10:
                # Mostra como a estabilidade varia ao longo do tempo
                df_stability = st.session_state.data.copy()
                df_stability['rolling_std'] = df_stability['rssi'].rolling(window=10, min_periods=1).std()
                df_stability['timestamp_num'] = range(len(df_stability))
                
                fig_stability = go.Figure()
                fig_stability.add_trace(go.Scatter(
                    x=df_stability['timestamp_num'],
                    y=df_stability['rolling_std'],
                    mode='lines',
                    name='Desvio Padrao Movel',
                    line=dict(color='#ff7f0e', width=2),
                    fill='tozeroy', 
                    fillcolor='rgba(255, 127, 14, 0.2)'
                ))
                
                fig_stability.update_layout(
                    xaxis_title="Tempo",
                    yaxis_title="Desvio Padrao (dBm)",
                    height=300,
                    showlegend=False
                )
                
                st.plotly_chart(fig_stability, use_container_width=True)
                st.caption("Quanto maior o desvio, mais instavel esta o sinal")
            else:
                st.info("Coletando dados... (minimo 10 amostras)")
        
        # GRÁFICO DIREITO: Distribuição de Qualidade
        with col_right:
            st.subheader("Distribuicao de Qualidade")
            if len(st.session_state.data) > 5:
                df_quality = st.session_state.data.copy()
                
                # Função para categorizar RSSI em níveis de qualidade
                def categorize_rssi(rssi):
                    if rssi >= -50:
                        return "Excelente" 
                    elif rssi >= -60:
                        return "Bom"      
                    elif rssi >= -70:
                        return "Regular"   
                    else:
                        return "Fraco"    
                
                # Aplica categorização e conta ocorrências
                df_quality['qualidade'] = df_quality['rssi'].apply(categorize_rssi)
                quality_counts = df_quality['qualidade'].value_counts()
                
                # Cria gráfico de pizza 
                fig_quality = go.Figure(data=[go.Pie(
                    labels=quality_counts.index,
                    values=quality_counts.values,
                    hole=0.4,  
                    marker=dict(colors=['#2ecc71', '#3498db', '#f39c12', '#e74c3c'])
                )])
                
                fig_quality.update_layout(
                    height=300,
                    showlegend=True,
                    legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5)
                )
                
                st.plotly_chart(fig_quality, use_container_width=True)
                st.caption("Distribuicao percentual da qualidade do sinal")
            else:
                st.info("Coletando dados... (minimo 5 amostras)")
        
        # ====================================================================
        # LINHA DO TEMPO DE EVENTOS
        # ====================================================================
        
        if eventos_count > 0:
            st.divider()
            st.subheader("Linha do Tempo de Eventos")
            
            eventos_df = st.session_state.data[st.session_state.data['evento'].notna()].copy()
            eventos_df['timestamp_num'] = range(len(eventos_df))
            
            # Mapeia cada tipo de evento para uma cor
            event_colors = {
                'Fast Fading': '#e74c3c',               # Vermelho
                'Slow Fading / Shadowing': '#f39c12',   # Laranja
                'Multipath Fading': '#9b59b6',          # Roxo
                'Variacao Moderada': '#3498db'          # Azul
            }
            
            eventos_df['color'] = eventos_df['evento'].map(event_colors)
            
            fig_timeline = go.Figure()
            
            # Adiciona uma série para cada tipo de evento
            for evento_tipo in eventos_df['evento'].unique():
                df_evento = eventos_df[eventos_df['evento'] == evento_tipo]
                fig_timeline.add_trace(go.Scatter(
                    x=df_evento.index,
                    y=[evento_tipo] * len(df_evento),
                    mode='markers',
                    name=evento_tipo,
                    marker=dict(size=12, color=event_colors.get(evento_tipo, '#95a5a6'))
                ))
            
            fig_timeline.update_layout(
                xaxis_title="Amostra",
                yaxis_title="Tipo de Evento",
                height=250,
                showlegend=True,
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            
            st.plotly_chart(fig_timeline, use_container_width=True)
            st.caption("Distribuicao temporal dos eventos detectados")
    else:
        st.info("Clique em 'Iniciar / Pausar Monitoramento' no menu lateral para comecar.")


def render_event_history():
    """Renderiza lista histórica de eventos com opção de análise individual."""
    st.subheader("Historico de Eventos")
    
    # Filtra apenas linhas que têm eventos detectados
    eventos_detectados = st.session_state.data[st.session_state.data['evento'].notna()]
    
    if not eventos_detectados.empty:
        st.caption("Clique em 'Analisar' para gerar um relatorio de IA especifico para aquele evento")
        st.divider()
        
        # Pega últimos 15 eventos e inverte ordem 
        eventos_recentes = eventos_detectados.tail(15).iloc[::-1]
        
        for idx, row in eventos_recentes.iterrows():
            # Container para cada evento
            with st.container():
                col1, col2, col3, col4, col5 = st.columns([2, 2, 2, 2, 1])
                
                with col1:
                    st.text(f"{row['timestamp']}")
                
                with col2:
                 
                    st.text(f"{row['evento']}")
                
                with col3:
                    st.text(f"RSSI: {row['rssi']:.1f} dBm")
                
                with col4:
                    canal_info = f"Canal {row['canal']}" if pd.notna(row['canal']) else "N/A"
                    st.text(f"{canal_info} | {row['frequencia']}")
                
                with col5:
                    # Botão para analisar evento específico
                  
                    if st.button("Analisar", key=f"analyze_{idx}", type="secondary", use_container_width=True):
                        analyze_specific_event(idx, row)
                
                st.divider()
    else:
        st.info("Nenhum evento detectado ainda.")


def analyze_specific_event(event_idx, event_row):
    """
    Analisa um evento específico enviando dados detalhados para a IA.
    
    Funcionamento:
    1. Busca contexto (5 amostras antes e depois do evento)
    2. Calcula taxa de variação em dBm/s
    3. Monta dados estruturados do evento
    4. Cria prompt específico para a IA
    5. Gera e exibe relatório detalhado
    
    Args:
        event_idx: Índice do evento no DataFrame
        event_row: Linha do DataFrame contendo os dados do evento
    """
    with st.spinner(f"Analisando evento {event_row['evento']}..."):
        # Busca contexto: 5 amostras antes e 5 depois do evento
        start_idx = max(0, event_idx - 5)
        end_idx = min(len(st.session_state.data), event_idx + 6)
        
        contexto_df = st.session_state.data.iloc[start_idx:end_idx]
        contexto_rssi = contexto_df['rssi'].tolist()
        
        # Calcula taxa de variação (dBm/s)
        # Mostra quão rápido o sinal mudou
        if event_idx > 0:
            rssi_anterior = st.session_state.data.iloc[event_idx - 1]['rssi']
            variacao = abs(event_row['rssi'] - rssi_anterior)
            # Divide pelo intervalo de coleta para obter taxa por segundo
            taxa_variacao = variacao / st.session_state.intervalo_coleta
        else:
            taxa_variacao = 0
        
        evento_data = {
            "rssi_sequence": contexto_rssi,
            "rssi_evento": event_row['rssi'],
            "timestamp": event_row['timestamp'],
            "canal": event_row['canal'] if pd.notna(event_row['canal']) else "N/A",
            "frequencia": event_row['frequencia'] if pd.notna(event_row['frequencia']) else "N/A",
            "tipo_evento": event_row['evento'],
            "taxa_variacao": f"{taxa_variacao:.1f} dBm/s"
        }
        
        # Cria prompt específico para análise deste evento
        prompt = f"""
Atue como um Engenheiro de Telecomunicacoes especialista em Camada Fisica do modelo OSI.

EVENTO ESPECIFICO DETECTADO:
- Tipo: {evento_data['tipo_evento']}
- Horario: {evento_data['timestamp']}
- RSSI no momento: {evento_data['rssi_evento']:.1f} dBm
- Taxa de variacao: {evento_data['taxa_variacao']}
- Canal Wi-Fi: {evento_data['canal']}
- Frequencia: {evento_data['frequencia']}

CONTEXTO (sequencia de RSSI antes e depois):
{evento_data['rssi_sequence']}

ANALISE SOLICITADA:
1. Analise especificamente este evento de {evento_data['tipo_evento']}.
2. Explique por que este tipo de fading ocorreu neste momento especifico.
3. Considerando a taxa de variacao de {evento_data['taxa_variacao']}, qual a severidade?
4. Relacione com fenomenos fisicos da camada OSI (multipercurso, shadowing, interferencia).
5. Sugira acoes corretivas especificas para este tipo de problema.

Seja tecnico e direto. Use no maximo 5 paragrafos curtos.
"""
        
        # Envia para a IA e processa resposta
        analyzer = AIAnalyzer(GROQ_API_KEY, MODELO_AI)
        
        try:
            chat_completion = analyzer.client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=analyzer.model,
                temperature=0.6
            )
            relatorio = chat_completion.choices[0].message.content
            
            st.session_state.ultimo_relatorio = relatorio
            st.success(f"Relatorio gerado para evento: {evento_data['tipo_evento']}")
            st.toast("Relatorio disponivel na aba Analise", icon="✅")
            
            st.markdown("### Relatorio do Evento")
            st.markdown(relatorio)
            
        except Exception as e:
            st.error(f"Erro ao gerar relatorio: {e}")


def render_ai_analysis():
    """Renderiza seção de análise com IA."""
    st.subheader("Relatorio com IA")
    
    col_btn, col_info = st.columns([1, 3])
    
    with col_btn:
        tem_dados = not st.session_state.data.empty
        # Botão para gerar relatório 
        if st.button("Relatorio", disabled=not tem_dados, type="secondary"):
            with st.spinner("Gerando relatorio..."):
                # Pega últimas 40 amostras para contexto amplo
                dados_recentes = st.session_state.data['rssi'].tail(40).tolist()
                eventos_recentes = st.session_state.data['evento'].tail(40).dropna()
                ultimo_evento = eventos_recentes.iloc[-1] if not eventos_recentes.empty else None
                
                # Pega canal e frequência mais recentes
                canal = st.session_state.data.iloc[-1]['canal'] if not st.session_state.data.empty else None
                frequencia = st.session_state.data.iloc[-1]['frequencia'] if not st.session_state.data.empty else None
                
                # Gera relatório geral
                analyzer = AIAnalyzer(GROQ_API_KEY, MODELO_AI)
                relatorio = analyzer.analyze_fading(dados_recentes, ultimo_evento, canal, frequencia)
                st.session_state.ultimo_relatorio = relatorio
                st.rerun()
    
    with col_info:
        if st.session_state.ultimo_relatorio:
            st.success("Relatorio Atualizado")
            st.markdown(st.session_state.ultimo_relatorio)
        else:
            st.caption("O relatorio aparecera aqui automaticamente ao detectar eventos ou via botao manual.")


def collect_and_process_data():
    """
    Loop principal de coleta e processamento de dados.
    
    Funcionamento:
    1. Verifica se monitoramento está ativo
    2. Coleta dados Wi-Fi do sistema
    3. Detecta eventos de fading
    4. Armazena dados no DataFrame
    5. Gera relatório automático se evento for detectado
    6. Aguarda intervalo configurado e reinicia
    """
    if st.session_state.monitoring:
        # Coleta dados Wi-Fi
        collector = WiFiDataCollector()
        wifi_info = collector.get_wifi_info()
        
        if wifi_info and wifi_info['rssi'] is not None:
            # Gera timestamp atual
            ts = datetime.now().strftime("%H:%M:%S")
            
            # Detecta fading usando histórico
            detector = FadingDetector()
            evento = detector.detect_fading(wifi_info['rssi'], st.session_state.data)
            
            # Cria novo ponto de dados
            novo_df = pd.DataFrame({
                'timestamp': [ts],
                'rssi': [wifi_info['rssi']],
                'canal': [wifi_info['canal']],
                'frequencia': [wifi_info['frequencia']],
                'evento': [evento]
            })
            
            # Adiciona ao DataFrame principal
            st.session_state.data = pd.concat(
                [st.session_state.data, novo_df],
                ignore_index=True
            )
            
            # Se evento foi detectado, gera relatório automático
            if evento:
                st.toast(f"Evento detectado: {evento}", icon="⚠️")
                
                # Pega contexto para IA 
                dados_para_ia = st.session_state.data['rssi'].tail(40).tolist()
                analyzer = AIAnalyzer(GROQ_API_KEY, MODELO_AI)
                relatorio_auto = analyzer.analyze_fading(
                    dados_para_ia,
                    evento,
                    wifi_info['canal'],
                    wifi_info['frequencia']
                )
                
                st.session_state.ultimo_relatorio = relatorio_auto
                st.toast("Relatorio Automatico Gerado", icon="📝")
        
        # Aguarda intervalo configurado antes da próxima coleta
        time.sleep(st.session_state.intervalo_coleta)
        st.rerun() 


def main():
    """Ponto de entrada principal da aplicação."""
    st.title("Sistema de Monitoramento de Fading Wi-Fi")
    st.caption("Analise de Camada Fisica - Deteccao e Classificacao de Fading em Tempo Real")
    
    # Inicializa estado da sessão
    initialize_session_state()
    
    # Renderiza barra lateral
    render_sidebar()
    
    # Cria abas principais da interface
    tab1, tab2, tab3 = st.tabs(["Monitoramento", "Analise", "Eventos"])
    
    # Aba 1: Monitoramento em tempo real
    with tab1:
        render_realtime_chart()
    
    # Aba 2: Análise com IA
    with tab2:
        render_ai_analysis()
    
    # Aba 3: Histórico de eventos
    with tab3:
        render_event_history()
    
    # Loop de coleta de dados 
    collect_and_process_data()


# Ponto de entrada do script
if __name__ == "__main__":
    main()