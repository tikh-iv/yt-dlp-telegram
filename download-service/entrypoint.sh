#!/bin/sh
set -e

# Lower MTU to avoid Docker overlay VXLAN fragmentation issues
ip link set eth0 mtu 1300 2>/dev/null || true

yt-dlp -U || true

exec "$@"
