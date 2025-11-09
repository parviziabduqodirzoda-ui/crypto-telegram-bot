import telebot
from telebot import types
from flask import Flask, request
import os
from pybit.unified_trading import HTTP

# === Настройки ===
TOKEN = os.environ.get("BOT_TOKEN")
API_KEY = os.environ.get("BYBIT_API_KEY")
API_SECRET = os.environ.get("BYBIT_API_SECRET")

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# === Подключаемся к Bybit ===
session = HTTP(api_key=API_KEY, api_secret=API_SECRET)

# === Активы для мониторинга ===
ASSETS = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
    "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "DOTUSDT", "MATICUSDT",
    "LINKUSDT", "ATOMUSDT", "LTCUSDT", "AAVEUSDT", "NEARUSDT",
    "SUIUSDT", "APTUSDT", "FILUSDT", "ETCUSDT", "INJUSDT"
]

# === Команда /start ===
@bot.message_handler(commands=['start'])
def start(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn1 = types.KeyboardButton("Price")
    markup.add(btn1)
    bot.send_message(message.chat.id,
                     "Бот запущен ✅\n\nНажми кнопку 'Price', чтобы получить текущие цены активов.",
                     reply_markup=markup)

# === Обработка кнопки Price ===
@bot.message_handler(func=lambda message: message.text.lower() == "price")
def send_prices(message):
    prices_text = "📊 *Текущие цены Bybit:*\n\n"
    for symbol in ASSETS:
        try:
            ticker = session.get_tickers(category="linear", symbol=symbol)
            price = float(ticker['result']['list'][0]['lastPrice'])
            prices_text += f"{symbol}: {price:.2f} USDT\n"
        except Exception as e:
            prices_text += f"{symbol}: ❌ Ошибка получения данных\n"

    bot.send_message(message.chat.id, prices_text, parse_mode="Markdown")

# === Flask webhook ===
@app.route('/' + TOKEN, methods=['POST'])
def getMessage():
    json_str = request.stream.read().decode('UTF-8')
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return '!', 200

@app.route('/')
def webhook():
    bot.remove_webhook()
    bot.set_webhook(url=f"https://{os.environ.get('RENDER_EXTERNAL_HOSTNAME')}/{TOKEN}")
    return 'Webhook установлен успешно!', 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
