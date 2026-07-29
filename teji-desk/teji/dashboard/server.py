"""Tiny stdlib dashboard server: serves the live UI + a JSON state endpoint.

No web framework — just http.server on a background thread. The browser polls
`/api/state` once a second and repaints. `/api/kill` drops the KILL file so you
can force-flat from the UI.
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

_STATIC = Path(__file__).parent / "static"


def make_server(state, host: str, port: int) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):  # quiet
            pass

        def _send(self, code, body: bytes, ctype: str):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path.startswith("/api/state"):
                body = json.dumps(state.snapshot()).encode()
                return self._send(200, body, "application/json")
            if self.path.startswith("/api/kill"):
                Path("KILL").write_text("engaged")
                state.halted = True
                return self._send(200, b'{"ok":true}', "application/json")
            # static — this UI is a single self-contained page
            if self.path in ("/", "", "/index.html"):
                f = _STATIC / "index.html"
                return self._send(200, f.read_bytes(), "text/html; charset=utf-8")
            return self._send(404, b"not found", "text/plain")

    httpd = ThreadingHTTPServer((host, port), Handler)
    return httpd


def serve_in_background(state, host: str, port: int) -> ThreadingHTTPServer:
    httpd = make_server(state, host, port)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd
