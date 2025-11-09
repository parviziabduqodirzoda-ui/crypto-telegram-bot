
# main.py — фоновый монитор + webhook (Render)
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

# ---- config from env ----
BOT_TOKEN = os.environ.get("BOT_TOKEN")
BYBIT_API_KEY = os.environ.get("BYBIT_API_KEY")
BYBIT_API_SECRET = os.environ.get("BYBIT_API_SECRET")
CHAT_ID = int(os.environ.get("CHAT_ID", "5198342012"))
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", "300"))  # seconds
KLIMIT = int(os.environ.get("KLIMIT", "200"))

if not BOT_TOKEN or not BYBIT_API_KEY or not BYBIT_API_SECRET:
    raise SystemExit("Missing BOT_TOKEN or BYBIT_API_KEY / BYBIT_API_SECRET in env")

# ---- init services ----
bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)
session = HTTP(api_key=BYBIT_API_KEY, api_secret=BYBIT_API_SECRET, testnet=False)

SYMBOLS = [
    "BTCUSDT","ETHUSDT","SOLUSDT","XRPUSDT","BNBUSDT",
    "ADAUSDT","AVAXUSDT","DOTUSDT","LTCUSDT","LINKUSDT",
    "MATICUSDT","DOGEUSDT","OPUSDT","ARBUSDT","APTUSDT",
    "NEARUSDT","ATOMUSDT","FILUSDT","SUIUSDT","TONUSDT"
]

# cooldown map to avoid repeat spamming
last_sent = {s: datetime.fromtimestamp(0) for s in SYMBOLS}
COOLDOWN = int(os.environ.get("COOLDOWN", "1800"))  # 30 min default

# ---- helpers ----
def log(msg):
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)

def fetch_klines(symbol, interval="15", limit=KLIMIT):
    try:
        r = session.get_kline(category="linear", symbol=symbol, interval=str(interval), limit=limit)
        arr = r.get("result", {}).get("list")
        if not arr:
            log(f"{symbol} get_kline empty")
            return None
        df = pd.DataFrame(arr, columns=["ts","open","high","low","close","volume","turnover"])
        df[["open","high","low","close","volume","turnover"]] = df[["open","high","low","close","volume","turnover"]].astype(float)
        df["time"] = pd.to_datetime(df["ts"], unit="s")
        df = df.sort_values("time").reset_index(drop=True)
        return df
    except Exception as e:
        log(f"fetch_klines error {symbol}: {e}")
        return None

def compute_signals(df_15, df_60):
    """Return 'long' or 'short' or None and reason dict"""
    try:
        close15 = df_15["close"].values
        if len(close15) < 30:
            return None, {}
        # EMA
        ema9 = pd.Series(close15).ewm(span=9).mean().iloc[-1]
        ema21 = pd.Series(close15).ewm(span=21).mean().iloc[-1]
        # RSI
        delta = pd.Series(close15).diff()
        up = delta.clip(lower=0).rolling(14).mean()
        down = -delta.clip(upper=0).rolling(14).mean()
        rsi = 100 - 100/(1 + up.iloc[-1]/(down.iloc[-1] if down.iloc[-1] != 0 else 1))
        # MACD simple
        ema12 = pd.Series(close15).ewm(span=12).mean()
        ema26 = pd.Series(close15).ewm(span=26).mean()
        macd = ema12 - ema26
        macd_hist = (macd - macd.ewm(span=9).mean()).iloc[-1]

        # candle pattern (last two)
        last = df_15.iloc[-1]
        prev = df_15.iloc[-2]
        bullish_engulf = (prev["close"] < prev["open"]) and (last["close"] > last["open"]) and (last["close"] > prev["open"]) and (last["open"] < prev["close"])
        bearish_engulf = (prev["close"] > prev["open"]) and (last["close"] < last["open"]) and (last["open"] > prev["close"]) and (last["close"] < prev["open"])
        hammer = (abs(last["close"] - last["open"]) < (last["high"] - last["low"]) * 0.4) and ((min(last["open"], last["close"]) - last["low"]) > (last["high"] - last["low"]) * 0.2)

        # imbalance: volume spike + big body
        avg_vol = df_15["volume"].tail(50).mean()
        vol_spike = last["volume"] > avg_vol * 1.8
        body = abs(last["close"] - last["open"])
        rng = last["high"] - last["low"] + 1e-9
        body_ratio = body / rng
        imb_up = vol_spike and body_ratio > 0.5 and last["close"] > last["open"]
        imb_down = vol_spike and body_ratio > 0.5 and last["close"] < last["open"]

        # support/resistance from 1h
        sr = None
        if df_60 is not None and len(df_60) > 30:
            last_price = last["close"]
            recent = df_60.tail(120)
            sup = recent["low"].min()
            res = recent["high"].max()
            if abs(last_price - sup)/last_price < 0.005:
                sr = "near_support"
            if abs(last_price - res)/last_price < 0.005:
                sr = "near_resistance"

        # votes
        votes_long = 0
        votes_short = 0
        reasons = []

        if ema9 > ema21:
            votes_long += 1; reasons.append("EMA9>21")
        else:
            votes_short += 1; reasons.append("EMA9<21")
        if rsi < 35:
            votes_long += 1; reasons.append("RSI low")
        if rsi > 65:
            votes_short += 1; reasons.append("RSI high")
        if macd_hist > 0:
            votes_long += 1; reasons.append("MACD+")
        else:
            votes_short += 1; reasons.append("MACD-")
        if bullish_engulf or hammer:
            votes_long += 1; reasons.append("candle bullish")
        if bearish_engulf:
            votes_short += 1; reasons.append("candle bearish")
        if imb_up:
            votes_long += 1; reasons.append("imbalance up")
        if imb_down:
            votes_short += 1; reasons.append("imbalance down")
        if sr == "near_support":
            votes_long += 1; reasons.append("near S")
        if sr == "near_resistance":
            votes_short += 1; reasons.append("near R")

        # require >=4 votes for signal
        if votes_long >= 4 and votes_long - votes_short >= 1.0:
            return "long", {"votes_long": votes_long, "votes_short": votes_short, "reasons": reasons}
        if votes_short >= 4 and votes_short - votes_long >= 1.0:
            return "short", {"votes_long": votes_long, "votes_short": votes_short, "reasons": reasons}
        return None, {"votes_long": votes_long, "votes_short": votes_short, "reasons": reasons}

    except Exception as e:
        log("compute_signals error: " + str(e))
        return None, {}

