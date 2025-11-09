import os
import logging
from flask import Flask, request
import telebot
from pybit.unified_trading import HTTP

# === Настройка логов ===
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

# === Инициализация Telegram-бота ===
bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# === Подключение к Bybit API ===
session = HTTP(
    testnet=USE_TESTNET,
    api_key=BYBIT_API_KEY,
    api_secret=BYBIT_API_SECRET
)

# === Обработчик сообщений ===
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.reply_to(message, "👋 Привет! Я крипто-бот. Отправь /price <тикер>, чтобы узнать цену.")

@bot.message_handler(commands=['price'])
def get_price(message):
    try:
        parts = message.text.split()
        if len(parts) < 2:
            bot.reply_to(message, "⚠️ Используй формат: /price BTCUSDT")
            return

        symbol = parts[1].upper()
        data = session.get_tickers(category="linear", symbol=symbol)
        price = data['result']['list'][0]['lastPrice']
        bot.reply_to(message, f"💰 Цена {symbol}: {price}")
    except Exception as e:
        logger.error(f"Ошибка при получении цены: {e}")
        bot.reply_to(message, "❌ Не удалось получить данные о цене.")

# === Flask endpoint для Telegram Webhook ===
@app.route(f"/{BOT_TOKEN}", methods=['POST'])
def webhook():
    try:
        json_str = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_str)
        bot.process_new_updates([update])
    except Exception as e:
        logger.error(f"Ошибка в webhook: {e}")
    return 'OK', 200

# === Проверочный маршрут (GET /) ===
@app.route("/", methods=['GET'])
def index():
    return "🚀 Bot is running on Render!", 200

# === Запуск приложения ===
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
