import os
import requests
import logging
from flask import Flask, request
from pybit.unified_trading import HTTP
from dotenv import load_dotenv

# ------------------------
# Настройки
# ------------------------
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
BYBIT_API_KEY = os.getenv("BYBIT_API_KEY")
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET")
PROXY_URL = os.getenv("PROXY_URL")

logging.basicConfig(level=logging.INFO)
app = Flask(__name__)

# ------------------------
# Настройка прокси
# ------------------------
session = requests.Session()
if PROXY_URL:
    session.proxies = {
        "http": PROXY_URL,
        "https": PROXY_URL
    }
    logging.info(f"Прокси активен: {PROXY_URL}")

# ------------------------
# Подключение к Bybit
# ------------------------
client = HTTP(
    testnet=False,  # True для тестнета, False для реального
    api_key=BYBIT_API_KEY,
    api_secret=BYBIT_API_SECRET,
    session=session
)

# ------------------------
# Telegram API
# ------------------------
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

def send_message(chat_id, text, reply_markup=None):
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        session.post(f"{TELEGRAM_API}/sendMessage", json=payload, timeout=10)
    except Exception as e:
        logging.error(f"Ошибка при отправке сообщения: {e}")

# ------------------------
# Основная логика
# ------------------------
@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    data = request.get_json()
    logging.info(data)

    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        text = data["message"].get("text", "").lower()

        if text == "/start":
            reply_markup = {
                "keyboard": [
                    [{"text": "💰 Price"}],
                    [{"text": "ℹ️ Help"}]
                ],
                "resize_keyboard": True
            }
            send_message(chat_id, "Привет! 👋 Я бот для Bybit.\nВыбери действие:", reply_markup)

        elif text in ["💰 price", "price"]:
            try:
                ticker = client.get_tickers(category="spot", symbol="BTCUSDT")
                price = ticker["result"]["list"][0]["lastPrice"]
                send_message(chat_id, f"💎 Текущая цена BTC/USDT: *{price}* $")
            except Exception as e:
                logging.error(f"Ошибка при получении цены BTCUSDT: {e}")
                send_message(chat_id, "❌ Ошибка при получении цены. Возможна блокировка IP.")

        elif text in ["ℹ️ help", "help"]:
            send_message(chat_id, "📖 Команды:\n- 💰 Price — узнать цену BTC\n- ℹ️ Help — помощь")

        else:
            send_message(chat_id, "Неизвестная команда. Нажми /start для меню.")

    return "ok"

# ------------------------
# Главная страница
# ------------------------
@app.route("/", methods=["GET"])
def index():
    return "Bot is running!", 200

# ------------------------
# Запуск
# ------------------------
if __name__ == "__main__":
    if WEBHOOK_URL:
        webhook_url = f"{WEBHOOK_URL}/{BOT_TOKEN}"
        r = requests.get(f"{TELEGRAM_API}/setWebhook?url={webhook_url}")
        logging.info(f"🌐 Вебхук установлен: {webhook_url}")
        logging.info(f"Ответ Telegram: {r.text}")

    app.run(host="0.0.0.0", port=10000)