def build_message(symbol, direction, price, sl, tp1, tp2, tp3):
    if direction == "long":
        header = f"📈 {symbol}\nЛонг\n"
    else:
        header = f"📉 {symbol}\nШорт\n"
    return f"{header}SL:{sl}\nTP1:{tp1}\nTP2:{tp2}\nTP3:{tp3}"

# ---- monitor loop (background) ----
def monitor_loop():
    log("Background monitor started")
    while True:
        cycle_start = time.time()
        for symbol in SYMBOLS:
            try:
                log(f"Checking {symbol} ...")
                df15 = fetch_klines(symbol, interval="15")
                df60 = fetch_klines(symbol, interval="60")
                if df15 is None:
                    log(f"{symbol} no df15, skip")
                    continue

                direction, info = compute_signals(df15, df60)
                if direction:
                    now = datetime.utcnow()
                    elapsed = (now - last_sent[symbol]).total_seconds()
                    if elapsed < COOLDOWN:
                        log(f"{symbol} signal but in cooldown ({int(elapsed)}s elapsed)")
                    else:
                        price = df15["close"].iloc[-1]
                        # ATR-based SL/TP or simple percent
                        sl = round(price * (0.97 if direction=="long" else 1.03), 2)
                        tp1 = round(price * (1.03 if direction=="long" else 0.97), 2)
                        tp2 = round(price * (1.05 if direction=="long" else 0.95), 2)
                        tp3 = round(price * (1.07 if direction=="long" else 0.93), 2)
                        msg = build_message(symbol, direction, price, sl, tp1, tp2, tp3)
                        try:
                            bot.send_message(CHAT_ID, msg)
                            log(f"Sent signal for {symbol}: {direction} votes {info.get('votes_long')}/{info.get('votes_short')}")
                            last_sent[symbol] = now
                        except Exception as e:
                            log(f"Telegram send failed: {e}")
                else:
                    log(f"{symbol}: no strong signal ({info.get('votes_long')}/{info.get('votes_short')})")
                time.sleep(1.2)  # avoid rate limits
            except Exception as e:
                log(f"Error processing {symbol}: {e}\n{traceback.format_exc()}")
        # sleep remaining to match CHECK_INTERVAL
        took = time.time() - cycle_start
        to_wait = max(5, CHECK_INTERVAL - took)
        log(f"Cycle done, sleeping {int(to_wait)}s")
        time.sleep(to_wait)

# ---- Flask webhook endpoints ----
@app.route('/' + BOT_TOKEN, methods=['POST'])
def webhook_receive():
    try:
        json_str = request.stream.read().decode('utf-8')
        update = telebot.types.Update.de_json(json_str)
        bot.process_new_updates([update])
    except Exception as e:
        log(f"Webhook processing error: {e}")
    return "OK", 200

@app.route('/')
def root():
    return "OK", 200

@bot.message_handler(commands=["start"])
def cmd_start(m):
    bot.send_message(m.chat.id, "✅ Бот активен. Мониторинг запущен.")

# ---- start background thread and run flask ----
if __name__ == "__main__":
    t = threading.Thread(target=monitor_loop, daemon=True)
    t.start()
    port = int(os.environ.get("PORT", 5000))
    log("Starting Flask app")
    app.run(host="0.0.0.0", port=port)
