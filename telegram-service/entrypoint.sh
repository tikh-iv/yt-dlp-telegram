#!/bin/bash
set -e

echo "Generating Xray config..."
python /app/generate-xray-config.py

if [ -f /app/xray-config.json ]; then
  echo "Starting Xray..."
  xray -config /app/xray-config.json &
  XRAY_PID=$!

  sleep 1

  if ! kill -0 $XRAY_PID 2>/dev/null; then
    echo "ERROR: Xray failed to start"
    exit 1
  fi

  echo "Xray running (PID $XRAY_PID), starting bot..."
else
  echo "No Xray config found, starting bot without proxy..."
fi

exec python main.py
