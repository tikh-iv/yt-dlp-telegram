import json
import os
import sys
from urllib.parse import urlparse, parse_qs


def parse_vless_url(url: str) -> dict:
    parsed = urlparse(url)
    if parsed.scheme != "vless":
        raise ValueError(f"Expected vless:// URL, got {parsed.scheme}://")

    uuid = parsed.username
    server = parsed.hostname
    port = parsed.port or 443
    params = parse_qs(parsed.query)

    return {
        "uuid": uuid,
        "server": server,
        "port": port,
        "security": params.get("security", ["none"])[0],
        "encryption": params.get("encryption", ["none"])[0],
        "flow": params.get("flow", [""])[0],
        "pbk": params.get("pbk", [""])[0],
        "sni": params.get("sni", [""])[0],
        "sid": params.get("sid", [""])[0],
        "fp": params.get("fp", ["chrome"])[0],
        "type": params.get("type", ["tcp"])[0],
    }


def generate_config(p: dict) -> dict:
    return {
        "log": {"loglevel": "warning"},
        "inbounds": [{
            "port": 1080,
            "protocol": "socks",
            "listen": "127.0.0.1",
            "settings": {"udp": True},
        }],
        "outbounds": [{
            "protocol": "vless",
            "settings": {
                "vnext": [{
                    "address": p["server"],
                    "port": p["port"],
                    "users": [{
                        "id": p["uuid"],
                        "encryption": p["encryption"],
                        "flow": p["flow"],
                    }],
                }]
            },
            "streamSettings": {
                "network": p["type"],
                "security": p["security"],
                "realitySettings": {
                    "serverName": p["sni"],
                    "publicKey": p["pbk"],
                    "shortId": p["sid"],
                    "fingerprint": p["fp"],
                },
            },
        }],
    }


def main():
    url = os.getenv("VLESS_URL", "")
    if not url:
        print("VLESS_URL not set, skipping Xray config generation")
        sys.exit(0)

    try:
        params = parse_vless_url(url)
    except Exception as e:
        print(f"ERROR: Failed to parse VLESS_URL: {e}", file=sys.stderr)
        sys.exit(1)

    config = generate_config(params)

    with open("/app/xray-config.json", "w") as f:
        json.dump(config, f, indent=2)

    print("Xray config generated at /app/xray-config.json")


if __name__ == "__main__":
    main()
