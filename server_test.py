from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Railway OK\n")
    def log_message(self, fmt, *args):
        print(fmt % args)

port = int(os.environ.get("PORT", "8000"))
print(f"Test server starting on {port}", flush=True)
ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
