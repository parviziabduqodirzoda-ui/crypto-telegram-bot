import os
import time
import telebot
from pybit.unified_trading import HTTP
import pandas as pd
import numpy as np
import talib
from datetime import datetime, timedelta

# === Настройки ===
BOT_TOKEN = os.environ.get("BOT_TOKEN")
BYBIT_API_KEY = os.environ.get("BYBIT_API_KEY")
BYBIT_API_SECRET = os.environ.get("BYBIT_API_SECRET")
USE_TESTNET = os.environ.get("USE_TESTNET", "True").lower() == "true"

bot = telebot.TeleBot(BOT_TOKEN)
CHAT_ID = 5198342012  # твой Telegram ID

session = HTTP(
    testnet=USE_TESTNET,
    api_key=BYBIT_API_KEY,
    api_secret=BYBIT_API_SECRET
)

# === Список активов ===
SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
    "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "DOTUSDT", "LINKUSDT",
    "LTCUSDT", "TRXUSDT", "UNIUSDT", "MATICUSDT", "APTUSDT",
    "ARBUSDT", "OPUSDT", "NEARUSDT", "ATOMUSDT", "FILUSDT"
]

# === Получение данных с Bybit ===
def get_klines(symbol, interval="15", limit=200):
    try:
        data = session.get_kline(category="linear", symbol=symbol, interval=interval, limit=limit)
        df = pd.DataFrame(data['result']['list'], columns=[
            "timestamp", "open", "high", "low", "close", "volume", "_", "_", "_", "_", "_", "_"
        ])
        df = df.astype(float)
        df["time"] = pd.to_datetime(df["timestamp"], unit='s')
        df = df[::-1]
        return df
    except Exception as e:
        print(f"Ошибка загрузки данных {symbol}: {e}")
        return None

# === Поиск уровней поддержки и сопротивления ===
def find_levels(df, sensitivity=3):
    levels = []
    for i in range(sensitivity, len(df)-sensitivity):
        high_range = df["high"][i-sensitivity:i+sensitivity]
        low_range = df["low"][i-sensitivity:i+sensitivity]
        if df["high"][i] == high_range.max():
            levels.append(df["high"][i])
        if df["low"][i] == low_range.min():
            levels.append(df["low"][i])
    return list(set([round(l, 2) for l in levels]))

# === Проверка сигналов ===
def analyze_symbol(symbol):
    df_15m = get_klines(symbol, "15", 200)
    df_1h = get_klines(symbol, "60", 200)
    if df_15m is None or len(df_15m) < 50:
        return None

    close = df_15m["close"].values
    high = df_15m["high"].values
    low = df_15m["low"].values

    # Индикаторы
    rsi = talib.RSI(close, timeperiod=14)
    macd, macdsignal, _ = talib.MACD(close)
    ma_fast = talib.SMA(close, 9)
    ma_slow = talib.SMA(close, 21)

    # Свечные паттерны
    hammer = talib.CDLHAMMER(df_15m["open"], high, low, close)
    engulf = talib.CDLENGULFING(df_15m["open"], high, low, close)

    # Уровни поддержки/сопротивления на старшем ТФ
    levels_h = find_levels(df_1h)
    current_price = close[-1]

    # Проверка на близость к уровню
    near_level = any(abs(current_price - lvl) / current_price < 0.01 for lvl in levels_h)

    # Условия на лонг и шорт
    bullish = (
        ma_fast[-1] > ma_slow[-1] and
        macd[-1] > macdsignal[-1] and
        rsi[-1] < 70 and
        (hammer[-1] != 0 or engulf[-1] > 0) and
        near_level
    )

    bearish = (
        ma_fast[-1] < ma_slow[-1] and
        macd[-1] < macdsignal[-1] and
        rsi[-1] > 30 and
        (hammer[-1] != 0 or engulf[-1] < 0) and
        near_level
    )

    # Формирование сигнала
    if bullish:
        entry = current_price
        sl = round(entry * 0.97, 2)
        tp1 = round(entry * 1.03, 2)
        tp2 = round(entry * 1.05, 2)
        tp3 = round(entry * 1.07, 2)
        return f"📈 {symbol}\nЛонг\nSL: {sl}\nTP1: {tp1}\nTP2: {tp2}\nTP3: {tp3}"

    elif bearish:
        entry = current_price
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
                bot.send_message(CHAT_ID, signal)
                print(f"✅ Сигнал отправлен: {signal}")
            time.sleep(3)  # Пауза между активами
        time.sleep(60 * 15)  # Проверка каждые 15 минут

if __name__ == "__main__":
    main_loop()
