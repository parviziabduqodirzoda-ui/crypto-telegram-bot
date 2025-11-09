import os
import time
import threading
import telebot
import pandas as pd
import numpy as np
from flask import Flask, request
from pybit.unified_trading import HTTP
from datetime import datetime

# --- Настройки ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")
BYBIT_API_KEY = os.environ.get("BYBIT_API_KEY")
BYBIT_API_SECRET = os.environ.get("BYBIT_API_SECRET")
CHAT_ID = 5198342012  # твой Telegram ID
CHECK_INTERVAL = 300  # 5 минут

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

session = HTTP(api_key=BYBIT_API_KEY, api_secret=BYBIT_API_SECRET)

SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT",
    "ADAUSDT", "AVAXUSDT", "DOTUSDT", "LTCUSDT", "LINKUSDT",
    "MATICUSDT", "DOGEUSDT", "OPUSDT", "ARBUSDT", "APTUSDT",
    "NEARUSDT", "ATOMUSDT", "FILUSDT", "SUIUSDT", "TONUSDT"
]

# --- Получаем исторические данные ---
def get_klines(symbol, interval="15"):
    try:
        resp = session.get_kline(category="linear", symbol=symbol, interval=interval, limit=200)
        data = pd.DataFrame(resp["result"]["list"], columns=[
            "timestamp", "open", "high", "low", "close", "volume", "turnover"
        ])
        data = data.astype(float)
        data["time"] = pd.to_datetime(data["timestamp"], unit='s')
        return data.sort_values("time")
    except Exception as e:
        print(f"Ошибка получения данных для {symbol}: {e}")
        return None

# --- Технический анализ ---
def technical_analysis(df):
    df["ema50"] = df["close"].ewm(span=50).mean()
    df["ema200"] = df["close"].ewm(span=200).mean()
    df["rsi"] = 100 - (100 / (1 + (df["close"].diff().clip(lower=0).rolling(14).mean() /
                                   df["close"].diff().clip(upper=0).abs().rolling(14).mean())))
    short_ema = df["close"].ewm(span=12).mean()
    long_ema = df["close"].ewm(span=26).mean()
    df["macd"] = short_ema - long_ema
    df["signal"] = df["macd"].ewm(span=9).mean()

    last = df.iloc[-1]
    trend = "long" if last["ema50"] > last["ema200"] else "short"
    rsi_signal = "long" if last["rsi"] < 30 else "short" if last["rsi"] > 70 else None
    macd_signal = "long" if last["macd"] > last["signal"] else "short"

    return trend, rsi_signal, macd_signal

# --- Свечной анализ (паттерны) ---
def candle_patterns(df):
    last = df.iloc[-1]
    prev = df.iloc[-2]
    bullish = last["close"] > last["open"] and prev["close"] < prev["open"] and last["open"] < prev["close"]
    bearish = last["close"] < last["open"] and prev["close"] > prev["open"] and last["open"] > prev["close"]
    if bullish:
        return "long"
    elif bearish:
        return "short"
    return None

# --- Поддержка / сопротивление ---
def support_resistance(df):
    recent = df.tail(50)
    support = recent["low"].min()
    resistance = recent["high"].max()
    last_close = recent.iloc[-1]["close"]
    if last_close <= support * 1.01:
        return "long"
    elif last_close >= resistance * 0.99:
        return "short"
    return None

# --- Имбаланс ---
def imbalance_check(df):
    avg_vol = df["volume"].mean()
    last_vol = df.iloc[-1]["volume"]
    return "long" if last_vol > 1.5 * avg_vol and df.iloc[-1]["close"] > df.iloc[-2]["close"] else \
           "short" if last_vol > 1.5 * avg_vol and df.iloc[-1]["close"] < df.iloc[-2]["close"] else None

# --- Проверка и отправка сигналов ---
def check_signals():
    while True:
        for symbol in SYMBOLS:
            print(f"Проверка {symbol}...")
            df = get_klines(symbol)
            if df is None:
                continue

            trend, rsi_signal, macd_signal = technical_analysis(df)
            pattern_signal = candle_patterns(df)
            level_signal = support_resistance(df)
            imbalance_signal = imbalance_check(df)

            signals = [trend, rsi_signal, macd_signal, pattern_signal, level_signal, imbalance_signal]
            longs = signals.count("long")
            shorts = signals.count("short")

            if longs >= 4:
                tp1 = round(df.iloc[-1]["close"] * 1.03, 2)
                tp2 = round(df.iloc[-1]["close"] * 1.05, 2)
                tp3 = round(df.iloc[-1]["close"] * 1.07, 2)
                sl = round(df.iloc[-1]["close"] * 0.97, 2)
                msg = f"📈 {symbol}\nЛонг\nSL: {sl}\nTP1: {tp1}\nTP2: {tp2}\nTP3: {tp3}"
                bot.send_message(CHAT_ID, msg)

            elif shorts >= 4:
                tp1 = round(df.iloc[-1]["close"] * 0.97, 2)
                tp2 = round(df.iloc[-1]["close"] * 0.95, 2)
                tp3 = round(df.iloc[-1]["close"] * 0.93, 2)
                sl = round(df.iloc[-1]["close"] * 1.03, 2)
                msg = f"📉 {symbol}\nШорт\nSL: {sl}\nTP1: {tp1}\nTP2: {tp2}\nTP3: {tp3}"
                bot.send_message(CHAT_ID, msg)

        time.sleep(CHECK_INTERVAL)

# --- Flask маршруты ---
@app.route('/' + BOT_TOKEN, methods=['POST'])
def webhook_post():
    update = telebot.types.Update.de_json(request.stream.read().decode('utf-8'))
    bot.process_new_updates([update])
    return "ok", 200

@app.route('/')
def webhook():
    bot.remove_webhook()
    bot.set_webhook(url=f"https://{os.environ.get('RENDER_EXTERNAL_HOSTNAME')}/{BOT_TOKEN}")
    return "Webhook установлен успешно!", 200

@bot.message_handler(commands=["start"])
def start_msg(message):
    bot.send_message(message.chat.id, "✅ Бот активен и мониторит рынок 24/7!")

# --- Запуск ---
if __name__ == "__main__":
    threading.Thread(target=check_signals, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
