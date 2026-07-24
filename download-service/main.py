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
    """Скачать видео через yt-dlp и вернуть путь к mp4 с H.264 + AAC.

    Стратегия — получить файл, который Telegram примет как видео (не как документ):
    Telegram Bot API надёжно проигрывает только MP4 с H.264 видео и AAC аудио.
    Любые другие комбинации (VP9/AV1 + Opus в webm/mp4) он отправляет как файл.

    1) Селектор предпочитает H.264+AAC форматы — на YouTube/X/TikTok они есть,
       файл скачивается сразу в нужном виде, без перекодировки.
    2) Если источник отдаёт только не-H.264 (Instagram — только VP9),
       селектор берёт лучший доступный, а после скачивания мы транскодируем
       его в H.264+AAC через ffmpeg. Это медленнее (~10-30с на короткий ролик),
       но иначе Telegram не покажет видео.

    Ограничение по размеру НЕ в селекторе: у DASH-форматов filesize=None заранее,
    фильтр [filesize<...] их отбросит (старый баг). Проверяем post-download.
    """
    # Сначала пытаемся взять H.264+AAC напрямую; fallback — любой лучший.
    format_spec = "bestvideo*[vcodec^=avc]+bestaudio[acodec^=mp4a]/best"
    subprocess.run(
        ["yt-dlp", "--impersonate", "chrome", "-f", format_spec, url, "-o", output_template,
         *cookies_args(), *potoken_args()],
        check=True,
    )
    unique_id = os.path.basename(output_template).split(".")[0]
    downloaded = None
    for file in os.listdir(DOWNLOAD_DIR):
        if file.startswith(unique_id):
            downloaded = os.path.join(DOWNLOAD_DIR, file)
            break
    if not downloaded:
        raise Exception("Downloaded file not found")

    # Если файл уже в нужном формате (H.264+AAC) — отдаём как есть.
    if is_telegram_friendly_mp4(downloaded):
        return downloaded

    # Иначе транскодируем в H.264+AAC mp4. Старый файл удаляем.
    logger.info(f"Transcoding to H.264+AAC mp4 (source: {downloaded})")
    target = downloaded.rsplit(".", 1)[0] + ".mp4"
    # Если source уже .mp4 (но с vp9/av1 внутри), пишем в temp, потом заменяем.
    if os.path.exists(target) and os.path.samefile(target, downloaded):
        target = downloaded + ".h264.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-i", downloaded,
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
         "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "128k",
         "-movflags", "+faststart",
         target],
        check=True, capture_output=True,
    )
    if target != downloaded:
        os.remove(downloaded)
    # Нормализуем имя: .h264.mp4 → .mp4
    if target.endswith(".h264.mp4"):
        final = target.replace(".h264.mp4", ".mp4")
        os.rename(target, final)
        target = final
    return target

def is_telegram_friendly_mp4(file_path: str) -> bool:
    """True, если файл — mp4 с H.264 видео и AAC аудио (Telegram играет как видео)."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error",
             "-select_streams", "v:0",
             "-show_entries", "stream=codec_name:format=format_name",
             "-of", "json", file_path],
            capture_output=True, text=True, timeout=15, check=True,
        )
        data = json.loads(result.stdout)
        stream = (data.get("streams") or [{}])[0]
        fmt_name = data.get("format", {}).get("format_name", "")
        vcodec = (stream.get("codec_name") or "").lower()
        # format_name может быть "mov,mp4,m4a,..."; нас интересует наличие mp4
        is_mp4 = "mp4" in fmt_name or "mov" in fmt_name
        if not is_mp4 or vcodec not in ("h264", "avc"):
            return False
        # Проверяем аудио-кодек (если аудио есть)
        aresult = subprocess.run(
            ["ffprobe", "-v", "error",
             "-select_streams", "a:0",
             "-show_entries", "stream=codec_name",
             "-of", "default=noprint_wrappers=1:nokey=1", file_path],
            capture_output=True, text=True, timeout=15, check=True,
        )
        acodec = (aresult.stdout or "").strip().lower()
        # Если аудио нет — это всё ещё OK (беззвучное видео). Если есть — должно быть AAC.
        return not acodec or acodec in ("aac", "mp4a")
    except Exception as e:
        logger.warning(f"is_telegram_friendly_mp4 probe failed for {file_path}: {e}")
        return False

def probe_video_meta(file_path: str) -> Dict:
    """Извлечь width/height/duration видео через ffprobe.

    Возвращает {} при ошибке — отправка в Telegram продолжится без метаданных
    ( Telegram сам попробует определить, как сейчас).
    """
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error",
             "-select_streams", "v:0",
             "-show_entries", "stream=width,height:format=duration",
             "-of", "json", file_path],
            capture_output=True, text=True, timeout=15, check=True,
        )
        data = json.loads(result.stdout)
        stream = (data.get("streams") or [{}])[0]
        fmt = data.get("format") or {}
        return {
            "width": int(stream["width"]) if stream.get("width") else None,
            "height": int(stream["height"]) if stream.get("height") else None,
            "duration": int(float(fmt["duration"])) if fmt.get("duration") else None,
        }
    except Exception as e:
        logger.warning(f"ffprobe failed for {file_path}: {e}")
        return {}

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

        # Извлекаем метаданные для Telegram sendVideo.
        # Без явных width/height/duration Telegram часто промахивается с aspect
        # ratio (показывает вертикальное видео квадратным 320x320) и duration=0
        # (видео не воспроизводится, только превью). Передаём их через Redis.
        video_meta = probe_video_meta(file_path)

        # Send result to redis
        result = {
            "task_id": task_id,
            "chat_id": chat_id,
            "status": "completed",
            "file_path": file_path,
            "width": video_meta.get("width"),
            "height": video_meta.get("height"),
            "duration": video_meta.get("duration"),
        }
        redis_client.rpush("download_results", json.dumps(result))
        logger.info(
            f"Task {task_id} completed: {file_path} "
            f"({video_meta.get('width')}x{video_meta.get('height')}, "
            f"{video_meta.get('duration')}s)"
        )

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