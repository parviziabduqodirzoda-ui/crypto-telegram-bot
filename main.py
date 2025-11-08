# main.py
import os
import time
import math
import requests
import feedparser
import threading
from datetime import datetime, timedelta

import pandas as pd
import numpy as np
import pandas_ta as ta

from pybit.unified_trading import HTTP
from flask import Flask, request
import telebot

# ---------------- Configuration (from env) ----------------
BOT_TOKEN = os.getenv("BOT_TOKEN")          # Telegram bot token
CHAT_ID = int(os.getenv("CHAT_ID", "0"))    # target chat id (int)
BYBIT_API_KEY = os.getenv("BYBIT_API_KEY")
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET")
USE_TESTNET = os.getenv("USE_TESTNET", "True").lower() in ("1","true","yes")
CATEGORY_SPOT = os.getenv("USE_SPOT", "True").lower() in ("1","true","yes")

CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "600"))  # seconds between full scans (default 10 min)
COOLDOWN_SEC = int(os.getenv("COOLDOWN_SEC", "1800"))     # cooldown per symbol in seconds (default 30 min)
KLIMIT = int(os.getenv("KLIMIT", "200"))

# Symbols list (20) — ты просил все пары
SYMBOLS = [
 "BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","XRPUSDT","ADAUSDT","DOGEUSDT","AVAXUSDT",
 "DOTUSDT","TRXUSDT","MATICUSDT","LINKUSDT","ATOMUSDT","LTCUSDT","XLMUSDT","AAVEUSDT",
 "UNIUSDT","XAUTUSDT","TONUSDT","NEARUSDT"
]

# News RSS sources (simple)
NEWS_RSS = [
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "https://cointelegraph.com/rss"
]
POSITIVE_WORDS = ['approve','approval','green','bull','partnership','list','etf','adopt','launch','upgrade','upgrade','positive','gain']
NEGATIVE_WORDS = ['hack','exploit','scam','ban','regulation','fraud','fine','suspend','liquidation','bear','drop','attack','delist','halt']

# Thresholds for composite decision (must be tuned)
MIN_INDICATOR_SCORE = 2.0  # how many indicator points needed
MIN_COMPOSITE_SCORE = 3.0  # final aggregated score threshold to send signal

# ---------------- Init services ----------------
if not BOT_TOKEN or not BYBIT_API_KEY or not BYBIT_API_SECRET or CHAT_ID == 0:
    raise SystemExit("Missing required env vars: BOT_TOKEN, BYBIT_API_KEY, BYBIT_API_SECRET, CHAT_ID")

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

session = HTTP(api_key=BYBIT_API_KEY, api_secret=BYBIT_API_SECRET, testnet=USE_TESTNET)
CATEGORY = "spot" if CATEGORY_SPOT else "linear"

last_signal_time = {s: datetime.utcfromtimestamp(0) for s in SYMBOLS}

# ---------------- Helpers ----------------
def send_telegram(text):
    try:
        bot.send_message(CHAT_ID, text)
        return True
    except Exception as e:
        print("Telegram send error:", e)
        return False

def fetch_klines_bybit(symbol, interval, limit=KLIMIT):
    """Fetch kline data from Bybit API v5 via pybit unified_trading.get_kline"""
    try:
        res = session.get_kline(category=CATEGORY, symbol=symbol, interval=str(interval), limit=limit)
        arr = res.get("result", {}).get("list", None)
        if not arr:
            print(f"fetch_klines: empty result for {symbol} {interval}")
            return None
        df = pd.DataFrame(arr, columns=["timestamp","open","high","low","close","volume","turnover"])
        df["open"] = df["open"].astype(float)
        df["high"] = df["high"].astype(float)
        df["low"] = df["low"].astype(float)
        df["close"] = df["close"].astype(float)
        df["volume"] = df["volume"].astype(float)
        df["dt"] = pd.to_datetime(df["timestamp"], unit='ms')
        df = df.iloc[::-1].reset_index(drop=True)  # oldest -> newest
        return df
    except Exception as e:
        print(f"fetch_klines_bybit error {symbol} {interval}: {e}")
        return None

