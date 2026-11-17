"""Reject network resource dependencies and broken local browser assets."""
import re
from html.parser import HTMLParser
from pathlib import Path

root = Path(__file__).resolve().parents[1] / 'frontend'
class Resources(HTMLParser):
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        value = attrs.get('src') if tag in ('script', 'img') else attrs.get('href') if tag == 'link' else None
        if value:
            assert not re.match(r'^(https?:)?//', value), value
            if value.startswith('/vendor/'):
                assert (root / value.lstrip('/')).is_file(), value

for path in root.rglob('*.html'):
    Resources().feed(path.read_text(encoding='utf-8'))
assert 'FleetOps' in (root / 'about.html').read_text(encoding='utf-8')
print('PASS: local HTML assets and FleetOps About')
