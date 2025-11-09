# main.py
import os
import time
import threading
import traceback
from datetime import datetime
import pandas as pd
import numpy as np
import telebot
from flask import Flask, request
from pybit.unified_trading import HTTP

# ---------------- Config ----------------
BOT_TOKEN = os.environ.get("BOT_TOKEN")
BYBIT_API_KEY = os.environ.get("BYBIT_API_KEY")
BYBIT_API_SECRET = os.environ.get("BYBIT_API_SECRET")
# fixed chat id as you requested
CHAT_ID = 5198342012

# Monitoring params (5 minutes)
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", "300"))  # seconds
KLIMIT = int(os.environ.get("KLIMIT", "200"))
COOLDOWN = int(os.environ.get("COOLDOWN", "1800"))  # seconds between repeated signals per symbol

# sanity
if not BOT_TOKEN or not BYBIT_API_KEY or not BYBIT_API_SECRET:
    raise SystemExit("Set BOT_TOKEN, BYBIT_API_KEY and BYBIT_API_SECRET in environment")

# ---------------- Init ----------------
bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)
# real Bybit (not testnet)
session = HTTP(api_key=BYBIT_API_KEY, api_secret=BYBIT_API_SECRET, testnet=False)

SYMBOLS = [
    "BTCUSDT","ETHUSDT","SOLUSDT","XRPUSDT","BNBUSDT",
    "ADAUSDT","AVAXUSDT","DOTUSDT","LTCUSDT","LINKUSDT",
    "MATICUSDT","DOGEUSDT","OPUSDT","ARBUSDT","APTUSDT",
    "NEARUSDT","ATOMUSDT","FILUSDT","SUIUSDT","TONUSDT"
]

last_sent = {s: datetime.fromtimestamp(0) for s in SYMBOLS}

def log(msg):
    print(f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)

# ---------------- Bybit data ----------------
def fetch_klines(symbol, interval="15", limit=KLIMIT):
    """
    Returns DataFrame sorted oldest->newest with columns:
    ts, open, high, low, close, volume, turnover, time (datetime)
    """
    try:
        res = session.get_kline(category="linear", symbol=symbol, interval=str(interval), limit=limit)
        arr = res.get("result", {}).get("list")
        if not arr:
            log(f"{symbol} get_kline returned empty")
            return None
        df = pd.DataFrame(arr, columns=["ts","open","high","low","close","volume","turnover"])
        df[["open","high","low","close","volume","turnover"]] = df[["open","high","low","close","volume","turnover"]].astype(float)
        # Bybit may return ts in ms or seconds depending on endpoint; try ms then sec
        if df["ts"].max() > 1e12:
            df["time"] = pd.to_datetime(df["ts"], unit="ms")
        else:
            df["time"] = pd.to_datetime(df["ts"], unit="s")
        df = df.sort_values("time").reset_index(drop=True)
        return df
    except Exception as e:
        log(f"fetch_klines error {symbol}: {e}")
        return None

# ---------------- Analysis helpers ----------------
def compute_indicator_votes(df15, df60):
    """
    Returns direction: 'long'/'short'/None and info dict
    Uses EMA crossover (9/21), RSI(14), MACD histogram sign,
    candle patterns (engulfing/hammer), volume imbalance, S/R proximity (from 1h)
    """
    try:
        close15 = df15["close"].values
        if len(close15) < 30:
            return None, {"reason":"not enough 15m bars"}

        # EMA 9/21
        ema9 = pd.Series(close15).ewm(span=9).mean().iloc[-1]
        ema21 = pd.Series(close15).ewm(span=21).mean().iloc[-1]

        # RSI 14
        delta = pd.Series(close15).diff()
        up = delta.clip(lower=0).rolling(14).mean()
        down = -delta.clip(upper=0).rolling(14).mean()
        rsi = 100 - 100/(1 + (up.iloc[-1] / (down.iloc[-1] if down.iloc[-1] != 0 else 1)))

        # MACD hist (12/26/9)
        ema12 = pd.Series(close15).ewm(span=12).mean()
        ema26 = pd.Series(close15).ewm(span=26).mean()
        macd = ema12 - ema26
        macd_hist = (macd - macd.ewm(span=9).mean()).iloc[-1]

        # candle patterns (last two)
        last = df15.iloc[-1]
        prev = df15.iloc[-2]
        bullish_engulf = (prev["close"] < prev["open"]) and (last["close"] > last["open"]) and (last["close"] > prev["open"]) and (last["open"] < prev["close"])
        bearish_engulf = (prev["close"] > prev["open"]) and (last["close"] < last["open"]) and (last["open"] > prev["close"]) and (last["close"] < prev["open"])
        # hammer approx
        body = abs(last["close"] - last["open"])
        rng = last["high"] - last["low"] + 1e-9
        lower_wick = min(last["open"], last["close"]) - last["low"]
        upper_wick = last["high"] - max(last["open"], last["close"])
        hammer = (body < rng * 0.4) and (lower_wick > body * 2) and (upper_wick < body)

        # imbalance / volume spike
        avg_vol = df15["volume"].tail(50).mean() if len(df15) >= 60 else df15["volume"].mean()
        vol_spike = last["volume"] > avg_vol * 1.8 if avg_vol and not np.isnan(avg_vol) else False
        imb_up = vol_spike and last["close"] > last["open"]
        imb_down = vol_spike and last["close"] < last["open"]

        # support/resistance proximity from 1h
        sr_signal = None
        if df60 is not None and len(df60) >= 60:
            recent = df60.tail(120)
            sup = recent["low"].min()
            res = recent["high"].max()
            last_price = last["close"]
            if abs(last_price - sup) / last_price < 0.005:
                sr_signal = "long"
            elif abs(last_price - res) / last_price < 0.005:
                sr_signal = "short"

        # Voting
        votes_long = 0
        votes_short = 0
        reasons = []
        if ema9 > ema21:
            votes_long += 1; reasons.append("EMA9>21")
        else:
            votes_short += 1; reasons.append("EMA9<21")

        if rsi <