# ---------------- Technical indicators ----------------
def compute_indicators(df):
    s = df['close']
    out = {}
    out['ema9'] = ta.ema(s, length=9).iloc[-1]
    out['ema21'] = ta.ema(s, length=21).iloc[-1]
    out['rsi14'] = ta.rsi(s, length=14).iloc[-1]
    macd = ta.macd(s)
    out['macd_hist'] = macd['MACDh_12_26_9'].iloc[-1] if 'MACDh_12_26_9' in macd else 0.0
    out['atr14'] = ta.atr(df['high'], df['low'], df['close'], length=14).iloc[-1]
    # VWAP on window
    pv = (df['close'] * df['volume']).cumsum()
    vv = df['volume'].cumsum()
    out['vwap'] = (pv / vv).iloc[-1]
    return out

# ---------------- Support / Resistance ----------------
def support_resistance_levels(df, lookback=120):
    window = df[-lookback:]
    sup = float(window['low'].min())
    res = float(window['high'].max())
    return sup, res

# ---------------- Volume spike / imbalance ----------------
def detect_imbalance(df):
    # volume spike + large real body
    last = df.iloc[-1]
    avg_vol = df['volume'].tail(50).mean()
    body = abs(last['close'] - last['open'])
    rng = (last['high'] - last['low']) + 1e-9
    body_ratio = body / rng
    vol_spike = last['volume'] > avg_vol * 1.8
    is_up = last['close'] > last['open']
    if vol_spike and body_ratio > 0.5:
        return 'imbalance_up' if is_up else 'imbalance_down'
    return None

# ---------------- Candle pattern detection (simple) ----------------
def candle_pattern(df):
    # look at last 2 candles for engulfing
    if len(df) < 3:
        return None
    c1 = df.iloc[-2]
    c2 = df.iloc[-1]
    # bullish engulfing
    if c1['close'] < c1['open'] and c2['close'] > c2['open'] and c2['close'] > c1['open'] and c2['open'] < c1['close']:
        return 'bullish_engulfing'
    # bearish engulfing
    if c1['close'] > c1['open'] and c2['close'] < c2['open'] and c2['open'] > c1['close'] and c2['close'] < c1['open']:
        return 'bearish_engulfing'
    # hammer / shooting star approximations
    body = abs(c2['close'] - c2['open'])
    upper = c2['high'] - max(c2['open'], c2['close'])
    lower = min(c2['open'], c2['close']) - c2['low']
    if body < (c2['high'] - c2['low']) * 0.4 and lower > body * 2 and upper < body:
        return 'hammer'
    if body < (c2['high'] - c2['low']) * 0.4 and upper > body * 2 and lower < body:
        return 'shooting_star'
    return None

# ---------------- News sentiment (simple RSS count) ----------------
def news_sentiment():
    score = 0.0
    try:
        for url in NEWS_RSS:
            feed = feedparser.parse(url)
            for entry in feed.entries[:6]:
                text = (entry.get('title','') + ' ' + entry.get('summary','')).lower()
                for w in POSITIVE_WORDS:
                    if w in text: score += 0.3
                for w in NEGATIVE_WORDS:
                    if w in text: score -= 0.6
        return round(score, 2)
    except Exception as e:
        print("news_sentiment error:", e)
        return 0.0

