import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import warnings
import sys
import os
import time
import random
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

warnings.filterwarnings('ignore')

# Configurazione della pagina Streamlit - DEVE ESSERE LA PRIMA COMANDA STREAMLIT
st.set_page_config(
    page_title="Bensdorp Trading Strategies",
    page_icon="📈",
    layout="wide"
)

# Verifica versione Python
st.sidebar.info(f"🐍 Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")

# Funzioni di utilità per indicatori tecnici (fallback)
def calculate_sma(data, length):
    """Calcola Simple Moving Average manualmente"""
    return data.rolling(window=length).mean()

def calculate_rsi(data, length=14):
    """Calcola RSI manualmente"""
    delta = data.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=length).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=length).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calculate_adx(high, low, close, length=14):
    """Calcolo semplificato ADX"""
    df = pd.DataFrame({'high': high, 'low': low, 'close': close})
    
    # True Range
    df['tr'] = np.maximum(
        df['high'] - df['low'],
        np.maximum(
            abs(df['high'] - df['close'].shift()),
            abs(df['low'] - df['close'].shift())
        )
    )
    df['atr'] = df['tr'].rolling(window=length).mean()
    
    # Directional Movement
    df['up_move'] = df['high'] - df['high'].shift()
    df['down_move'] = df['low'].shift() - df['low']
    
    df['plus_dm'] = np.where((df['up_move'] > df['down_move']) & (df['up_move'] > 0), df['up_move'], 0)
    df['minus_dm'] = np.where((df['down_move'] > df['up_move']) & (df['down_move'] > 0), df['down_move'], 0)
    
    df['plus_di'] = 100 * (df['plus_dm'].rolling(window=length).mean() / df['atr'])
    df['minus_di'] = 100 * (df['minus_dm'].rolling(window=length).mean() / df['atr'])
    
    # ADX
    df['dx'] = 100 * abs(df['plus_di'] - df['minus_di']) / (df['plus_di'] + df['minus_di'])
    df['adx'] = df['dx'].rolling(window=length).mean()
    
    return df['adx']

def calculate_bbands(data, length=20, std=2):
    """Calcola Bollinger Bands manualmente"""
    sma = data.rolling(window=length).mean()
    std_dev = data.rolling(window=length).std()
    upper = sma + (std_dev * std)
    lower = sma - (std_dev * std)
    return upper, sma, lower

# Tentativo di importare pandas_ta con fallback
try:
    import pandas_ta as ta
    TA_AVAILABLE = True
    st.sidebar.success("✅ pandas_ta disponibile")
except ImportError:
    TA_AVAILABLE = False
    st.sidebar.warning("⚠️ pandas_ta non disponibile - uso funzioni manuali")

# Titolo e descrizione
st.title("📊 Laurens Bensdorp - Sistemi di Trading Automatici")
st.markdown("""
Implementazione delle 7 strategie di trading descritte nel libro 
*"Automated Stock Trading Systems"* con visualizzazione interattiva.
""")

# Sidebar per i parametri comuni
with st.sidebar:
    st.header("⚙️ Parametri Generali")
    
    # Selezione del titolo
    ticker = st.text_input("Simbolo Titolo", value="AAPL").upper()
    
    # Date di backtest
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input(
            "Data Inizio",
            value=datetime.now() - timedelta(days=365)
        )
    with col2:
        end_date = st.date_input(
            "Data Fine",
            value=datetime.now()
        )
    
    # Parametri di trading
    st.subheader("💰 Gestione del Rischio")
    budget = st.number_input("Capitale Iniziale ($)", value=10000, step=1000)
    risk_percentage = st.slider("Rischio per Operazione (%)", 0.5, 5.0, 2.0) / 100
    
    # Filtri comuni 
    st.subheader("🔍 Filtri di Liquidità")
    min_price = st.number_input("Prezzo Minimo ($)", value=5.0, step=1.0)
    min_volume = st.number_input("Volume Minimo (azioni)", value=500000, step=100000)
    
    # Selezione della strategia
    st.subheader("📋 Selezione Strategia")
    strategy = st.selectbox(
        "Scegli la strategia da analizzare",
        [
            "1. Long Trend High Momentum",
            "2. Short RSI Thrust", 
            "3. Long Mean Reversion Selloff",
            "4. Long Trend Low Volatility",
            "5. Long Mean Reversion High ADX Reversal",
            "6. Short Mean Reversion High Six-Day Surge",
            "7. Catastrophe Hedge",
            "Tutte le Strategie (Portafoglio)"
        ]
    )

