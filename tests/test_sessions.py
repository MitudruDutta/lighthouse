"""A session cookie must survive arriving from another site, and every reload after it."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
ROUTES = ['frontend/app/api/auth/[action]/route.ts', 'memory-site/app/api/auth/[action]/route.ts']


class SessionCookieTests(unittest.TestCase):
    def test_sign_in_cookies_are_lax(self):
        # A strict cookie is left out when a page is reached from another site, and on every
        # reload of that page: the person looks signed out though the session is valid.
        for route in ROUTES:
            text = (ROOT / route).read_text()
            self.assertEqual(re.findall(r'sameSite: "(\w+)"', text), ['lax'], route)


if __name__ == '__main__':
    unittest.main()
