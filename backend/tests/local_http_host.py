"""Offline test harness for frontend integration tests, NOT a Functions host.

Run from backend/: .venv-test/bin/python tests/local_http_host.py
Then frontend/: VITE_API_BASE_URL=http://127.0.0.1:7079/api npm test
Uses the registered Azure Functions handlers with test-only in-memory storage.
No cloud credentials or requests are allowed. Never used by production.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import re
from urllib.parse import urlparse, parse_qsl
from unittest.mock import patch
import azure.functions as func
import support
import function_app
from meeting_service import MeetingService

# Keep optional providers disabled. Existing Jira frontend tests stub that route.
function_app.meetings = MeetingService(function_app.repository)
routes = []
for function in function_app.app.get_functions():
    binding = next((b.get_dict_repr() for b in function.get_bindings() if b.type == "httpTrigger"), None)
    if binding is None: continue
    pattern = re.sub(r"\{(\w+)\}", r"(?P<\1>[^/]+)", binding["route"])
    routes.append((re.compile("^/api/" + pattern + "$"), binding["methods"], function.get_user_function()))


class Handler(BaseHTTPRequestHandler):
    def handle_request(self):
        url = urlparse(self.path)
        for pattern, methods, operation in routes:
            match = pattern.match(url.path)
            if not match or self.command not in [m.name for m in methods]: continue
            request = func.HttpRequest(method=self.command, url="http://127.0.0.1:7079" + self.path,
                                      headers=dict(self.headers), params=dict(parse_qsl(url.query)),
                                      route_params=match.groupdict(), body=self.rfile.read(int(self.headers.get("Content-Length", 0))))
            result = operation(request)
            self.send_response(result.status_code)
            self.send_header("Content-Type", result.mimetype or "application/json")
            for key, value in result.headers.items(): self.send_header(key, value)
            self.end_headers(); self.wfile.write(result.get_body()); return
        self.send_error(404)
    do_GET = do_POST = do_PATCH = do_DELETE = handle_request
    def log_message(self, *_): pass


if __name__ == "__main__":
    with patch("requests.sessions.Session.request", side_effect=AssertionError("Cloud HTTP is disabled in the test harness")):
        print("Offline Azure handler test harness listening on 127.0.0.1:7079", flush=True)
        ThreadingHTTPServer(("127.0.0.1", 7079), Handler).serve_forever()
