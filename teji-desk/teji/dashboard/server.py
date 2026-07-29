"""Tiny stdlib dashboard server: serves the live UI + JSON state + a settings API.

Endpoints:
  GET  /                 the dashboard
  GET  /api/state        full state snapshot (polled ~1/s)
  POST /api/config       runtime controls (timeframe / toggle / trade_all / kill)
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

_STATIC = Path(__file__).parent / "static"


def make_server(state, controller, host: str, port: int) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body: bytes, ctype: str):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code, obj):
            self._send(code, json.dumps(obj).encode(), "application/json")

        def do_GET(self):
            if self.path.startswith("/api/state"):
                return self._json(200, state.snapshot())
            if self.path in ("/", "", "/index.html"):
                return self._send(200, (_STATIC / "index.html").read_bytes(),
                                  "text/html; charset=utf-8")
            return self._send(404, b"not found", "text/plain")

        def do_POST(self):
            if not self.path.startswith("/api/config"):
                return self._send(404, b"not found", "text/plain")
            try:
                n = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(n) or b"{}")
            except Exception as exc:
                return self._json(400, {"ok": False, "error": f"bad body: {exc}"})

            action = body.get("action")
            try:
                if action == "timeframe":
                    res = controller.set_timeframe(int(body["value"]))
                elif action == "toggle":
                    res = controller.toggle(body["symbol"], bool(body["enabled"]))
                elif action == "trade_all":
                    res = controller.trade_all(bool(body["enabled"]))
                elif action == "kill":
                    res = controller.engage_kill()
                else:
                    res = {"ok": False, "error": f"unknown action {action}"}
            except Exception as exc:
                res = {"ok": False, "error": str(exc)}
            return self._json(200, res)

    return ThreadingHTTPServer((host, port), Handler)


def serve_in_background(state, controller, host: str, port: int) -> ThreadingHTTPServer:
    httpd = make_server(state, controller, host, port)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd
