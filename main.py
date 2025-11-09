import os
import logging
from flask import Flask, request
import telebot
from telebot import types
from pybit.unified_trading import HTTP

# Настройки логов
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Загружаем переменные окружения
BOT_TOKEN = os.getenv("BOT_TOKEN")
BYBIT_API_KEY = os.getenv("BYBIT_API_KEY")
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET")
USE_TESTNET = os.getenv("USE_TESTNET", "False").lower() == "true"

# Проверяем переменные
if not BOT_TOKEN or not BYBIT_API_KEY or not BYBIT_API_SECRET:
    logger.error("❌ Не найдены ключи в переменных окружения. Проверь Render Environment Variables.")
    exit(1)

# Подключение к Bybit API
session = HTTP(
    testnet=USE_TESTNET,
    api_key=BYBIT_API_KEY,
    api_secret=BYBIT_API_SECRET,
)

# Telegram Bot
bot = telebot.TeleBot(BOT_TOKEN)
ADMIN_ID = 5198342012

# Flask для Render
app = Flask(__name__)

# Список торговых пар
symbols = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
    "DOGEUSDT", "ADAUSDT", "TRXUSDT", "DOTUSDT", "AVAXUSDT",
    "MATICUSDT", "LTCUSDT", "LINKUSDT", "BCHUSDT", "UNIUSDT",
    "ATOMUSDT", "XLMUSDT", "FILUSDT", "NEARUSDT", "ALGOUSDT"
]

# 🟢 Команда /start
@bot.message_handler(commands=["start"])
def start(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn1 = types.KeyboardButton("Price")
    markup.add(btn1)
    bot.send_message(message.chat.id, "🤖 Бот запущен! Нажми 'Price', чтобы получить котировки.", reply_markup=markup)
    logger.info(f"Пользователь {message.chat.id} запустил бота.")


# 📈 Обработка кнопки /price
@bot.message_handler(func=lambda message: message.text.lower() == "price" or message.text.lower() == "/price")
def get_prices(message):
    logger.info(f"Запрос цен от пользователя {message.chat.id}")
    try:
        prices = []
        for symbol in symbols:
            try:
                data = session.get_tickers(category="linear", symbol=symbol)
                price = data["result"]["list"][0]["lastPrice"]
                prices.append(f"{symbol}: {price}")
            except Exception as e:
                prices.append(f"{symbol}: ошибка ❌ ({e})")
        price_message = "💰 *Актуальные цены:*\n\n" + "\n".join(prices)
        bot.send_message(message.chat.id, price_message, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Ошибка получения цен: {e}")
        bot.send_message(message.chat.id, f"⚠️ Ошибка при получении данных: {e}")


# 🧠 Проверка живости (Render healthcheck)
@app.route("/", methods=["GET", "POST"])
def webhook():
    if request.method == "POST":
        update = telebot.types.Update.de_json(request.stream.read().decode("utf-8"))
        bot.process_new_updates([update])
        return "OK", 200
    else:
        return "✅ Бот работает!", 200


if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    logger.info(f"🚀 Бот запущен на порту {port}")
    app.run(host="0.0.0.0", port=port)
