import os
import time
import requests
import telebot
from telebot import types
from flask import Flask, request

# === Telegram токен ===
TOKEN = "7603757075:AAEGAqO0CzWy-0lT-Zp6rjagNvXmxx9CsSs"
bot = telebot.TeleBot(TOKEN)

# === Flask сервер для Render ===
app = Flask(__name__)

# === Список активов для мониторинга ===
ASSETS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
    "DOGEUSDT", "ADAUSDT", "TRXUSDT", "AVAXUSDT", "DOTUSDT",
    "LINKUSDT", "MATICUSDT", "LTCUSDT", "SHIBUSDT", "APTUSDT",
    "NEARUSDT", "TONUSDT", "BCHUSDT", "ATOMUSDT", "SUIUSDT"
]

# === Функция получения цены с Bybit ===
def get_price(symbol):
    try:
        url = f"https://api.bybit.com/v5/market/tickers?category=spot&symbol={symbol}"
        r = requests.get(url, timeout=5)
        data = r.json()
        if "result" in data and data["result"]["list"]:
            return float(data["result"]["list"][0]["lastPrice"])
        else:
            return None
    except Exception:
        return None


# === Команда /start ===
@bot.message_handler(commands=['start'])
def start(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("Price"))
    bot.send_message(
        message.chat.id,
        "👋 Привет! Я крипто-бот.\nНажми «Price», чтобы увидеть текущие цены.",
        reply_markup=markup
    )


# === Кнопка Price ===
@bot.message_handler(func=lambda msg: msg.text and msg.text.lower() == "price")
def send_prices(message):
    bot.send_message(message.chat.id, "📊 Загружаю данные с Bybit...")
    text = "💰 *Текущие цены на 20 активов:*\n\n"
    for symbol in ASSETS:
        price = get_price(symbol)
        if price:
            text += f"▫️ {symbol}: `${price:.3f}`\n"
        else:
            text += f"▫️ {symbol}: _недоступно_\n"
        time.sleep(0.1)
    bot.send_message(message.chat.id, text, parse_mode="Markdown")


# === Flask webhook ===
@app.route(f'/{TOKEN}', methods=['POST'])
def getMessage():
    json_str = request.get_data(as_text=True)
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return 'ok', 200


@app.route('/')
def webhook():
    # Устанавливаем webhook при запуске
    bot.remove_webhook()
    bot.set_webhook(url=f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}/{TOKEN}")
    return "Webhook установлен успешно!", 200


# === Запуск приложения ===
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
