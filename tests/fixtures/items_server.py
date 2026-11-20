"""Disposable loopback-only API used to prove configuration-only API onboarding.

The requirements in examples/items/openapi.yaml and requirements.md are the test
oracle. This server is an independently implemented test double, not an oracle.
Faults deliberately violate that contract to demonstrate failure detection.
"""

from __future__ import annotations

import argparse
import json
import secrets
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit


FAULTS = (
    "wrong_owner", "wrong_type", "missing_field", "server_error", "non_json",
    "cleanup_error", "experience",
)


class _ItemsHTTPServer(ThreadingHTTPServer):
    # Buffer concurrent case connections while the accept loop starts handlers.
    request_queue_size = 64


class ItemsServer:
    """Context manager exposing a fresh in-memory service and request audit."""

    def __init__(self, *, port: int = 0, fault: str | None = None):
        if fault is not None and fault not in FAULTS:
            raise ValueError(f"Unknown fault: {fault}")
        self.fault = fault
        self.tokens: dict[str, str] = {}
        self.items: dict[int, dict] = {}
        self.requests: list[dict] = []
        self._next_id = 1
        self._lock = threading.Lock()
        service = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "ItemsTestFixture/1.0"

            def log_message(self, format, *args):
                pass

            def _reply(self, status: int, body=None, *, raw: bytes | None = None):
                if raw is not None:
                    data = raw
                    content_type = "text/plain; charset=utf-8"
                elif body is None:
                    data = b""
                    content_type = "application/json"
                else:
                    data = json.dumps(body).encode("utf-8")
                    content_type = "application/json"
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _body(self):
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if length < 0 or length > 65536:
                        raise ValueError("Body too large")
                    return True, json.loads(self.rfile.read(length))
                except (ValueError, UnicodeDecodeError):
                    self._reply(400, {"error": "invalid_json"})
                    return False, None

            def _route(self):
                path = urlsplit(self.path).path
                with service._lock:
                    service.requests.append({"method": self.command, "path": path})
                if path == "/session" and self.command == "POST":
                    valid, body = self._body()
                    if not valid:
                        return
                    if (not isinstance(body, dict)
                            or not isinstance(body.get("owner"), str)
                            or not body["owner"]):
                        return self._reply(422, {"error": "invalid_owner"})
                    token = secrets.token_urlsafe(24)
                    with service._lock:
                        service.tokens[token] = body["owner"]
                    return self._reply(200, {"token": token})

                token = self.headers.get("Authorization", "")
                owner = service.tokens.get(token[7:]) if token.startswith("Bearer ") else None
                if not owner:
                    return self._reply(401, {"error": "unauthorized"})

                if path == "/items" and self.command == "POST":
                    valid, body = self._body()
                    if not valid:
                        return
                    if not isinstance(body, dict):
                        return self._reply(422, {"error": "invalid_item"})
                    name, quantity, kind = body.get("name"), body.get("quantity"), body.get("kind")
                    if (not isinstance(name, str) or not 1 <= len(name) <= 24
                            or type(quantity) is not int or not 1 <= quantity <= 5
                            or kind not in ("book", "tool")
                            or set(body) - {"name", "quantity", "kind"}):
                        return self._reply(422, {"error": "invalid_item"})
                    with service._lock:
                        if any(item["owner"] == owner and item["name"] == name
                               for item in service.items.values()):
                            return self._reply(409, {"error": "duplicate_name"})
                        item_id = service._next_id
                        service._next_id += 1
                        item = {"id": item_id, "name": name, "quantity": quantity,
                                "kind": kind, "owner": owner}
                        service.items[item_id] = item
                    return self._reply(201, item)

                if path.startswith("/items/") and self.command in ("GET", "DELETE"):
                    try:
                        item_id = int(path.removeprefix("/items/"))
                    except ValueError:
                        return self._reply(404, {"error": "not_found"})
                    item = service.items.get(item_id)
                    if item is None or item["owner"] != owner:
                        return self._reply(404, {"error": "not_found"})
                    if self.command == "DELETE":
                        if service.fault == "cleanup_error":
                            return self._reply(500, {"error": "injected_cleanup_error"})
                        with service._lock:
                            del service.items[item_id]
                        return self._reply(204)
                    fault = service.fault
                    if fault == "experience":
                        fault = self.headers.get("X-Demo-Fault")
                        if fault == 'disconnect':
                            self.close_connection = True
                            self.connection.shutdown(socket.SHUT_RDWR)
                            self.connection.close()
                            return
                    if fault == "server_error":
                        return self._reply(503, {"error": "injected_service_unavailable"})
                    if fault == "non_json":
                        return self._reply(200, raw=b"injected non-json upstream response")
                    result = item.copy()
                    if fault == "wrong_owner":
                        result["owner"] = "another_user"
                    elif fault == "wrong_type":
                        result["quantity"] = str(result["quantity"])
                    elif fault == "missing_field":
                        del result["name"]
                    return self._reply(200, result)
                return self._reply(404, {"error": "not_found"})

            do_POST = _route
            do_GET = _route
            do_DELETE = _route

        self.httpd = _ItemsHTTPServer(("127.0.0.1", port), Handler)
        self.httpd.daemon_threads = True
        self.base_url = f"http://127.0.0.1:{self.httpd.server_port}"
        self._thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def start(self):
        self._thread.start()
        return self

    def close(self):
        if self._thread.is_alive():
            self.httpd.shutdown()
            self._thread.join(timeout=3)
        self.httpd.server_close()
        self.tokens.clear()
        self.items.clear()

    def __enter__(self):
        return self.start()

    def __exit__(self, *_):
        self.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=18082)
    parser.add_argument("--fault", choices=FAULTS)
    arguments = parser.parse_args()
    with ItemsServer(port=arguments.port, fault=arguments.fault) as running:
        print(f"Local disposable items API: {running.base_url}", flush=True)
        print("Ctrl+C discards all in-memory data.", flush=True)
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            pass
