import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from langchain_community.chat_models import GigaChat
from dotenv import load_dotenv
import os

# Загрузка переменных из файла .env
load_dotenv()

# Получение токенов и данных из переменных окружения
GIGACHAT_AUTH_KEY = os.getenv("GIGACHAT_AUTH_KEY").strip()  # Authorization key из личного кабинета
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

# Проверка, что токены загружены
if not GIGACHAT_AUTH_KEY or not TELEGRAM_TOKEN:
    raise ValueError("Не удалось загрузить GIGACHAT_AUTH_KEY или TELEGRAM_TOKEN из файла .env")

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Инициализация GigaChat клиента
try:
    giga = GigaChat(
        credentials=GIGACHAT_AUTH_KEY,
        scope="GIGACHAT_API_PERS",  # Указываем scope, как в статье
        verify_ssl_certs=False  # Отключаем проверку SSL для тестирования
    )
    logger.info("GigaChat клиент успешно инициализирован")
except Exception as e:
    logger.error(f"Ошибка инициализации GigaChat: {e}")
    raise

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Я бот, использующий GigaChat. Напиши мне что-нибудь, и я отвечу!")

# Обработка текстовых сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    try:
        logger.info(f"Получено сообщение: {user_message}")
        response = giga.invoke(user_message)  # Отправка сообщения в GigaChat
        logger.info(f"Ответ от GigaChat: {response}")
        await update.message.reply_text(str(response.content))
    except Exception as e:
        logger.error(f"Ошибка при запросе к GigaChat: {e}")
        await update.message.reply_text("Извини, произошла ошибка при обращении к GigaChat.")

# Обработка ошибок
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} вызвал ошибку: {context.error}")
    if update and update.message:
        await update.message.reply_text("Произошла ошибка. Попробуйте еще раз.")

def main():
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_error_handler(error_handler)
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()