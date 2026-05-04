#!/usr/bin/env python3
"""
Minimal HMAC-validated webhook server for CI/CD deploys.
Listens on WEBHOOK_PORT (default 9000), validates X-Deploy-Token,
then runs scripts/deploy.sh <service> <tag> in a background thread.

Required env var:
  DEPLOY_TOKEN   — shared secret; GitHub Actions signs the body with it

Optional env var:
  WEBHOOK_PORT   — default 9000

GitHub Actions sends:
  POST /webhook
  X-Deploy-Token: <hex HMAC-SHA256 of request body using DEPLOY_TOKEN>
  X-Service: autoagent | cua | trend-radar | synapse | all
  X-Image-Tag: <git sha>
"""

import hashlib
import hmac
import http.server
import json
import os
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path

PORT = int(os.getenv("WEBHOOK_PORT", "9000"))
TOKEN: bytes = os.environ["DEPLOY_TOKEN"].encode()
DEPLOY_SCRIPT = str(Path(__file__).parent / "deploy.sh")
ALLOWED_SERVICES = {"autoagent", "cua", "trend-radar", "synapse", "all"}


def _log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def _run_deploy(service: str, tag: str) -> None:
    _log(f"→ deploy {service} @ {tag}")
    result = subprocess.run(
        ["/bin/bash", DEPLOY_SCRIPT, service, tag],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        _log(f"✔ deploy OK: {service}")
    else:
        _log(f"✘ deploy FAILED: {service}\n{result.stderr.strip()}")


class _Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_POST(self) -> None:
        if self.path != "/webhook":
            self._respond(404, {"error": "not found"})
            return

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)

        expected = hmac.new(TOKEN, body, hashlib.sha256).hexdigest()
        received = self.headers.get("X-Deploy-Token", "")
        if not hmac.compare_digest(expected, received):
            _log("⚠ bad token — rejected")
            self._respond(403, {"error": "forbidden"})
            return

        service = self.headers.get("X-Service", "all")
        tag = self.headers.get("X-Image-Tag", "latest")

        if service not in ALLOWED_SERVICES:
            self._respond(400, {"error": f"unknown service: {service}"})
            return

        threading.Thread(
            target=_run_deploy, args=(service, tag), daemon=True
        ).start()
        self._respond(202, {"accepted": True, "service": service, "tag": tag})

    def _respond(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    _log(f"Webhook server listening on :{PORT}")
    http.server.HTTPServer(("0.0.0.0", PORT), _Handler).serve_forever()
