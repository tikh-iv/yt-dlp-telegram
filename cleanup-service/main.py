import os
import time
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Каталог с downloaded-видео. По умолчанию "downloads" (относительно WORKDIR /app),
# совпадает с тем, что используют download-service и telegram-service.
DOWNLOAD_DIR = os.getenv("DOWNLOAD_DIR", "downloads")
# Файлы старше этого возраста считаются orphan и удаляются.
MAX_AGE_SECONDS = int(os.getenv("MAX_AGE_HOURS", "1")) * 3600
# Как часто сканировать каталог.
INTERVAL = int(os.getenv("CLEANUP_INTERVAL_SECONDS", "600"))


def sweep() -> None:
    """Удалить все файлы в DOWNLOAD_DIR старше MAX_AGE_SECONDS.

    Безопасность против race condition: yt-dlp и send_video непрерывно
    обновляют mtime записываемого/читаемого файла, поэтому активно
    обрабатываемый файл всегда «моложе» порога. См. план в docs/plans.
    """
    now = time.time()
    try:
        entries = os.listdir(DOWNLOAD_DIR)
    except FileNotFoundError:
        logger.warning(f"Download dir disappeared: {DOWNLOAD_DIR}")
        return

    for entry in entries:
        path = os.path.join(DOWNLOAD_DIR, entry)
        # Пропускаем подкаталоги — чистим только файлы (видео, .part, .ytdl).
        if not os.path.isfile(path):
            continue
        try:
            age = now - os.path.getmtime(path)
            if age > MAX_AGE_SECONDS:
                os.remove(path)
                logger.info(f"Removed orphan: {path} (age={age:.0f}s)")
        except FileNotFoundError:
            # Файл исчез между listdir и remove — нормально, другой процесс успел.
            continue
        except OSError as e:
            logger.warning(f"Could not remove {path}: {e}")


def main():
    logger.info(
        f"Starting cleanup-service: dir={DOWNLOAD_DIR} "
        f"max_age={MAX_AGE_SECONDS}s interval={INTERVAL}s"
    )
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    while True:
        try:
            sweep()
        except Exception as e:
            # Ошибка в одном цикле не должна валить сервис.
            logger.error(f"Sweep error: {e}")
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
