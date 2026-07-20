import redis
import json
import subprocess
import os
import uuid
import logging
from typing import List, Dict

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

DOWNLOAD_DIR = "downloads"
# Опциональные cookies для yt-dlp (обход Sign in to confirm you're not a bot).
# Если файла нет — yt-dlp запускается без --cookies (текущее поведение).
#
# Путь должен быть writable: yt-dlp при завершении сохраняет сессию обратно
# в этот файл (cookies.save). Read-only маунт config:/app/config:ro ломает это
# с OSError [Errno 30] Read-only file system.
# Поэтому entrypoint.sh копирует /app/config/cookies.txt (read-only с хоста)
# в /app/cookies/cookies.txt (writable слой контейнера).
COOKIES_FILE = os.getenv("COOKIES_FILE", "/app/cookies/cookies.txt")
# URL bgutil PO Token provider (сервис potoken-service в docker-compose).
# PO Token нужен YouTube с 2025-2026 — без него даже с валидными cookies
# видео возвращают LOGIN_REQUIRED ("Sign in to confirm you're not a bot").
# Plugin (bgutil-ytdlp-pot-provider, ставится в Dockerfile) сам стучится к этому URL.
# Пустое значение отключает PO Token.
POTOKEN_URL = os.getenv("POTOKEN_URL", "http://potoken-service:4416")
MAX_FILE_SIZE_MB = 100
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024  # 50 MB в байтах

# Подключение к Redis
redis_client = redis.Redis(host=os.getenv("REDIS_HOST", "redis"), port=6379, db=0)

if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)


def cookies_args() -> List[str]:
    """Вернуть аргументы yt-dlp для cookies, если файл существует.

    Делается один log на старте, чтобы было видно в логах, используются cookies или нет.
    Возвращает ["--cookies", path] или [].
    """
    if os.path.isfile(COOKIES_FILE):
        return ["--cookies", COOKIES_FILE]
    return []

def potoken_args() -> List[str]:
    """Вернуть аргументы yt-dlp для bgutil PO Token provider, если URL задан.

    Namespace именно `youtubepot-bgutilhttp` (не `youtube`) — это сам plugin,
    а не youtube extractor. base_url указывает на potoken-service.
    При пустом POTOKEN_URL возвращает [] (PO Token выключен).
    """
    if POTOKEN_URL:
        return ["--extractor-args", f"youtubepot-bgutilhttp:base_url={POTOKEN_URL}"]
    return []

def download_video(url: str, output_template: str) -> str:
    """Скачать видео через yt-dlp с нативным формат-селектором.

    Раньше выбор формата делался в Python (get_formats + select_best_format_under_size),
    но это ломалось на DASH-источниках (Instagram/YouTube): фильтр `vcodec != none
    AND acodec != none` выбрасывал все современные video-only DASH-форматы, и бот
    падал на fallback к CDN-ссылкам с `unknown` кодеком/разрешением — оттуда
    квадратные/растянутые ролики.

    Теперь селектор формата полностью delegируем yt-dlp:
      - `bestvideo*+bestaudio/best` — лучший видеоформат (включая DASH video-only)
        склеивается с лучшим аудио через ffmpeg; если склейка невозможна — берётся
        лучший combined-формат.
      - Ограничение по размеру: yt-dlp сам отсечёт форматы тяжелее MAX_FILE_SIZE_BYTES
        через `[filesize<...]`. Размер склеенного файла проверим ещё раз после
        загрузки (см. process_task).
    """
    size_filter = f"[filesize<{MAX_FILE_SIZE_BYTES}]"
    format_spec = f"bestvideo*{size_filter}+bestaudio{size_filter}/best{size_filter}/best"
    subprocess.run(
        ["yt-dlp", "--impersonate", "chrome", "-f", format_spec, url, "-o", output_template,
         *cookies_args(), *potoken_args()],
        check=True,
        capture_output=True,
        text=True,
    )
    unique_id = os.path.basename(output_template).split(".")[0]
    for file in os.listdir(DOWNLOAD_DIR):
        if file.startswith(unique_id):
            return os.path.join(DOWNLOAD_DIR, file)
    raise Exception("Downloaded file not found")

def process_task(task_data: Dict) -> None:
    """
    Get task from Redis
    """
    task_id = task_data["task_id"]
    url = task_data["url"]
    chat_id = task_data["chat_id"]

    logger.info(f"Processing task {task_id} for URL: {url}")

    try:
        unique_id = str(uuid.uuid4())
        output_template = f"{DOWNLOAD_DIR}/{unique_id}.%(ext)s"

        # Download video (yt-dlp сам выбирает лучший формат под размер)
        file_path = download_video(url, output_template)

        # Проверяем размер уже после скачивания: yt-dlp-овский [filesize<...]
        # фильтрует только форматы с известным filesize, но для склеенных
        # DASH (video+audio) размер заранее неизвестен — проверим итог.
        file_size = os.path.getsize(file_path)
        if file_size > MAX_FILE_SIZE_BYTES:
            os.remove(file_path)
            raise Exception(f"File size {file_size / (1024 * 1024):.2f} MB exceeds {MAX_FILE_SIZE_MB} MB")

        # Send result to redis
        result = {
            "task_id": task_id,
            "chat_id": chat_id,
            "status": "completed",
            "file_path": file_path
        }
        redis_client.rpush("download_results", json.dumps(result))
        logger.info(f"Task {task_id} completed successfully")

    except Exception as e:
        # Send errorr message
        result = {
            "task_id": task_id,
            "chat_id": chat_id,
            "status": "failed",
            "error": str(e)
        }
        redis_client.rpush("download_results", json.dumps(result))
        logger.error(f"Task {task_id} failed: {e}")

def main():
    if os.path.isfile(COOKIES_FILE):
        logger.info(f"Starting download-service... (cookies: {COOKIES_FILE})")
    else:
        logger.info(f"Starting download-service... (no cookies file at {COOKIES_FILE})")
    if POTOKEN_URL:
        logger.info(f"Starting download-service... (potoken provider: {POTOKEN_URL})")
    else:
        logger.info(f"Starting download-service... (no potoken provider)")
    while True:
        try:
            # Get task from reddis
            task = redis_client.blpop("download_tasks")
            task_data = json.loads(task[1])
            process_task(task_data)
        except Exception as e:
            logger.error(f"Error in main loop: {e}")
            continue

if __name__ == "__main__":
    main()