# Funzioni di utilità
@st.cache_data(ttl=3600)  # Cache per 1 ora
def load_data(ticker, start, end):
    """Carica i dati da Yahoo Finance con strategie anti-blocco"""
    try:
        # Crea una sessione con retry logic
        session = requests.Session()
        
        # Configura i retry per gestire errori temporanei
        retry = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504]
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        
        # Imposta headers per sembrare un browser reale
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
        })
        
        # Mostra tentativo di connessione
        with st.spinner(f"Tentativo di caricare {ticker}..."):
            # Aggiungi un piccolo ritardo casuale per evitare pattern
            time.sleep(random.uniform(1, 3))
            
            # Usa yfinance con la sessione configurata
            stock = yf.Ticker(ticker, session=session)
            data = stock.history(start=start, end=end)
            
            if data.empty:
                st.warning(f"Nessun dato trovato per {ticker} con metodo standard. Provo metodo alternativo...")
                # Prova un metodo alternativo
                data = yf.download(ticker, start=start, end=end, progress=False, session=session)
        
        if data.empty:
            st.error(f"Impossibile recuperare dati per {ticker} dopo vari tentativi.")
            return None
        
        # Aggiungi indicatori tecnici di base
        if TA_AVAILABLE:
            # Usa pandas_ta se disponibile
            data['SMA_20'] = ta.sma(data['Close'], length=20)
            data['SMA_50'] = ta.sma(data['Close'], length=50)
            data['SMA_200'] = ta.sma(data['Close'], length=200)
            data['RSI'] = ta.rsi(data['Close'], length=14)
            data['Volume_SMA'] = ta.sma(data['Volume'], length=20)
            
            # Calcola ADX
            adx_df = ta.adx(data['High'], data['Low'], data['Close'], length=14)
            data['ADX'] = adx_df['ADX_14']
            
            # Calcola Bollinger Bands
            bb_df = ta.bbands(data['Close'], length=20, std=2)
            if bb_df is not None and len(bb_df.columns) >= 3:
                data['BB_upper'] = bb_df.iloc[:, 0]
                data['BB_middle'] = bb_df.iloc[:, 1]
                data['BB_lower'] = bb_df.iloc[:, 2]
        else:
            # Usa funzioni manuali
            data['SMA_20'] = calculate_sma(data['Close'], 20)
            data['SMA_50'] = calculate_sma(data['Close'], 50)
            data['SMA_200'] = calculate_sma(data['Close'], 200)
            data['RSI'] = calculate_rsi(data['Close'], 14)
            data['Volume_SMA'] = calculate_sma(data['Volume'], 20)
            data['ADX'] = calculate_adx(data['High'], data['Low'], data['Close'], 14)
            
            # Bollinger Bands manuali
            upper, middle, lower = calculate_bbands(data['Close'], 20, 2)
            data['BB_upper'] = upper
            data['BB_middle'] = middle
            data['BB_lower'] = lower
        
        # Calcola volatilità (sempre con pandas)
        data['Volatility'] = data['Close'].pct_change().rolling(20).std() * np.sqrt(252)
        
        # Pulisci NaN
        data = data.fillna(method='bfill').fillna(method='ffill')
        
        st.success(f"✅ Dati caricati con successo per {ticker}")
        return data
        
    except Exception as e:
        st.error(f"Errore nel caricamento dei dati: {e}")
        return None

