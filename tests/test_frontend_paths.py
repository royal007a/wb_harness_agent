"""Regression for the public nginx /harness mount (never steal root routes)."""
import re
import subprocess
from html.parser import HTMLParser
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app


class Links(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.urls = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.urls.extend(value for key, value in attrs if key in {'href', 'src'})


@pytest.mark.parametrize('prefix', ['', '/harness'])
def test_every_page_and_asset_respects_mount(tmp_path, prefix):
    with TestClient(create_app(tmp_path / 'db.sqlite', run_worker=False), base_url='http://127.0.0.1') as client:
        for page in ['/', '/docs', '/research', '/research-agents', '/agent-lab', '/agent-runtime', '/connectors/baidu-netdisk']:
            response = client.get(page, headers={'X-Forwarded-Prefix': prefix})
            assert response.status_code == 200
            assert "base-uri 'none'" in response.headers['content-security-policy']
            links = Links(response.text).urls
            assert prefix + '/static/paths.js' in links
            for link in links:
                if link.startswith(('#', 'https:', 'http:')):
                    continue
                assert link.startswith(prefix + '/'), (page, link)
                local_path = link[len(prefix):]
                if local_path.startswith('/static/'):
                    asset = client.get(local_path)
                    assert asset.status_code == 200
                    expected_type = 'text/css' if local_path.endswith('.css') else 'javascript'
                    assert expected_type in asset.headers['content-type']
            # The dynamically loaded JS cannot rely on a root-only fetch.
            for script in [p for p in links if p.endswith('.js') and not p.endswith('/paths.js')]:
                text = client.get(script[len(prefix):]).text
                assert not re.search(r'fetch\((?!HarnessURLs\.url)', text)
                assert 'crypto.randomUUID' not in text


def test_invalid_prefix_cannot_inject_page_or_redirect(tmp_path):
    with TestClient(create_app(tmp_path / 'db.sqlite', run_worker=False), base_url='http://127.0.0.1') as client:
        for prefix in ['//example.com', '/harness/', '/other', '/harness/../', '/harness"><script>']:
            result = client.get('/', headers={'X-Forwarded-Prefix': prefix})
            assert result.status_code == 400
            assert result.json()['error']['code'] == 'INVALID_PROXY_PREFIX'


def test_browser_paths_and_insecure_http_uuid():
    subprocess.run(['node', '--test', 'tests/frontend_paths.test.cjs'], cwd=Path(__file__).resolve().parents[1], check=True)
