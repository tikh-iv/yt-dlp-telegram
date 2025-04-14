import redis
import json
import subprocess
import os
import uuid
import logging
from typing import List, Dict, Optional

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

DOWNLOAD_DIR = "downloads"
MAX_FILE_SIZE_MB = 50
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024  # 50 MB в байтах

# Подключение к Redis
redis_client = redis.Redis(host=os.getenv("REDIS_HOST", "redis"), port=6379, db=0)

if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

def get_formats(url: str) -> List[Dict]:
    """Получить список форматов видео с видео и аудио."""
    try:
        result = subprocess.run(
            ["yt-dlp", "--dump-json", url],
            capture_output=True,
            text=True,
            check=True
        )
        video_info = json.loads(result.stdout)
        formats = video_info.get("formats", [])
        return [
            fmt for fmt in formats
            if fmt.get("vcodec") != "none" and fmt.get("acodec") != "none"
        ]
    except subprocess.CalledProcessError as e:
        raise Exception(f"Failed to retrieve formats: {e.stderr}")
    except Exception as e:
        raise Exception(f"Error in get_formats: {str(e)}")

def select_best_format_under_size(formats: List[Dict], max_size_bytes: int = MAX_FILE_SIZE_BYTES) -> str:
    """Выбрать лучший формат видео, не превышающий заданный размер."""
    suitable_formats = [
        fmt for fmt in formats
        if fmt.get("filesize") is not None and fmt["filesize"] <= max_size_bytes
    ]

    if suitable_formats:
        suitable_formats.sort(
            key=lambda x: ((x.get("height") or 0), (x.get("tbr") or 0)),
            reverse=True
        )
        return suitable_formats[0]["format_id"]
    else:
        formats_with_size = [fmt for fmt in formats if fmt.get("filesize") is not None]
        if formats_with_size:
            smallest_format = min(formats_with_size, key=lambda x: x["filesize"])
            return smallest_format["format_id"]
        formats.sort(key=lambda x: (x.get("height") or 0))
        return formats[0]["format_id"]

def download_video(url: str, output_template: str, format_id: str) -> str:
    """Скачать видео и вернуть путь к файлу."""
    subprocess.run(
        ["yt-dlp", "-f", format_id, url, "-o", output_template],
        check=True
    )
    for file in os.listdir(DOWNLOAD_DIR):
        if file.startswith(os.path.basename(output_template).split(".")[0]):
            return os.path.join(DOWNLOAD_DIR, file)
    raise Exception("Downloaded file not found")

def process_task(task_data: Dict) -> None:
    """Обработать задачу из очереди."""
    task_id = task_data["task_id"]
    url = task_data["url"]
    chat_id = task_data["chat_id"]

    logger.info(f"Processing task {task_id} for URL: {url}")

    try:
        # Получить форматы видео
        formats = get_formats(url)
        if not formats:
            raise Exception("No suitable formats found")

        # Выбрать лучший формат
        best_format_id = select_best_format_under_size(formats)
        unique_id = str(uuid.uuid4())
        output_template = f"{DOWNLOAD_DIR}/{unique_id}.%(ext)s"

        # Скачать видео
        file_path = download_video(url, output_template, best_format_id)

        # Проверить размер файла
        file_size = os.path.getsize(file_path)
        if file_size > MAX_FILE_SIZE_BYTES:
            os.remove(file_path)
            raise Exception(f"File size {file_size / (1024 * 1024):.2f} MB exceeds {MAX_FILE_SIZE_MB} MB")

        # Отправить результат в очередь
        result = {
            "task_id": task_id,
            "chat_id": chat_id,
            "status": "completed",
            "file_path": file_path
        }
        redis_client.rpush("download_results", json.dumps(result))
        logger.info(f"Task {task_id} completed successfully")

    except Exception as e:
        # Отправить сообщение об ошибке
        result = {
            "task_id": task_id,
            "chat_id": chat_id,
            "status": "failed",
            "error": str(e)
        }
        redis_client.rpush("download_results", json.dumps(result))
        logger.error(f"Task {task_id} failed: {str(e)}")

def main():
    """Основной цикл обработки задач."""
    logger.info("Starting download-service...")
    while True:
        try:
            # Извлечь задачу из очереди (блокирующий вызов)
            task = redis_client.blpop("download_tasks")
            task_data = json.loads(task[1])
            process_task(task_data)
        except Exception as e:
            logger.error(f"Error in main loop: {str(e)}")
            continue

if __name__ == "__main__":
    main()