# ---------------- Composite decision ----------------
def analyze_symbol(symbol):
    now = datetime.utcnow()
    # fetch TFs
    df_15 = fetch_klines_bybit(symbol, "15", limit=KLIMIT)
    df_60 = fetch_klines_bybit(symbol, "60", limit=KLIMIT)
    df_240 = fetch_klines_bybit(symbol, "240", limit=KLIMIT)
    if df_15 is None or df_60 is None:
        return None

    ind15 = compute_indicators(df_15)
    ind60 = compute_indicators(df_60) if df_60 is not None else None
    ind240 = compute_indicators(df_240) if df_240 is not None else None

    # basic directional votes from indicators (15m)
    votes = {'long':0.0, 'short':0.0}
    reasons = []

    # EMA crossover (15m)
    if ind15['ema9'] > ind15['ema21']:
        votes['long'] += 1.0; reasons.append("EMA9>EMA21(15m)")
    else:
        votes['short'] += 1.0; reasons.append("EMA9<EMA21(15m)")

    # RSI
    if ind15['rsi14'] < 35:
        votes['long'] += 0.9; reasons.append("RSI oversold")
    if ind15['rsi14'] > 65:
        votes['short'] += 0.9; reasons.append("RSI overbought")

    # MACD hist momentum
    if ind15['macd_hist'] > 0:
        votes['long'] += 0.6; reasons.append("MACD+")
    else:
        votes['short'] += 0.6; reasons.append("MACD-")

    # VWAP bias
    last_price = float(df_15['close'].iloc[-1])
    if last_price > ind15['vwap']:
        votes['long'] += 0.4; reasons.append("Price>VWAP")
    else:
        votes['short'] += 0.4; reasons.append("Price<VWAP")

    # volume spike / imbalance
    imb = detect_imbalance(df_15)
    if imb == 'imbalance_up':
        votes['long'] += 0.8; reasons.append("Imbalance up")
    if imb == 'imbalance_down':
        votes['short'] += 0.8; reasons.append("Imbalance down")

    # candle pattern (15m)
    pat = candle_pattern(df_15)
    if pat in ('bullish_engulfing','hammer'):
        votes['long'] += 1.0; reasons.append(pat)
    if pat in ('bearish_engulfing','shooting_star'):
        votes['short'] += 1.0; reasons.append(pat)

    # Support/Resistance proximity (15m window)
    sup, res = support_resistance_levels(df_60 if df_60 is not None else df_15, lookback=120)
    if abs(last_price - sup) / last_price < 0.003:
        votes['long'] += 0.5; reasons.append("Near support")
    if abs(last_price - res) / last_price < 0.003:
        votes['short'] += 0.5; reasons.append("Near resistance")

    # Higher TF confirmation (require same direction on 1h and 4h)
    higher_confirm = 0.0
    hc_reasons = []
    try:
        if ind60:
            if ind60['ema9'] > ind60['ema21']:
                higher_confirm += 0.8; hc_reasons.append("1H bullish")
            else:
                higher_confirm -= 0.8; hc_reasons.append("1H bearish")
        if ind240:
            if ind240['ema9'] > ind240['ema21']:
                higher_confirm += 0.8; hc_reasons.append("4H bullish")
            else:
                higher_confirm -= 0.8; hc_reasons.append("4H bearish")
    except Exception:
        pass

    if higher_confirm > 0:
        votes['long'] += 0.8; reasons += hc_reasons
    elif higher_confirm < 0:
        votes['short'] += 0.8; reasons += hc_reasons

    # news sentiment
    news_score = news_sentiment()
    if news_score > 0.6:
        votes['long'] += 0.5; reasons.append("Positive news")
    if news_score < -0.6:
        votes['short'] += 1.0; reasons.append("Negative news")

    # Composite scoring
    long_score = round(votes['long'],2)
    short_score = round(votes['short'],2)
    direction = None
    score = 0.0
    if long_score >= MIN_COMPOSITE_SCORE and long_score - short_score > 0.8:
        direction = 'LONG'
        score = long_score - short_score
    elif short_score >= MIN_COMPOSITE_SCORE and short_score - long_score > 0.8:
        direction = 'SHORT'
        score = short_score - long_score

    # final check: require indicator minimum + higher tf agreement not strongly opposite
    # also avoid signals if news strongly negative for long or strongly positive for short
    if direction:
        if (direction == 'LONG' and news_score < -0.8) or (direction == 'SHORT' and news_score > 0.8):
            # news contradicts => cancel
            direction = None

    # prepare SL/TP using ATR (1H preferred)
    atr_ref = ind60['atr14'] if ind60 is not None else ind15['atr14']
    if atr_ref is None or atr_ref == 0:
        atr_ref = ind15['atr14'] if ind15 else 0.0
    # risk multiple (tweakable)
    if direction == 'LONG':
        sl = last_price - max(atr_ref * 1.5, last_price*0.015)
        tp1 = last_price + max(atr_ref * 2.5, last_price*0.03)
        tp2 = last_price + max(atr_ref * 4.0, last_price*0.05)
        tp3 = last_price + max(atr_ref * 6.0, last_price*0.07)
    elif direction == 'SHORT':
        sl = last_price + max(atr_ref * 1.5, last_price*0.015)
        tp1 = last_price - max(atr_ref * 2.5, last_price*0.03)
        tp2 = last_price - max(atr_ref * 4.0, last_price*0.05)
        tp3 = last_price - max(atr_ref * 6.0, last_price*0.07)
    else:
        sl=tp1=tp2=tp3=None

    info = {
        "symbol": symbol,
        "time": datetime.utcnow().isoformat(),
        "price": last_price,
        "direction": direction,
        "score": round(score,2),
        "reasons": reasons,
        "sl": round(sl, 2) if sl else None,
        "tp1": round(tp1, 2) if tp1 else None,
        "tp2": round(tp2, 2) if tp2 else None,
        "tp3": round(tp3, 2) if tp3 else None,
        "news_score": news_score,
    }
    return info

