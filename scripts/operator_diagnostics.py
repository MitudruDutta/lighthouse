"""Read private operator diagnostics from this checkout's .env. Never print credentials."""

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from dotenv import dotenv_values

settings = {**dotenv_values(Path(__file__).resolve().parents[1] / ".env"), **os.environ}
token = settings.get("LIGHTHOUSE_OPERATOR_TOKEN", "")
if not token:
    raise SystemExit("Run ./start.sh first to create the private operator token.")
request = urllib.request.Request(
    f"http://127.0.0.1:{settings.get('API_PORT', '8100')}/api/operator/diagnostics",
    headers={"Authorization": f"Bearer {token}"},
)
try:
    with urllib.request.urlopen(request, timeout=15) as response:
        print(json.dumps(json.load(response), indent=2))
except urllib.error.HTTPError as exc:
    raise SystemExit(f"Operator diagnostics unavailable (HTTP {exc.code}).") from None
except (urllib.error.URLError, TimeoutError):
    raise SystemExit("Cannot reach the local API. Start Lighthouse and try again.") from None
