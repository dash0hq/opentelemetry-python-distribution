"""Exercise opentelemetry-instrumentation-requests and exit.

The target is a standard-library HTTP server in a background thread of this
same process. ``http.server`` is not instrumented by anything the distribution
ships, so the only span the outbound call produces is the client span under
test.
"""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

from requests import get


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        body: bytes = b'{"name": "widget"}'
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


def main() -> None:
    server: ThreadingHTTPServer = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    Thread(target=server.serve_forever, daemon=True).start()
    try:
        host, port = server.server_address[0], server.server_address[1]
        response = get(f"http://{host}:{port}/items/7", timeout=10)
        assert response.status_code == 200, response.status_code
        assert response.json() == {"name": "widget"}
    finally:
        server.shutdown()


main()
