import telebot
import requests
import time

import os
BOT_TOKEN = os.environ.get("BOT_TOKEN")
bot = telebot.TeleBot(BOT_TOKEN)

@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "Бот работает! Получаю данные с Bybit...")

def get_price(symbol="BTCUSDT"):
    url = f"https://api.bybit.com/v5/market/tickers?category=spot&symbol={symbol}"
    data = requests.get(url).json()
    try:
        return float(data["result"]["list"][0]["lastPrice"])
    except Exception:
        return None

@bot.message_handler(commands=['price'])
def price(message):
    price_btc = get_price("BTCUSDT")
    price_eth = get_price("ETHUSDT")
    price_xaut = get_price("XAUTUSDT")
    bot.reply_to(
        message,
        f"💰 Актуальные цены:\n\n"
        f"BTC/USDT: {price_btc}\n"
        f"ETH/USDT: {price_eth}\n"
        f"XAUT/USDT: {price_xaut}"
    )

while True:
    try:
        bot.polling(none_stop=True, interval=3)
    except Exception as e:
        print("Ошибка:", e)
        time.sleep(5)