def apply_filters(data, min_price, min_volume):
    """Applica i filtri comuni a tutte le strategie"""
    if data is None or data.empty:
        return False, ["❌ Dati non disponibili"]
    
    latest = data.iloc[-1]
    filters_passed = True
    filter_messages = []
    
    # Filtro prezzo minimo
    if latest['Close'] < min_price:
        filters_passed = False
        filter_messages.append(f"❌ Prezzo ${latest['Close']:.2f} < ${min_price}")
    else:
        filter_messages.append(f"✅ Prezzo ${latest['Close']:.2f} ≥ ${min_price}")
    
    # Filtro volume
    if latest['Volume'] < min_volume:
        filters_passed = False
        filter_messages.append(f"❌ Volume {latest['Volume']:,.0f} < {min_volume:,.0f}")
    else:
        filter_messages.append(f"✅ Volume {latest['Volume']:,.0f} ≥ {min_volume:,.0f}")
    
    return filters_passed, filter_messages

def calculate_position_size(price, budget, risk_percentage, stop_loss_pct):
    """Calcola la dimensione della posizione basata sul rischio"""
    if price <= 0 or stop_loss_pct <= 0:
        return 0
    risk_amount = budget * risk_percentage
    stop_loss_amount = price * stop_loss_pct
    if stop_loss_amount <= 0:
        return 0
    shares = int(risk_amount / stop_loss_amount)
    return max(shares, 1)  # Almeno 1 azione

# Implementazione delle strategie 
def strategy_1_trend_high_momentum(data, budget, risk_percentage):
    """
    Strategia 1: Long Trend High Momentum
    - Trend rialzista: SMA 25 > SMA 50
    - Alto momentum: ranking per ROC 200 giorni
    """
    if data is None or data.empty:
        return pd.DataFrame()
    
    signals = pd.DataFrame(index=data.index)
    signals['Signal'] = 0
    signals['Position'] = 0
    
    # Calcola indicatori
    data_copy = data.copy()
    data_copy['SMA_25'] = calculate_sma(data_copy['Close'], 25)
    data_copy['SMA_50'] = calculate_sma(data_copy['Close'], 50)
    data_copy['ROC_200'] = data_copy['Close'].pct_change(200) * 100
    
    # Condizioni di ingresso
    trend_up = data_copy['SMA_25'] > data_copy['SMA_50']
    momentum_high = data_copy['ROC_200'] > data_copy['ROC_200'].rolling(50).mean()
    
    # Genera segnali
    signals.loc[trend_up & momentum_high, 'Signal'] = 1
    
    # Calcola posizioni
    current_position = 0
    entry_price = 0
    shares = 0
    
    for i in range(1, len(signals)):
        if signals['Signal'].iloc[i] == 1 and current_position == 0:
            current_position = 1
            entry_price = data_copy['Close'].iloc[i]
            shares = calculate_position_size(entry_price, budget, risk_percentage, 0.10)  # Stop loss 10%
            if shares > 0:
                signals.loc[signals.index[i], 'Position'] = shares
        elif current_position == 1:
            # Trailing stop del 15%
            trailing_stop = entry_price * 0.85
            if data_copy['Close'].iloc[i] < trailing_stop:
                current_position = 0
                signals.loc[signals.index[i], 'Position'] = -shares
            else:
                signals.loc[signals.index[i], 'Position'] = shares
    
    return signals

