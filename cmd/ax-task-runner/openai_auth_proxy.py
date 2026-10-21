# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Loopback auth-injecting proxy for OpenAI-compatible gateways.

The Antigravity SDK's OpenAI-compatible connection is built for local, no-auth
model servers and does not send an Authorization header. This proxy sits in
front of it: the agent points at http://127.0.0.1:<port><path> and this process
adds `Authorization: Bearer $OPENAI_API_KEY` and forwards to the real gateway
(OPENAI_UPSTREAM_BASE_URL) with TLS verification disabled, so it also passes
through Agent Substrate's egress MITM. Responses are streamed so SSE works.

Env:
  OPENAI_UPSTREAM_BASE_URL  the real gateway base URL (host/scheme used)
  OPENAI_API_KEY            bearer token injected on every request
  OPENAI_PROXY_PORT         loopback port to listen on (default 8787)
"""

import http.client
import http.server
import os
import ssl
import urllib.parse

UPSTREAM = os.environ["OPENAI_UPSTREAM_BASE_URL"].rstrip("/")
API_KEY = os.environ["OPENAI_API_KEY"]
PORT = int(os.environ.get("OPENAI_PROXY_PORT", "8787"))

_u = urllib.parse.urlparse(UPSTREAM)
UP_HOST = _u.hostname
UP_PORT = _u.port or (443 if _u.scheme == "https" else 80)
UP_HTTPS = _u.scheme == "https"
_CTX = ssl._create_unverified_context()

_HOP_BY_HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
               "te", "trailers", "transfer-encoding", "upgrade", "content-length"}


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _proxy(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        body = self.rfile.read(length) if length else None

        headers = {k: v for k, v in self.headers.items()
                   if k.lower() not in _HOP_BY_HOP and k.lower() not in ("host", "authorization")}
        headers["Host"] = UP_HOST
        headers["Authorization"] = "Bearer " + API_KEY
        if body is not None:
            headers["Content-Length"] = str(len(body))

        if UP_HTTPS:
            conn = http.client.HTTPSConnection(UP_HOST, UP_PORT, context=_CTX, timeout=600)
        else:
            conn = http.client.HTTPConnection(UP_HOST, UP_PORT, timeout=600)
        try:
            conn.request(self.command, self.path, body=body, headers=headers)
            resp = conn.getresponse()
            self.send_response_only(resp.status)
            for k, v in resp.getheaders():
                if k.lower() in _HOP_BY_HOP:
                    continue
                self.send_header(k, v)
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            while True:
                chunk = resp.read(4096)
                if not chunk:
                    break
                self.wfile.write(b"%X\r\n" % len(chunk) + chunk + b"\r\n")
                self.wfile.flush()
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()
        finally:
            conn.close()

    do_GET = _proxy
    do_POST = _proxy
    do_DELETE = _proxy

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
