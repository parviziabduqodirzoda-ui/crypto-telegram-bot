import os
import logging
from flask import Flask, request
import telebot
from telebot import types
from pybit.unified_trading import HTTP

# === Логирование ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === Переменные окружения ===
BOT_TOKEN = os.environ.get("BOT_TOKEN")
BYBIT_API_KEY = os.environ.get("BYBIT_API_KEY")
BYBIT_API_SECRET = os.environ.get("BYBIT_API_SECRET")
USE_TESTNET = os.environ.get("USE_TESTNET", "True").lower() == "true"
RENDER_EXTERNAL_HOSTNAME = os.environ.get("RENDER_EXTERNAL_HOSTNAME")

if not BOT_TOKEN or not BYBIT_API_KEY or not BYBIT_API_SECRET:
    raise ValueError("❌ BOT_TOKEN, BYBIT_API_KEY и BYBIT_API_SECRET должны быть заданы в Environment Variables!")

# === Telegram и Flask ===
bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# === Bybit API ===
session = HTTP(
    testnet=USE_TESTNET,
    api_key=BYBIT_API_KEY,
    api_secret=BYBIT_API_SECRET
)

# === Команда /start ===
@bot.message_handler(commands=['start'])
def start(message):
    markup = types.InlineKeyboardMarkup()
    btn_price = types.InlineKeyboardButton("💰 Узнать цену BTCUSDT", callback_data="price_BTCUSDT")
    markup.add(btn_price)
    bot.send_message(message.chat.id, "👋 Привет! Я крипто-бот. Нажми кнопку ниже:", reply_markup=markup)

# === Команда /price вручную ===
@bot.message_handler(commands=['price'])
def price_command(message):
    parts = message.text.split()
    if len(parts) < 2:
        bot.reply_to(message, "⚠️ Используй формат: /price BTCUSDT")
        return

    symbol = parts[1].upper()
    send_price(message.chat.id, symbol)

# === Обработка нажатий на кнопку ===
@bot.callback_query_handler(func=lambda call: call.data.startswith("price_"))
def callback_price(call):
    symbol = call.data.split("_")[1]
    send_price(call.message.chat.id, symbol)
    bot.answer_callback_query(call.id)

# === Универсальная функция получения цены ===
def send_price(chat_id, symbol):
    try:
        data = session.get_tickers(category="linear", symbol=symbol)
        price = data['result']['list'][0]['lastPrice']
        bot.send_message(chat_id, f"💰 Текущая цена {symbol}: {price}")
    except Exception as e:
        logger.error(f"Ошибка при получении цены {symbol}: {e}")
        bot.send_message(chat_id, "❌ Не удалось получить данные о цене.")

# === Flask Webhook ===
@app.route(f"/{BOT_TOKEN}", methods=['POST'])
def webhook():
    json_str = request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return "OK", 200

@app.route("/", methods=['GET'])
def index():
    return "🚀 Bot is running on Render!", 200

# === Точка входа ===
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    logger.info(f"🚀 Бот запущен на порту {port}")

    # Настройка вебхука
    if RENDER_EXTERNAL_HOSTNAME:
        webhook_url = f"https://{RENDER_EXTERNAL_HOSTNAME}/{BOT_TOKEN}"
        bot.remove_webhook()
        bot.set_webhook(url=webhook_url)
        logger.info(f"🌐 Вебхук установлен: {webhook_url}")
    else:
        logger.warning("⚠️ RENDER_EXTERNAL_HOSTNAME не задан, вебхук не установлен.")

    app.run(host="0.0.0.0", port=port)