def strategy_2_short_rsi_thrust(data, budget, risk_percentage):
    """
    Strategia 2: Short RSI Thrust
    - Vende quando RSI > 70 (ipercomprato)
    - Copertura per mercati in discesa
    """
    if data is None or data.empty:
        return pd.DataFrame()
    
    signals = pd.DataFrame(index=data.index)
    signals['Signal'] = 0
    signals['Position'] = 0
    
    # RSI > 70 genera segnale di short
    overbought = data['RSI'] > 70
    
    signals.loc[overbought, 'Signal'] = -1  # Segnale short
    
    # Calcola posizioni
    current_position = 0
    shares = 0
    
    for i in range(1, len(signals)):
        if signals['Signal'].iloc[i] == -1 and current_position == 0:
            current_position = -1
            shares = calculate_position_size(data['Close'].iloc[i], budget, risk_percentage, 0.05)
            if shares > 0:
                signals.loc[signals.index[i], 'Position'] = -shares
        elif current_position == -1:
            # Cover quando RSI < 30
            if data['RSI'].iloc[i] < 30:
                current_position = 0
                signals.loc[signals.index[i], 'Position'] = shares
            else:
                signals.loc[signals.index[i], 'Position'] = -shares
    
    return signals

def strategy_3_mean_reversion_selloff(data, budget, risk_percentage):
    """
    Strategia 3: Long Mean Reversion Selloff
    - Compra in uptrend dopo un selloff significativo
    - RSI < 30 (oversold) in trend rialzista
    """
    if data is None or data.empty:
        return pd.DataFrame()
    
    signals = pd.DataFrame(index=data.index)
    signals['Signal'] = 0
    signals['Position'] = 0
    
    # Calcola indicatori
    data_copy = data.copy()
    data_copy['SMA_50'] = calculate_sma(data_copy['Close'], 50)
    
    # Condizioni: uptrend e oversold
    uptrend = data_copy['Close'] > data_copy['SMA_50']
    oversold = data_copy['RSI'] < 30
    below_lower_bb = data_copy['Close'] < data_copy['BB_lower'] if 'BB_lower' in data_copy.columns else pd.Series(False, index=data_copy.index)
    
    # Segnale di acquisto
    buy_signal = uptrend & (oversold | below_lower_bb)
    signals.loc[buy_signal, 'Signal'] = 1
    
    # Calcola posizioni
    current_position = 0
    entry_price = 0
    shares = 0
    
    for i in range(1, len(signals)):
        if signals['Signal'].iloc[i] == 1 and current_position == 0:
            current_position = 1
            entry_price = data_copy['Close'].iloc[i]
            shares = calculate_position_size(entry_price, budget, risk_percentage, 0.07)
            if shares > 0:
                signals.loc[signals.index[i], 'Position'] = shares
        elif current_position == 1:
            # Exit quando torna alla media (BB_middle)
            if 'BB_middle' in data_copy.columns and data_copy['Close'].iloc[i] > data_copy['BB_middle'].iloc[i]:
                current_position = 0
                signals.loc[signals.index[i], 'Position'] = -shares
            else:
                signals.loc[signals.index[i], 'Position'] = shares
    
    return signals

def strategy_4_trend_low_volatility(data, budget, risk_percentage):
    """
    Strategia 4: Long Trend Low Volatility
    - Trend following a bassa volatilità
    - SMA 20 > SMA 50 e volatilità < media
    """
    if data is None or data.empty:
        return pd.DataFrame()
    
    signals = pd.DataFrame(index=data.index)
    signals['Signal'] = 0
    signals['Position'] = 0
    
    # Condizioni
    trend_up = data['SMA_20'] > data['SMA_50']
    low_vol = data['Volatility'] < data['Volatility'].rolling(50).mean()
    
    # Segnale di acquisto
    buy_signal = trend_up & low_vol
    signals.loc[buy_signal, 'Signal'] = 1
    
    # Calcola posizioni
    current_position = 0
    entry_price = 0
    shares = 0
    
    for i in range(1, len(signals)):
        if signals['Signal'].iloc[i] == 1 and current_position == 0:
            current_position = 1
            entry_price = data['Close'].iloc[i]
            shares = calculate_position_size(entry_price, budget, risk_percentage, 0.08)
            if shares > 0:
                signals.loc[signals.index[i], 'Position'] = shares
        elif current_position == 1:
            # Exit quando trend si inverte o volatilità aumenta
            vol_mean = data['Volatility'].rolling(50).mean().iloc[i]
            if data['SMA_20'].iloc[i] < data['SMA_50'].iloc[i] or \
               data['Volatility'].iloc[i] > vol_mean * 1.5:
                current_position = 0
                signals.loc[signals.index[i], 'Position'] = -shares
            else:
                signals.loc[signals.index[i], 'Position'] = shares
    
    return signals

