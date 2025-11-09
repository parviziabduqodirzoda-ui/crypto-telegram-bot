import os
import requests
from flask import Flask, request
from pybit.unified_trading import HTTP
from dotenv import load_dotenv

# ==============================
# Загружаем .env переменные
# ==============================
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
BYBIT_API_KEY = os.getenv("BYBIT_API_KEY")
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET")
PROXY_URL = os.getenv("PROXY_URL")

# ==============================
# Flask app
# ==============================
app = Flask(__name__)

# ==============================
# Настройка сессии с прокси
# ==============================
session = requests.Session()
if PROXY_URL:
    session.proxies = {
        "http": PROXY_URL,
        "https": PROXY_URL
    }

# ==============================
# Подключаемся к Bybit
# ==============================
client = HTTP(
    testnet=False,  # если используешь реальный Bybit, ставь False
    api_key=BYBIT_API_KEY,
    api_secret=BYBIT_API_SECRET,
    request_timeout=10,
    session=session
)

# ==============================
# Телеграм API
# ==============================
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

def send_message(chat_id, text, reply_markup=None):
    """Отправка сообщений в Telegram"""
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    requests.post(f"{TELEGRAM_API}/sendMessage", json=payload)

# ==============================
# Главная логика
# ==============================
@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    data = request.get_json()

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
            return "ok"

        elif text == "💰 price" or text == "price":
            try:
                ticker = client.get_tickers(category="spot", symbol="BTCUSDT")
                price = ticker["result"]["list"][0]["lastPrice"]
                send_message(chat_id, f"💎 Текущая цена BTC/USDT: *{price}* $")
            except Exception as e:
                send_message(chat_id, f"Ошибка при получении цены: {e}")

        elif text == "ℹ️ help" or text == "help":
            send_message(chat_id, "Доступные команды:\n- 💰 Price — узнать цену BTC\n- ℹ️ Help — помощь")

        else:
            send_message(chat_id, "Неизвестная команда. Нажми /start для меню.")

    return "ok"


@app.route("/", methods=["GET"])
def index():
    return "Bot is running!", 200


if __name__ == "__main__":
    # Устанавливаем вебхук
    if WEBHOOK_URL:
        webhook_url = f"{WEBHOOK_URL}/{BOT_TOKEN}"
        r = requests.get(f"{TELEGRAM_API}/setWebhook?url={webhook_url}")
        print(f"Webhook set: {r.text}")

    app.run(host="0.0.0.0", port=10000)
