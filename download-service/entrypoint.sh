#!/bin/sh
set -e

yt-dlp -U || true

exec "$@"
