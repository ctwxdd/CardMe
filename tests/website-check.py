#!/usr/bin/env python3
"""Check localized SEO routes, reciprocal language links and truthful app metadata."""
import hashlib, json, re
from html.parser import HTMLParser
from pathlib import Path
import xml.etree.ElementTree as ET
root = Path(__file__).resolve().parents[1]
class Page(HTMLParser):
    def __init__(self):
        super().__init__(); self.links = []; self.lang = ''; self.schema = ''; self.in_schema = False; self.headings = 0
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'html': self.lang = a['lang']
        if tag == 'link': self.links.append(a)
        if tag == 'script': self.in_schema = a.get('type') == 'application/ld+json'
        if tag == 'h1': self.headings += 1
    def handle_endtag(self, tag):
        if tag == 'script': self.in_schema = False
    def handle_data(self, data):
        if self.in_schema: self.schema += data
locales = {p.stem: json.loads(p.read_text()) for p in (root/'website/locales').glob('*.json')}
# Public downloads can lag an unreleased development build.
public_versions = {re.search(r'\b\d+\.\d+\.\d+', d['version']).group() for d in locales.values()}
assert len(public_versions) == 1
version = public_versions.pop()
assert tuple(map(int, version.split('.'))) <= tuple(map(int, json.loads((root/'VERSION.json').read_text())['version'].split('.')))
expected = {'https://getpickology.com/cardme' if lang == 'en' else 'https://getpickology.com/cardme/'+lang.lower() for lang in locales}
css_version = hashlib.sha256((root/'website/dist/style.css').read_bytes()).hexdigest()[:12]
for lang in locales:
    path = root/'website/dist'/('index.html' if lang == 'en' else lang.lower()+'/index.html')
    body = path.read_text(); p = Page(); p.feed(body)
    assert p.lang == lang and p.headings == 1 and '�' not in body
    canonical = [a['href'] for a in p.links if a.get('rel') == 'canonical']
    assert len(canonical) == 1 and canonical[0] in expected
    alternates = {a['hreflang']: a['href'] for a in p.links if a.get('rel') == 'alternate'}
    assert set(alternates) == set(locales) | {'x-default'}
    assert set(alternates.values()) == expected
    schema = json.loads(p.schema)
    assert schema['offers']['price'] == '0' and schema['inLanguage'] == lang
    assert schema['downloadUrl'] == 'https://getpickology.com/cardme/download'
    assert 'aggregateRating' not in schema and 'review' not in schema
    assert version in body and '/cardme/assets/cardme-mark.svg' in body
    assert any(a.get('rel') == 'stylesheet' and a.get('href') == '/cardme/style.css?v='+css_version for a in p.links)
    assert len(locales[lang]['faq']) >= 9
    assert 'class="wrap support"' not in body
    assert body.count('href="https://ko-fi.com/alittleseal"') == 2
    assert 'ko-fi.com' not in body.split('<footer')[1]
ns = {'s': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
assert {n.text for n in ET.parse(root/'website/dist/sitemap.xml').findall('.//s:loc', ns)} == expected
print(f'{len(locales)} languages: unique canonicals, reciprocal hreflang, sitemap, free app schema and secondary donation link checked.')
