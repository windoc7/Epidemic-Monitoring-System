#!/usr/bin/env python
"""
One-time Kakao OAuth helper for issuing a refresh token.

Before running, register this redirect URI in Kakao Developers:
http://localhost:8765/callback
"""

from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import urllib.parse
import urllib.request
from urllib.error import HTTPError
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = BASE_DIR / "config.json"
REDIRECT_URI = "http://localhost:8765/callback"


def load_config(path: Path) -> dict:
    if path.exists():
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    return {}


def save_config(path: Path, config: dict) -> None:
    with path.open("w", encoding="utf-8") as file:
        json.dump(config, file, ensure_ascii=False, indent=2)
        file.write("\n")


class OAuthHandler(BaseHTTPRequestHandler):
    auth_code = None
    auth_error = None

    def log_message(self, format: str, *args) -> None:
        return

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        OAuthHandler.auth_code = params.get("code", [None])[0]
        OAuthHandler.auth_error = params.get("error", [None])[0]

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        if OAuthHandler.auth_code:
            message = "Kakao authorization is complete. You can close this window."
        else:
            message = "Could not receive the Kakao authorization code."
        self.wfile.write(message.encode("utf-8"))


def post_form(url: str, payload: dict[str, str], *, verify_ssl: bool) -> dict:
    data = urllib.parse.urlencode(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded;charset=utf-8"},
    )
    context = None if verify_ssl else ssl._create_unverified_context()
    try:
        with urllib.request.urlopen(request, timeout=30, context=context) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Kakao token request failed: HTTP {error.code} {body}") from error


def main() -> int:
    parser = argparse.ArgumentParser(description="Issue Kakao OAuth tokens for the KDCA notifier.")
    parser.add_argument("--config", default=os.environ.get("KDCA_KAKAO_CONFIG", str(DEFAULT_CONFIG)))
    args = parser.parse_args()

    config_path = Path(args.config)
    config = load_config(config_path)
    rest_api_key = config.get("kakao_rest_api_key") or input("Kakao REST API key: ").strip()
    if not rest_api_key:
        print("ERROR: REST API key is required.", file=sys.stderr)
        return 1

    client_secret = config.get("kakao_client_secret")
    if not client_secret:
        client_secret = input("Kakao Client Secret (press Enter if disabled): ").strip()

    config["kakao_rest_api_key"] = rest_api_key
    if client_secret:
        config["kakao_client_secret"] = client_secret
    else:
        config.pop("kakao_client_secret", None)
    config.setdefault("verify_ssl", False)
    save_config(config_path, config)

    auth_url = "https://kauth.kakao.com/oauth/authorize?" + urllib.parse.urlencode(
        {
            "response_type": "code",
            "client_id": rest_api_key,
            "redirect_uri": REDIRECT_URI,
            "scope": "talk_message",
        }
    )

    print("Make sure this Redirect URI is registered in Kakao Developers:")
    print(REDIRECT_URI)
    print()
    print("Open this URL in your browser and complete Kakao authorization:")
    print(auth_url)
    print()
    print("Waiting for authorization...")

    server = HTTPServer(("localhost", 8765), OAuthHandler)
    while OAuthHandler.auth_code is None and OAuthHandler.auth_error is None:
        server.handle_request()

    if OAuthHandler.auth_error or not OAuthHandler.auth_code:
        print(f"ERROR: Kakao OAuth failed: {OAuthHandler.auth_error}", file=sys.stderr)
        return 1

    payload = {
        "grant_type": "authorization_code",
        "client_id": rest_api_key,
        "redirect_uri": REDIRECT_URI,
        "code": OAuthHandler.auth_code,
    }
    if config.get("kakao_client_secret"):
        payload["client_secret"] = config["kakao_client_secret"]

    token_data = post_form(
        "https://kauth.kakao.com/oauth/token",
        payload,
        verify_ssl=bool(config.get("verify_ssl", False)),
    )
    config["kakao_access_token"] = token_data["access_token"]
    config["kakao_refresh_token"] = token_data["refresh_token"]
    save_config(config_path, config)
    print(f"Saved Kakao tokens to {config_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