def strategy_5_adx_reversal(data, budget, risk_percentage):
    """
    Strategia 5: Long Mean Reversion High ADX Reversal
    - Forte trend (ADX alto) con pullback
    - ADX > 25 e RSI < 40
    """
    if data is None or data.empty:
        return pd.DataFrame()
    
    signals = pd.DataFrame(index=data.index)
    signals['Signal'] = 0
    signals['Position'] = 0
    
    # Condizioni
    strong_trend = data['ADX'] > 25
    pullback = data['RSI'] < 40
    uptrend = data['Close'] > data['SMA_50']
    
    # Segnale di acquisto
    buy_signal = strong_trend & pullback & uptrend
    signals.loc[buy_signal, 'Signal'] = 1
    
    # Calcola posizioni
    current_position = 0
    entry_price = 0
    shares = 0
    
    for i in range(1, len(signals)):
        if signals['Signal'].iloc[i] == 1 and current_position == 0:
            current_position = 1
            entry_price = data['Close'].iloc[i]
            shares = calculate_position_size(entry_price, budget, risk_percentage, 0.06)
            if shares > 0:
                signals.loc[signals.index[i], 'Position'] = shares
        elif current_position == 1:
            # Exit quando RSI > 60 o ADX scende
            if data['RSI'].iloc[i] > 60 or data['ADX'].iloc[i] < 20:
                current_position = 0
                signals.loc[signals.index[i], 'Position'] = -shares
            else:
                signals.loc[signals.index[i], 'Position'] = shares
    
    return signals

def strategy_6_six_day_surge(data, budget, risk_percentage):
    """
    Strategia 6: Short Mean Reversion High Six-Day Surge
    - Short dopo un forte rally di 6 giorni
    - Aumento > 15% in 6 giorni e RSI > 70
    """
    if data is None or data.empty:
        return pd.DataFrame()
    
    signals = pd.DataFrame(index=data.index)
    signals['Signal'] = 0
    signals['Position'] = 0
    
    # Calcola rally di 6 giorni
    data_copy = data.copy()
    data_copy['6day_return'] = data_copy['Close'].pct_change(6) * 100
    
    # Condizioni per short
    surge = data_copy['6day_return'] > 15
    overbought = data_copy['RSI'] > 70
    
    # Segnale di short
    short_signal = surge & overbought
    signals.loc[short_signal, 'Signal'] = -1
    
    # Calcola posizioni short
    current_position = 0
    shares = 0
    entry_day = 0
    
    for i in range(1, len(signals)):
        if signals['Signal'].iloc[i] == -1 and current_position == 0:
            current_position = -1
            shares = calculate_position_size(data_copy['Close'].iloc[i], budget, risk_percentage, 0.05)
            entry_day = i
            if shares > 0:
                signals.loc[signals.index[i], 'Position'] = -shares
        elif current_position == -1:
            # Cover dopo 5 giorni o se RSI < 40
            if i > entry_day + 5 or data_copy['RSI'].iloc[i] < 40:
                current_position = 0
                signals.loc[signals.index[i], 'Position'] = shares
            else:
                signals.loc[signals.index[i], 'Position'] = -shares
    
    return signals

