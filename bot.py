import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from langchain_gigachat import GigaChat
from langchain_core.messages import HumanMessage, AIMessage
from dotenv import load_dotenv
import os
import uuid
import random  # Добавляем для случайного выбора

# Загрузка переменных из файла .env
load_dotenv()

# Получение токенов и данных из переменных окружения
GIGACHAT_AUTH_KEY = os.getenv("GIGACHAT_AUTH_KEY").strip()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GIGACHAT_SCOPE = os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS")  # Значение по умолчанию

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
        scope=GIGACHAT_SCOPE,
        verify_ssl_certs=False
    )
    logger.info("GigaChat клиент успешно инициализирован")
except Exception as e:
    logger.error(f"Ошибка инициализации GigaChat: {e}")
    raise

# Хранилище данных чата (ключ - chat_id, значение - список сообщений)
chat_data = {}  # Ключ - chat_id, значение - {messages: [], session_id: None}

# Хранилище кастомного кэша (ключ - нормализованное сообщение, значение - ответ)
custom_cache = {}

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    session_id = str(uuid.uuid4())  # Генерируем уникальный X-Session-ID для чата
    chat_data[chat_id] = {"messages": [], "session_id": session_id}
    await update.message.reply_text("Привет! Я бот, использующий GigaChat. Напиши мне что-нибудь, и я отвечу!")

# Обработка текстовых сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_message = update.message.text.lower()  # Нормализация для поиска

    # Инициализация данных для чата, если их нет
    if chat_id not in chat_data:
        chat_data[chat_id] = {"messages": [], "session_id": str(uuid.uuid4())}

    # Добавление нового сообщения пользователя в историю
    chat_data[chat_id]["messages"].append(HumanMessage(content=user_message))
    logger.info(f"Получено сообщение в чате {chat_id}: {user_message}")

    try:
        # Передача истории и нового сообщения в GigaChat
        messages = chat_data[chat_id]["messages"].copy()
        logger.info(f"Отправка сообщений в GigaChat: {messages}")

        if user_message in custom_cache and random.random() < 0.5:  # Используем кэш с вероятностью 50%
            response = AIMessage(content=custom_cache[user_message])
            logger.info(f"Ответ из кастомного кэша: {response.content}")
        else:
            # Создаем новый экземпляр с текущим X-Session-ID
            giga_session = GigaChat(
                credentials=GIGACHAT_AUTH_KEY,
                scope=GIGACHAT_SCOPE,
                verify_ssl_certs=False
            )
            response = giga_session.invoke(messages)
            custom_cache[user_message] = response.content  # Обновляем кэш новым ответом
            logger.info(f"Ответ от GigaChat (новый): {response.content}")

        # Добавление ответа модели в историю
        chat_data[chat_id]["messages"].append(AIMessage(content=response.content))
        logger.info(f"Обновленная история: {chat_data[chat_id]['messages']}")

        await update.message.reply_text(response.content)

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