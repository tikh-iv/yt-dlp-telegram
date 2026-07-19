FROM python:3.11
LABEL authors="eevarn"

WORKDIR /app

# Install:
#   - ffmpeg: required by yt-dlp for media processing
#   - curl: to download yt-dlp and deno binaries
#   - deno: JavaScript runtime required for YouTube extraction
#           (https://github.com/yt-dlp/yt-dlp/wiki/EJS)
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        curl \
        unzip \
    && curl -fsSL --retry 5 --retry-delay 2 \
           https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp \
           -o /usr/local/bin/yt-dlp \
    && chmod +x /usr/local/bin/yt-dlp \
    && curl -fsSL --retry 5 --retry-delay 2 \
           https://github.com/denoland/deno/releases/latest/download/deno-x86_64-unknown-linux-gnu.zip \
           -o /tmp/deno.zip \
    && unzip -q /tmp/deno.zip -d /tmp \
    && mv /tmp/deno /usr/local/bin/deno \
    && chmod +x /usr/local/bin/deno \
    && rm /tmp/deno.zip \
    && apt-get purge -y --auto-remove unzip \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# bgutil PO Token provider plugin — для обхода YouTube "Sign in to confirm you're not a bot".
# Pinned: major версия plugin ДОЛЖНА совпадать с major версией potoken-service
# (brainicism/bgutil-ytdlp-pot-provider:1.3.1 в docker-compose.yml). При рассинхроне
# plugin молча откажется общаться с сервером. См. https://github.com/yt-dlp/yt-dlp/wiki/Extractors#po-token-guide
RUN pip install --no-cache-dir bgutil-ytdlp-pot-provider==1.3.1

COPY openssl-reduced.cnf /etc/ssl/openssl-reduced.cnf
COPY . .
RUN chmod +x /app/entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["python", "main.py"]