def strategy_7_catastrophe_hedge(data, budget, risk_percentage):
    """
    Strategia 7: Catastrophe Hedge
    - Protezione da crolli di mercato
    - Entra short quando il mercato mostra forte momentum ribassista
    """
    if data is None or data.empty:
        return pd.DataFrame()
    
    signals = pd.DataFrame(index=data.index)
    signals['Signal'] = 0
    signals['Position'] = 0
    
    # Calcola momentum ribassista
    data_copy = data.copy()
    data_copy['200ma'] = calculate_sma(data_copy['Close'], 200)
    data_copy['Returns_5d'] = data_copy['Close'].pct_change(5) * 100
    data_copy['Returns_20d'] = data_copy['Close'].pct_change(20) * 100
    
    # Condizioni catastrofe
    below_200ma = data_copy['Close'] < data_copy['200ma']
    sharp_decline = data_copy['Returns_5d'] < -10  # -10% in 5 giorni
    momentum_down = data_copy['Returns_20d'] < -15  # -15% in 20 giorni
    
    # Segnale di hedge
    hedge_signal = below_200ma & (sharp_decline | momentum_down)
    signals.loc[hedge_signal, 'Signal'] = -1  # Short per protezione
    
    # Calcola posizioni
    current_position = 0
    shares = 0
    
    for i in range(1, len(signals)):
        if signals['Signal'].iloc[i] == -1 and current_position == 0:
            current_position = -1
            shares = calculate_position_size(data_copy['Close'].iloc[i], budget, risk_percentage * 2, 0.10)
            if shares > 0:
                signals.loc[signals.index[i], 'Position'] = -shares
        elif current_position == -1:
            # Exit quando mercato si stabilizza
            if data_copy['Close'].iloc[i] > data_copy['200ma'].iloc[i] or data_copy['Returns_5d'].iloc[i] > -5:
                current_position = 0
                signals.loc[signals.index[i], 'Position'] = shares
            else:
                signals.loc[signals.index[i], 'Position'] = -shares
    
    return signals

def plot_strategy(data, signals, strategy_name, ticker):
    """Crea grafico interattivo con Plotly"""
    if data is None or data.empty or signals is None or signals.empty:
        return None
    
    fig = make_subplots(
        rows=3, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.05,
        row_heights=[0.5, 0.25, 0.25],
        subplot_titles=(f'{ticker} - Prezzo', 'Volume', 'RSI')
    )
    
    # Grafico prezzi con medie mobili
    fig.add_trace(
        go.Candlestick(
            x=data.index,
            open=data['Open'],
            high=data['High'],
            low=data['Low'],
            close=data['Close'],
            name='Prezzo'
        ),
        row=1, col=1
    )
    
    # Aggiungi medie mobili
    fig.add_trace(
        go.Scatter(x=data.index, y=data['SMA_20'], name='SMA 20', line=dict(color='orange')),
        row=1, col=1
    )
    fig.add_trace(
        go.Scatter(x=data.index, y=data['SMA_50'], name='SMA 50', line=dict(color='blue')),
        row=1, col=1
    )
    
    # Segnali di trading
    buy_signals = data[signals['Signal'] == 1].index
    sell_signals = data[signals['Signal'] == -1].index
    
    if len(buy_signals) > 0:
        fig.add_trace(
            go.Scatter(
                x=buy_signals,
                y=data.loc[buy_signals, 'Low'] * 0.98,
                mode='markers',
                name='Buy Signal',
                marker=dict(symbol='triangle-up', size=15, color='green')
            ),
            row=1, col=1
        )
    
    if len(sell_signals) > 0:
        fig.add_trace(
            go.Scatter(
                x=sell_signals,
                y=data.loc[sell_signals, 'High'] * 1.02,
                mode='markers',
                name='Sell Signal',
                marker=dict(symbol='triangle-down', size=15, color='red')
            ),
            row=1, col=1
        )
    
    # Volume
    colors = ['red' if data['Close'].iloc[i] < data['Open'].iloc[i] else 'green' 
              for i in range(len(data))]
    
    fig.add_trace(
        go.Bar(x=data.index, y=data['Volume'], name='Volume', marker_color=colors),
        row=2, col=1
    )
    
    # RSI
    fig.add_trace(
        go.Scatter(x=data.index, y=data['RSI'], name='RSI', line=dict(color='purple')),
        row=3, col=1
    )
    
    # Linee RSI 30/70
    fig.add_hline(y=70, line_dash="dash", line_color="red", row=3, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color="green", row=3, col=1)
    
    fig.update_layout(
        title=f'{strategy_name} - {ticker}',
        xaxis_title='Data',
        yaxis_title='Prezzo ($)',
        template='plotly_dark',
        height=900,
        showlegend=True
    )
    
    return fig

