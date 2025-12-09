import streamlit as st
import pandas as pd
import numpy as np
import time
import subprocess
import re
from datetime import datetime

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Detector de Fading Wi-Fi", layout="wide")
st.title("📡 Analisador de Fading Wi-Fi com IA")

# --- FUNÇÕES DE COLETA DE DADOS ---

def get_wifi_signal_windows():
    """
    Coleta o sinal Wi-Fi real no Windows usando comando netsh.
    Retorna RSSI em dBm (estimado) e qualidade %.
    """
    try:
        # Executa o comando do Windows para ver interfaces
        cmd_output = subprocess.check_output("netsh wlan show interfaces", shell=True).decode('utf-8', errors='ignore')
        
        # Procura a linha "Sinal" ou "Signal"
        match = re.search(r"Sinal\s*:\s*(\d+)%", cmd_output)
        if not match:
             match = re.search(r"Signal\s*:\s*(\d+)%", cmd_output)
        
        if match:
            quality = int(match.group(1))
            # Conversão aproximada de Qualidade(%) para dBm
            # Fórmula comum: (Qualidade / 2) - 100
            rssi = (quality / 2) - 100
            return rssi, quality
        else:
            return -100, 0
    except Exception as e:
        return -100, 0

def get_wifi_signal_simulated():
    """
    Simula um sinal Wi-Fi com Fading para testes.
    Gera quedas bruscas aleatórias para simular obstáculos.
    """
    base_signal = -50 # Sinal forte
    noise = np.random.normal(0, 2) # Pequena variação natural
    
    # Simula um evento de Fading (queda brusca) aleatoriamente
    fading_effect = 0
    if np.random.rand() > 0.90: # 10% de chance de fading
        fading_effect = np.random.randint(10, 25) * -1 # Queda de 10 a 25 dBm
    
    return base_signal + noise + fading_effect, 100

# --- FUNÇÃO DA IA (MOCK - Para não gastar API agora) ---
def ask_ai_explanation(event_data):
    """
    Simula a resposta da IA baseada no documento do trabalho.
    Para usar IA real, substitua por chamada à API da OpenAI/Gemini.
    """
    rssi_drop = abs(event_data['variacao'])
    
    # Lógica simples para simular a resposta da IA baseada nas regras do Doc
    if rssi_drop > 15:
        return f"🤖 **Análise da IA:** A queda de {rssi_drop:.1f} dBm foi muito brusca! \n\nIsso indica **Shadow Fading** severo ou bloqueio total da linha de visada (LOS), possivelmente causado por uma parede grossa de concreto ou porta de metal fechada repentinamente."
    elif rssi_drop > 8:
        return f"🤖 **Análise da IA:** Variação de {rssi_drop:.1f} dBm detectada. \n\nIsso tem características de **Fast Fading**. Provavelmente causado por **multipercurso** (reflexões do sinal) devido a pessoas se movendo no ambiente ou objetos próximos à antena."
    else:
        return "🤖 **Análise da IA:** Variação leve. Pode ser apenas ruído natural do ambiente ou interferência co-canal."

# --- INTERFACE E LÓGICA PRINCIPAL ---

# Sidebar de Controles
st.sidebar.header("Configurações")
mode = st.sidebar.radio("Modo de Coleta", ["Simulação (Teste)", "Tempo Real (Windows)"])
threshold = st.sidebar.slider("Sensibilidade de Fading (dBm)", 5, 20, 10)
run = st.sidebar.checkbox("Iniciar Coleta", value=False)

# Estado da sessão para guardar dados
if 'history' not in st.session_state:
    st.session_state.history = []
if 'events' not in st.session_state:
    st.session_state.events = []

# Layout do Dashboard
col1, col2 = st.columns([3, 1])
placeholder_chart = col1.empty()
placeholder_metrics = col2.empty()
st.divider()
st.subheader("📝 Registro de Eventos de Fading")
placeholder_events = st.empty()

if run:
    # 1. Coletar Dado
    if mode == "Simulação (Teste)":
        rssi, quality = get_wifi_signal_simulated()
    else:
        rssi, quality = get_wifi_signal_windows()
        
    timestamp = datetime.now().strftime("%H:%M:%S")
    
    # 2. Guardar no histórico
    st.session_state.history.append({"time": timestamp, "rssi": rssi})
    # Manter apenas últimos 50 pontos no gráfico
    if len(st.session_state.history) > 50:
        st.session_state.history.pop(0)
    
    df = pd.DataFrame(st.session_state.history)

    # 3. Detectar Fading (Lógica descrita no documento)
    # Compara o valor atual com o anterior
    if len(st.session_state.history) > 1:
        prev_rssi = st.session_state.history[-2]['rssi']
        diff = rssi - prev_rssi
        
        # Se a queda for maior que a sensibilidade (ex: caiu 10db)
        if abs(diff) >= threshold and diff < 0:
            event = {
                "Horário": timestamp,
                "RSSI Anterior": f"{prev_rssi:.1f}",
                "RSSI Atual": f"{rssi:.1f}",
                "Variação": diff,
                "Tipo": "Queda Brusca"
            }
            st.session_state.events.insert(0, event) # Adiciona no topo

    # 4. Atualizar Gráfico e Métricas
    with placeholder_chart:
        st.line_chart(df.set_index("time")['rssi'])
    
    with placeholder_metrics:
        st.metric(label="RSSI Atual", value=f"{rssi:.1f} dBm", delta=f"{rssi - (st.session_state.history[-2]['rssi'] if len(st.session_state.history) > 1 else rssi):.1f} dBm")
        st.metric(label="Eventos Detectados", value=len(st.session_state.events))

    # 5. Loop de atualização
    time.sleep(0.5) # Atualiza a cada 0.5 segundos (2Hz)
    st.rerun()

# Exibição dos eventos e Botão da IA
if st.session_state.events:
    for i, event in enumerate(st.session_state.events[:5]): # Mostra os 5 últimos
        with st.expander(f"⚠️ {event['Horário']} | Variação: {event['Variação']:.1f} dBm"):
            st.write(f"**Detalhes:** O sinal caiu de {event['RSSI Anterior']} para {event['RSSI Atual']} dBm.")
            
            # Botão para chamar a "IA"
            if st.button(f"🧠 Explicar Evento {event['Horário']}", key=f"btn_{i}"):
                explanation = ask_ai_explanation({"variacao": abs(event['Variação'])})
                st.info(explanation)

else:
    placeholder_events.info("Nenhum evento de fading detectado ainda. Inicie a coleta.")