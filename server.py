#!/usr/bin/env python
"""Small Railway web service that publishes the latest generated report image."""

from __future__ import annotations

import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from kdca_kakao_report import (
    KDCA_LIST_URL,
    article_text,
    extract_report_summary,
    find_latest_report,
    render_summary_image,
    request_text,
)


BASE_DIR = Path(__file__).resolve().parent
IMAGE_PATH = BASE_DIR / "latest_report.png"


def ensure_report_image() -> None:
    verify_ssl = os.environ.get("VERIFY_SSL", "").strip().lower() in {"1", "true", "yes", "on"}
    report = find_latest_report(request_text(KDCA_LIST_URL, verify_ssl=verify_ssl))
    summary = extract_report_summary(report, article_text(report, verify_ssl=verify_ssl))
    render_summary_image(report, summary, IMAGE_PATH)


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path in {"/", "/health"}:
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"KDCA report image service is running.\n")
            return

        if self.path.startswith("/latest_report.png"):
            ensure_report_image()
            self.path = "/latest_report.png"

        return super().do_GET()


def main() -> None:
    ensure_report_image()
    os.chdir(BASE_DIR)
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"Serving report image on port {port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
