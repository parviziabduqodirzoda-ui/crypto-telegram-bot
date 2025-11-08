import os
import time
import telebot
from pybit.unified_trading import HTTP
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import talib

# === Настройки ===
BOT_TOKEN = os.environ.get("BOT_TOKEN")
BYBIT_API_KEY = os.environ.get("BYBIT_API_KEY")
BYBIT_API_SECRET = os.environ.get("BYBIT_API_SECRET")
USE_TESTNET = os.environ.get("USE_TESTNET", "True").lower() == "true"

bot = telebot.TeleBot(BOT_TOKEN)

session = HTTP(
    testnet=USE_TESTNET,
    api_key=BYBIT_API_KEY,
    api_secret=BYBIT_API_SECRET
)

# Список активов для анализа
SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
    "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "DOTUSDT", "LINKUSDT",
    "LTCUSDT", "TRXUSDT", "UNIUSDT", "MATICUSDT", "APTUSDT",
    "ARBUSDT", "OPUSDT", "NEARUSDT", "ATOMUSDT", "FILUSDT"
]

# === Получение данных ===
def get_klines(symbol, interval="15", limit=200):
    try:
        data = session.get_kline(category="linear", symbol=symbol, interval=interval, limit=limit)
        df = pd.DataFrame(data['result']['list'], columns=[
            "timestamp", "open", "high", "low", "close", "volume", "_", "_", "_", "_", "_", "_"
        ])
        df = df.astype(float)
        df['close_time'] = pd.to_datetime(df['timestamp'], unit='s')
        return df[::-1]  # в правильном порядке
    except Exception as e:
        print(f"Ошибка загрузки {symbol}: {e}")
        return None

# === Проверка сигналов ===
def analyze_symbol(symbol):
    df = get_klines(symbol, "15", 200)
    if df is None or len(df) < 50:
        return None

    close = df["close"].values
    high = df["high"].values
    low = df["low"].values

    # Индикаторы
    rsi = talib.RSI(close, timeperiod=14)
    macd, macdsignal, macdhist = talib.MACD(close)
    ma_fast = talib.SMA(close, 9)
    ma_slow = talib.SMA(close, 21)

    # Свечной анализ (пример)
    hammer = talib.CDLHAMMER(df["open"], high, low, close)
    engulfing = talib.CDLENGULFING(df["open"], high, low, close)

    # Проверка паттернов
    last_rsi = rsi[-1]
    bullish = (ma_fast[-1] > ma_slow[-1]) and (macd[-1] > macdsignal[-1]) and (last_rsi < 70) and (hammer[-1] != 0 or engulfing[-1] > 0)
    bearish = (ma_fast[-1] < ma_slow[-1]) and (macd[-1] < macdsignal[-1]) and (last_rsi > 30) and (hammer[-1] != 0 or engulfing[-1] < 0)

    if bullish:
        entry = close[-1]
        sl = round(entry * 0.97, 2)
        tp1 = round(entry * 1.03, 2)
        tp2 = round(entry * 1.05, 2)
        tp3 = round(entry * 1.07, 2)
        return f"📈 {symbol}\nЛонг\nSL: {sl}\nTP1: {tp1}\nTP2: {tp2}\nTP3: {tp3}"

    elif bearish:
        entry = close[-1]
        sl = round(entry * 1.03, 2)
        tp1 = round(entry * 0.97, 2)
        tp2 = round(entry * 0.95, 2)
        tp3 = round(entry * 0.93, 2)
        return f"📉 {symbol}\nШорт\nSL: {sl}\nTP1: {tp1}\nTP2: {tp2}\nTP3: {tp3}"

    return None

# === Основной цикл ===
def main_loop():
    print("🚀 Бот запущен и анализирует рынок...")
    while True:
        for sym in SYMBOLS:
            signal = analyze_symbol(sym)
            if signal:
                bot.send_message(chat_id="ТВОЙ_CHAT_ID", text=signal)
                print(f"✅ Сигнал отправлен: {signal}")
            time.sleep(2)
        time.sleep(60 * 15)  # обновление каждые 15 минут

if __name__ == "__main__":
    main_loop()
