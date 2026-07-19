#!/bin/sh
set -e

yt-dlp -U || true

# Подкладываем cookies в writable-путь, чтобы yt-dlp мог сохранить сессию туда,
# не падая на read-only маунте config:/app/config:ro.
# Источник /app/config/cookies.txt — монтируется с хоста (только чтение),
# приёмник /app/cookies/cookies.txt — writable (внутри слоя контейнера).
mkdir -p /app/cookies
if [ -f /app/config/cookies.txt ]; then
    cp /app/config/cookies.txt /app/cookies/cookies.txt
fi

exec "$@"
