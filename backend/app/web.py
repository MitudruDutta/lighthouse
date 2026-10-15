"""Reading JSON from public services, without trusting the answer.

Only https is read (urllib would also open a local file). The body is cut off at a size
before and after it is unpacked, since a small gzip body can hold gigabytes. What does not
parse as JSON raises ValueError, and so does a body nested too deep to parse.
"""

import json
import urllib.parse
import urllib.request
import zlib

MOST = 50_000_000  # bytes of one answer: far more than any answer these services give


def read_json(url: str, what: str, headers=None, params=None, most: int = MOST):
    """The JSON that `url` answers, with `params` as its query. `what` names the source in
    errors, such as "the feed"."""
    if not url.startswith("https://"):
        raise ValueError(f"{what} is read over https only")
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"Accept-Encoding": "gzip", **(headers or {})})
    with urllib.request.urlopen(request, timeout=30) as response:
        body = response.read(most + 1)
        if response.headers.get("Content-Encoding") == "gzip":
            body = zlib.decompressobj(wbits=31).decompress(body, most + 1)
    if len(body) > most:
        raise ValueError(f"{what} answer is larger than {most} bytes")
    try:
        return json.loads(body)
    except (ValueError, RecursionError) as exc:
        raise ValueError(f"{what} answer is not JSON: {type(exc).__name__}") from None
