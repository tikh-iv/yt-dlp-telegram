import redis
import json
import os
import logging
from typing import Dict
import requests
from fastapi import HTTPException

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Подключение к Redis
redis_client = redis.Redis(host=os.getenv("REDIS_HOST", "redis"), port=6379, db=0)


# Чтение токена Telegram из секрета
def get_telegram_token() -> str:
    try:
        with open("/run/secrets/telegram_token", "r") as secret_file:
            return secret_file.read().strip()
    except Exception as e:
        logger.error(f"Error reading Telegram token: {e}")
        raise HTTPException(status_code=500, detail="Failed to load Telegram token")


TELEGRAM_TOKEN = get_telegram_token()
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"


def send_message(chat_id: str, text: str) -> None:
    """Отправить текстовое сообщение в Telegram."""
    try:
        response = requests.post(
            f"{TELEGRAM_API_URL}/sendMessage",
            json={"chat_id": chat_id, "text": text}
        )
        response.raise_for_status()
        logger.info(f"Message sent to chat {chat_id}: {text}")
    except requests.RequestException as e:
        logger.error(f"Failed to send message to chat {chat_id}: {e}")
        raise


def send_video(chat_id: str, video_path: str) -> None:
    """Отправить видео в Telegram."""
    try:
        with open(video_path, "rb") as video_file:
            response = requests.post(
                f"{TELEGRAM_API_URL}/sendVideo",
                data={"chat_id": chat_id},
                files={"video": video_file}
            )
            response.raise_for_status()
        logger.info(f"Video sent to chat {chat_id}: {video_path}")
    except requests.RequestException as e:
        logger.error(f"Failed to send video to chat {chat_id}: {e}")
        raise
    except FileNotFoundError as e:
        logger.error(f"Video file not found: {video_path}")
        raise


def process_result(result: Dict) -> None:
    """Обработать результат из очереди."""
    task_id = result.get("task_id")
    chat_id = result.get("chat_id")
    status = result.get("status")

    logger.info(f"Processing result for task {task_id}, chat {chat_id}")

    try:
        if status == "completed":
            file_path = result.get("file_path")
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"Video file not found: {file_path}")

            # Отправить видео
            send_video(chat_id, file_path)

            # Удалить файл после отправки
            os.remove(file_path)
            logger.info(f"File deleted: {file_path}")

            # Отправить сообщение об успехе
            send_message(chat_id, f"Video for task {task_id} successfully sent!")
        elif status == "failed":
            error = result.get("error", "Unknown error")
            send_message(chat_id, f"Failed to download video for task {task_id}: {error}")
        else:
            logger.warning(f"Unknown status for task {task_id}: {status}")
            send_message(chat_id, f"Unknown status for task {task_id}. Please contact support.")
    except Exception as e:
        logger.error(f"Error processing task {task_id}: {e}")
        send_message(chat_id, f"Error processing task {task_id}: {str(e)}")


def main():
    """Основной цикл обработки результатов."""
    logger.info("Starting telegram-service...")
    while True:
        try:
            # Извлечь результат из очереди (блокирующий вызов)
            result = redis_client.blpop("download_results")
            result_data = json.loads(result[1])
            process_result(result_data)
        except Exception as e:
            logger.error(f"Error in main loop: {e}")
            continue


if __name__ == "__main__":
    main()