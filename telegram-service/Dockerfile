FROM python:3.11
LABEL authors="eevarn"

RUN apt-get update && apt-get install -y --no-install-recommends curl unzip && \
    curl -L https://github.com/XTLS/Xray-core/releases/latest/download/Xray-linux-64.zip \
        -o /tmp/xray.zip && \
    unzip /tmp/xray.zip -d /usr/local/bin/ && \
    chmod +x /usr/local/bin/xray && \
    rm /tmp/xray.zip && \
    apt-get purge -y curl unzip && apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chmod +x entrypoint.sh

CMD ["./entrypoint.sh"]