# ---------------- Main monitor loop ----------------
def monitor_loop():
    print("Monitor started, scanning symbols...")
    while True:
        start = time.time()
        for s in SYMBOLS:
            try:
                info = analyze_symbol(s)
                if info and info['direction']:
                    now = datetime.utcnow()
                    elapsed = (now - last_signal_time[s]).total_seconds()
                    if elapsed < COOLDOWN_SEC:
                        print(f"{s}: cooldown active ({int(elapsed)}s elapsed)")
                        continue
                    # prepare short message
                    msg = f"{s}\n"
                    msg += "Лонг\n" if info['direction']=='LONG' else "Шорт\n"
                    msg += f"SL:{info['sl']}\nTP1:{info['tp1']}\nTP2:{info['tp2']}\nTP3:{info['tp3']}"
                    send_telegram(msg)
                    last_signal_time[s] = now
                    print(f"Sent {s} {info['direction']} score={info['score']}")
                else:
                    print(f"{s}: no strong signal")
            except Exception as e:
                print("Error in monitor for", s, e)
            time.sleep(1.2)  # small pause to avoid hitting rate limits
        took = time.time() - start
        wait = max(10, CHECK_INTERVAL - took)
        print(f"Cycle done. Sleeping {int(wait)}s")
        time.sleep(wait)

# ---------------- Flask webhook for Telegram -------------

@app.route('/' + BOT_TOKEN, methods=['POST'])
def webhook_receive():
    json_str = request.stream.read().decode('UTF-8')
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return 'OK', 200

@app.route('/')
def webhook_set():
    # when Render calls root, set webhook
    host = os.environ.get('RENDER_EXTERNAL_HOSTNAME')
    url = f"https://{host}/{BOT_TOKEN}"
    bot.remove_webhook()
    bot.set_webhook(url=url)
    return "Webhook set", 200

# ---------------- Start background thread and Flask app -----------
def start_service():
    t = threading.Thread(target=monitor_loop, daemon=True)
    t.start()
    print("Background monitor thread started")

if __name__ == "__main__":
    start_service()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
