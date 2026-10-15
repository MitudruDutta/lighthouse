"""Memory documentation must not drift back into application or local-setup guides."""
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1] / 'docs-site/app'


class MemoryDocsTests(unittest.TestCase):
    def test_search_index_contains_only_existing_memory_pages(self):
        pages = json.loads((ROOT / 'search-index.json').read_text())
        paths = {page['path'] for page in pages}
        self.assertTrue({'/library', '/reference', '/integrations', '/falkordb'} <= paths)
        self.assertFalse(paths & {'/run', '/http', '/configuration', '/desk-agent', '/port-desk'})
        for page in pages:
            source = ROOT / page['path'].lstrip('/')
            self.assertTrue(any((source / ('page.' + extension)).exists() for extension in ('tsx', 'mdx')), page['path'])
            for forbidden in ('setup.sh', 'start.sh', 'LIGHTHOUSE_MODEL_KEY', 'Open workspace', 'Fintraffic', 'PortWatch'):
                self.assertNotIn(forbidden, page['text'])

    def test_internal_article_and_navigation_links_resolve(self):
        paths = {page['path'] for page in json.loads((ROOT / 'search-index.json').read_text())}
        for source in [*ROOT.rglob('page.mdx'), ROOT / 'page.tsx', ROOT / 'layout.tsx', ROOT / 'pages.ts']:
            text = source.read_text()
            links = re.findall(r'\]\((/[^)]+)\)|href="(/[^"}]+)"|\["(/[^"#]+)",', text)
            for group in links:
                route = next(value for value in group if value).split('#')[0]
                self.assertIn(route, paths, f'{source}: {route}')
        self.assertNotIn('localhost:3000', (ROOT / 'layout.tsx').read_text())


if __name__ == '__main__':
    unittest.main()