def calculate_performance(data, signals, budget):
    """Calcola le performance della strategia"""
    if data is None or data.empty or signals is None or signals.empty:
        return None
    
    if 'Position' not in signals.columns:
        return None
    
    # Calcola valore del portafoglio
    portfolio_value = pd.Series(index=data.index, dtype=float)
    portfolio_value.iloc[0] = budget
    cash = budget
    position = 0
    
    for i in range(1, len(data)):
        if signals['Position'].iloc[i] != 0:
            if signals['Position'].iloc[i] > 0:  # Acquisto
                shares = signals['Position'].iloc[i]
                cost = shares * data['Close'].iloc[i]
                if cash >= cost:
                    cash -= cost
                    position += shares
            else:  # Vendita
                shares = -signals['Position'].iloc[i]
                if position >= shares:
                    cash += shares * data['Close'].iloc[i]
                    position -= shares
        
        portfolio_value.iloc[i] = cash + position * data['Close'].iloc[i]
    
    # Calcola metriche
    total_return = (portfolio_value.iloc[-1] - budget) / budget * 100
    daily_returns = portfolio_value.pct_change().dropna()
    sharpe = daily_returns.mean() / daily_returns.std() * np.sqrt(252) if daily_returns.std() != 0 else 0
    max_drawdown = (portfolio_value / portfolio_value.cummax() - 1).min() * 100
    
    return {
        'Portfolio Value': portfolio_value,
        'Total Return (%)': total_return,
        'Sharpe Ratio': sharpe,
        'Max Drawdown (%)': max_drawdown,
        'Final Value': portfolio_value.iloc[-1]
    }

