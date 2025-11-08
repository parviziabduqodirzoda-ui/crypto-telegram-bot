import telebot
from flask import Flask, request
import os

TOKEN = os.environ.get("BOT_TOKEN")  # токен из переменных окружения
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# --- Обработчик команды /start ---
@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id, "Бот запущен! ✅")

# --- Flask маршруты для Render ---
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
