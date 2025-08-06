import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from langchain_gigachat import GigaChat
from langchain_core.messages import HumanMessage, AIMessage
from dotenv import load_dotenv
import os
import uuid
import random
import io
import subprocess
import tempfile
from mimetypes import guess_type

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

# Хранилище данных чата
chat_data = {}

# Хранилище кастомного кэша
custom_cache = {}

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    session_id = str(uuid.uuid4())
    chat_data[chat_id] = {"messages": [], "session_id": session_id}
    await update.message.reply_text("Привет! Я бот, использующий GigaChat. Отправь текст, фото или любой файл, и я помогу!")

# Обработка текстовых сообщений
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_message = update.message.text.lower()

    if chat_id not in chat_data:
        chat_data[chat_id] = {"messages": [], "session_id": str(uuid.uuid4())}

    chat_data[chat_id]["messages"].append(HumanMessage(content=user_message))
    logger.info(f"Получено сообщение в чате {chat_id}: {user_message}")

    try:
        messages = chat_data[chat_id]["messages"].copy()
        logger.info(f"Отправка сообщений в GigaChat: {messages}")

        if user_message in custom_cache and random.random() < 0.5:
            response = AIMessage(content=custom_cache[user_message])
            logger.info(f"Ответ из кастомного кэша: {response.content}")
        else:
            giga_session = GigaChat(
                credentials=GIGACHAT_AUTH_KEY,
                scope=GIGACHAT_SCOPE,
                verify_ssl_certs=False
            )
            response = giga_session.invoke(messages)
            custom_cache[user_message] = response.content
            logger.info(f"Ответ от GigaChat (новый): {response.content}")

        chat_data[chat_id]["messages"].append(AIMessage(content=response.content))
        logger.info(f"Обновленная история: {chat_data[chat_id]['messages']}")

        await update.message.reply_text(response.content)

    except Exception as e:
        logger.error(f"Ошибка при запросе к GigaChat: {e}")
        await update.message.reply_text("Извини, произошла ошибка при обращении к GigaChat.")

# Обработка файлов (документы и фото)
async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    if chat_id not in chat_data:
        chat_data[chat_id] = {"messages": [], "session_id": str(uuid.uuid4())}

    try:
        # Проверка на фото
        if update.message.photo:
            photo = update.message.photo[-1]  # Берем фото наилучшего качества
            file = await context.bot.get_file(photo.file_id)
            file_buffer = io.BytesIO()
            await file.download_to_memory(out=file_buffer)
            file_buffer.seek(0)
            mime_type, _ = guess_type(f"file{photo.file_id}.jpg")
            logger.info(f"Определенный mime_type для фото: {mime_type}")
            file_data = file_buffer.getvalue()
            logger.info(f"Размер файла: {len(file_data)} байт")

            # Сохранение файла во временный файл с использованием tempfile
            with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as temp_file:
                temp_file.write(file_data)
                temp_file_path = temp_file.name

            # Выполнение cURL-запроса
            curl_command = [
                "curl", "--location", "--request", "POST",
                "https://gigachat.devices.sberbank.ru/api/v1/files",
                "--header", f"Authorization: Bearer {GIGACHAT_AUTH_KEY}",
                "--form", f"file=@{temp_file_path}",
                "--form", "purpose=general"
            ]
            result = subprocess.run(curl_command, capture_output=True, text=True)
            if result.returncode != 0:
                logger.error(f"Ошибка cURL: {result.stderr}")
                raise Exception("Ошибка загрузки файла через cURL")
            logger.info(f"cURL ответ: {result.stdout}")
            file_data = result.stdout
            import json
            file_info = json.loads(file_data)
            file_id = file_info["id"]
            logger.info(f"Фото загружено, file_id: {file_id}")

            giga_session = GigaChat(
                credentials=GIGACHAT_AUTH_KEY,
                scope=GIGACHAT_SCOPE,
                verify_ssl_certs=False
            )
            messages = [HumanMessage(content=f"Анализируй это изображение: {file_id}")]
            response = giga_session.invoke(messages)
            logger.info(f"Ответ на фото: {response.content}")

            # Удаление временного файла
            import os
            os.remove(temp_file_path)

        # Проверка на документ
        elif update.message.document:
            document = update.message.document
            file = await context.bot.get_file(document.file_id)
            file_buffer = io.BytesIO()
            await file.download_to_memory(out=file_buffer)
            file_buffer.seek(0)
            mime_type = document.mime_type or guess_type(f"file{document.file_id}.{document.file_name.split('.')[-1]}")[0]
            logger.info(f"Определенный mime_type для документа: {mime_type}")
            file_data = file_buffer.getvalue()
            logger.info(f"Размер файла: {len(file_data)} байт")

            # Сохранение файла во временный файл с использованием tempfile
            with tempfile.NamedTemporaryFile(delete=False, suffix=f".{document.file_name.split('.')[-1]}") as temp_file:
                temp_file.write(file_data)
                temp_file_path = temp_file.name

            # Выполнение cURL-запроса
            curl_command = [
                "curl", "--location", "--request", "POST",
                "https://gigachat.devices.sberbank.ru/api/v1/files",
                "--header", f"Authorization: Bearer {GIGACHAT_AUTH_KEY}",
                "--form", f"file=@{temp_file_path}",
                "--form", "purpose=general"
            ]
            result = subprocess.run(curl_command, capture_output=True, text=True)
            if result.returncode != 0:
                logger.error(f"Ошибка cURL: {result.stderr}")
                raise Exception("Ошибка загрузки файла через cURL")
            logger.info(f"cURL ответ: {result.stdout}")
            file_data = result.stdout
            import json
            file_info = json.loads(file_data)
            file_id = file_info["id"]
            logger.info(f"Документ загружен, file_id: {file_id}")

            giga_session = GigaChat(
                credentials=GIGACHAT_AUTH_KEY,
                scope=GIGACHAT_SCOPE,
                verify_ssl_certs=False
            )
            messages = [HumanMessage(content=f"Анализируй этот файл: {file_id}")]
            response = giga_session.invoke(messages)
            logger.info(f"Ответ на документ: {response.content}")

            # Удаление временного файла
            import os
            os.remove(temp_file_path)

        chat_data[chat_id]["messages"].append(AIMessage(content=response.content))
        logger.info(f"Обновленная история: {chat_data[chat_id]['messages']}")
        await update.message.reply_text(response.content)

    except Exception as e:
        logger.error(f"Ошибка при обработке файла: {e}")
        if "unsupported file type" in str(e).lower() or "invalid file" in str(e).lower() or "file format is not supported" in str(e).lower():
            await update.message.reply_text("Извини, этот тип файла не поддерживается GigaChat.")
        else:
            await update.message.reply_text("Извини, произошла ошибка при обработке файла.")

# Обработка ошибок
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} вызвал ошибку: {context.error}")
    if update and update.message:
        await update.message.reply_text("Произошла ошибка. Попробуйте еще раз.")

def main():
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_handler(MessageHandler(filters.PHOTO, handle_file))  # Обработка фото
    application.add_handler(MessageHandler(filters.Document.ALL, handle_file))  # Обработка всех документов
    application.add_error_handler(error_handler)
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()