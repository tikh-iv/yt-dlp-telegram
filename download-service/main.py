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

def get_formats(url: str) -> tuple[List[Dict], Optional[float]]:
    """
    Get list of formats and choose native ratio if possible.
    """
    try:
        result = subprocess.run(
            ["yt-dlp", "--dump-json", url],
            capture_output=True,
            text=True,
            check=True
        )
        video_info = json.loads(result.stdout)
        formats = video_info.get("formats", [])
        # Get ratio if possible
        original_aspect_ratio = video_info.get("aspect_ratio")
        if original_aspect_ratio is None:
            # If there is no aspect_ratio try to get from width/height
            width = video_info.get("width")
            height = video_info.get("height")
            if width and height:
                original_aspect_ratio = width / height
        combined_formats = [
            fmt for fmt in formats
            if fmt.get("vcodec") != "none" and fmt.get("acodec") != "none"
        ]
        return combined_formats, original_aspect_ratio
    except subprocess.CalledProcessError as e:
        raise Exception(f"Failed to retrieve formats: {e.stderr}")
    except Exception as e:
        raise Exception(f"Error in get_formats: {str(e)}")

def select_best_format_under_size(formats: List[Dict], original_aspect_ratio: Optional[float] = None, max_size_bytes: int = MAX_FILE_SIZE_BYTES) -> str:
    """
    Choose best format to download.
    """
    def get_format_aspect_ratio(fmt: Dict) -> float:
        aspect_ratio = fmt.get("aspect_ratio")
        if aspect_ratio is not None:
            return aspect_ratio
        width = fmt.get("width")
        height = fmt.get("height")
        if width and height:
            return width / height
        # If no data choose 16:9
        return 16 / 9

    # 1 filter files by size
    suitable_formats = [
        fmt for fmt in formats
        if fmt.get("filesize") is not None and fmt["filesize"] <= max_size_bytes
    ]

    if suitable_formats:
        # 2 if there is original ratio sort by it
        if original_aspect_ratio is not None:
            suitable_formats.sort(
                key=lambda x: (
                    # close to original ratio is better
                    abs(get_format_aspect_ratio(x) - original_aspect_ratio),
                    # than bitrate and quality
                    -(x.get("height") or 0),
                    -(x.get("tbr") or 0)
                )
            )
        else:
            # if there is no original ratio sort by bitrate and quality
            suitable_formats.sort(
                key=lambda x: (
                    -(x.get("height") or 0),
                    -(x.get("tbr") or 0)
                )
            )
        return suitable_formats[0]["format_id"]
    else:
        # Шаг 3: Fallback — known formats
        formats_with_size = [fmt for fmt in formats if fmt.get("filesize") is not None]
        if formats_with_size:
            # sort by size
            if original_aspect_ratio is not None:
                formats_with_size.sort(
                    key=lambda x: (
                        abs(get_format_aspect_ratio(x) - original_aspect_ratio),
                        x["filesize"]
                    )
                )
            else:
                formats_with_size.sort(key=lambda x: x["filesize"])
            return formats_with_size[0]["format_id"]
        # 4 last fallback minimal ratio
        formats.sort(key=lambda x: (x.get("height") or 0))
        return formats[0]["format_id"]

def download_video(url: str, output_template: str, format_id: str) -> str:
    """
    Download video.
    """
    subprocess.run(
        ["yt-dlp", "-f", format_id, url, "-o", output_template],
        check=True
    )
    for file in os.listdir(DOWNLOAD_DIR):
        if file.startswith(os.path.basename(output_template).split(".")[0]):
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
        # Get formats and original ratio
        formats, original_aspect_ratio = get_formats(url)
        if not formats:
            raise Exception("No suitable formats found")

        # Choose the best
        best_format_id = select_best_format_under_size(formats, original_aspect_ratio)
        unique_id = str(uuid.uuid4())
        output_template = f"{DOWNLOAD_DIR}/{unique_id}.%(ext)s"

        # Download video
        file_path = download_video(url, output_template, best_format_id)

        # Choose the size
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
    logger.info("Starting download-service...")
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