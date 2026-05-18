#!/bin/sh
set -e

# Clamp TCP MSS to prevent Docker overlay MTU black hole
# Container MTU 1400 => MSS 1360 (1400 - 40 TCP/IP headers)
iptables -A OUTPUT -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --set-mss 1360 2>/dev/null || true

yt-dlp -U || true

exec "$@"