# Main execution
if st.button("🚀 Esegui Analisi", type="primary"):
    with st.spinner('Caricamento dati e calcolo strategie...'):
        # Carica dati
        data = load_data(ticker, start_date, end_date)
        
        if data is not None and not data.empty:
            # Applica filtri
            st.header("🔍 Verifica Filtri di Liquidità")
            filters_passed, filter_messages = apply_filters(data, min_price, min_volume)
            
            for msg in filter_messages:
                st.write(msg)
            
            if not filters_passed:
                st.warning("⚠️ Il titolo non supera i filtri di liquidità. Le simulazioni potrebbero non essere realistiche.")
            
            st.divider()
            
            # Mappa strategie
            strategies = {
                "1. Long Trend High Momentum": strategy_1_trend_high_momentum,
                "2. Short RSI Thrust": strategy_2_short_rsi_thrust,
                "3. Long Mean Reversion Selloff": strategy_3_mean_reversion_selloff,
                "4. Long Trend Low Volatility": strategy_4_trend_low_volatility,
                "5. Long Mean Reversion High ADX Reversal": strategy_5_adx_reversal,
                "6. Short Mean Reversion High Six-Day Surge": strategy_6_six_day_surge,
                "7. Catastrophe Hedge": strategy_7_catastrophe_hedge
            }
            
            if strategy == "Tutte le Strategie (Portafoglio)":
                # Esegui tutte le strategie
                all_performances = {}
                
                cols = st.columns(2)
                for idx, (strat_name, strat_func) in enumerate(strategies.items()):
                    with cols[idx % 2]:
                        st.subheader(strat_name)
                        signals = strat_func(data.copy(), budget, risk_percentage)
                        
                        perf = calculate_performance(data, signals, budget)
                        if perf:
                            all_performances[strat_name] = perf
                            
                            # Metriche rapide
                            col1, col2, col3 = st.columns(3)
                            col1.metric("Return %", f"{perf['Total Return (%)']:.1f}%")
                            col2.metric("Sharpe", f"{perf['Sharpe Ratio']:.2f}")
                            col3.metric("Max DD %", f"{perf['Max Drawdown (%)']:.1f}%")
                
                # Grafico comparativo
                if all_performances:
                    st.header("📊 Confronto Performance")
                    fig = go.Figure()
                    
                    for strat_name, perf in all_performances.items():
                        short_name = strat_name.split('.')[1] if '.' in strat_name else strat_name
                        fig.add_trace(go.Scatter(
                            x=perf['Portfolio Value'].index,
                            y=perf['Portfolio Value'].values,
                            name=short_name
                        ))
                    
                    fig.add_hline(y=budget, line_dash="dash", line_color="gray", annotation_text="Capitale Iniziale")
                    fig.update_layout(
                        title="Confronto Performance Strategie",
                        xaxis_title="Data",
                        yaxis_title="Valore Portafoglio ($)",
                        template='plotly_dark',
                        height=600
                    )
                    st.plotly_chart(fig, use_container_width=True)
                
            else:
                # Esegui singola strategia
                st.header(f"📈 Analisi: {strategy}")
                
                # Ottieni la funzione della strategia
                strat_func = strategies.get(strategy)
                if strat_func:
                    signals = strat_func(data.copy(), budget, risk_percentage)
                    
                    # Calcola performance
                    performance = calculate_performance(data, signals, budget)
                    
                    if performance:
                        # Metriche
                        col1, col2, col3, col4 = st.columns(4)
                        col1.metric("Rendimento Totale", f"{performance['Total Return (%)']:.2f}%")
                        col2.metric("Sharpe Ratio", f"{performance['Sharpe Ratio']:.2f}")
                        col3.metric("Max Drawdown", f"{performance['Max Drawdown (%)']:.2f}%")
                        col4.metric("Valore Finale", f"${performance['Final Value']:,.2f}")
                        
                        st.divider()
                        
                        # Grafico principale
                        fig = plot_strategy(data, signals, strategy, ticker)
                        if fig:
                            st.plotly_chart(fig, use_container_width=True)
                        
                        # Grafico performance
                        st.subheader("📈 Curva del Capitale")
                        perf_fig = go.Figure()
                        perf_fig.add_trace(go.Scatter(
                            x=performance['Portfolio Value'].index,
                            y=performance['Portfolio Value'].values,
                            mode='lines',
                            name='Portafoglio',
                            line=dict(color='gold', width=2)
                        ))
                        perf_fig.add_hline(y=budget, line_dash="dash", line_color="gray", 
                                         annotation_text="Capitale Iniziale")
                        perf_fig.update_layout(
                            title="Andamento del Portafoglio",
                            xaxis_title="Data",
                            yaxis_title="Valore ($)",
                            template='plotly_dark',
                            height=400
                        )
                        st.plotly_chart(perf_fig, use_container_width=True)
                        
                        # Tabella segnali
                        st.subheader("📋 Tabella Segnali")
                        signals_display = signals[signals['Signal'] != 0].copy()
                        if not signals_display.empty:
                            signals_display['Data'] = signals_display.index
                            signals_display['Tipo'] = signals_display['Signal'].map({1: 'BUY', -1: 'SELL'})
                            signals_display['Prezzo'] = data.loc[signals_display.index, 'Close'].values
                            st.dataframe(
                                signals_display[['Data', 'Tipo', 'Prezzo']].sort_values('Data', ascending=False),
                                use_container_width=True
                            )
                        else:
                            st.info("Nessun segnale generato nel periodo selezionato.")
                else:
                    st.error("Strategia non trovata")
        else:
            st.error("Impossibile caricare i dati. Verifica il simbolo del titolo.")

# Footer - CORRETTO con tripli apici chiusi
st.divider()
st.markdown("""
**Nota:** Questo strumento è solo a scopo educativo. Il trading comporta rischi significativi.
Le performance passate non garantiscono risultati futuri.
""")
