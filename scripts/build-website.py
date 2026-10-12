#!/usr/bin/env python3
"""Generate indexable localized landing pages from shared copy and markup."""
import hashlib, json
from html import escape as esc
from pathlib import Path

root = Path(__file__).resolve().parents[1]
site = root / 'website/dist'
locales = {p.stem: json.loads(p.read_text()) for p in sorted((root / 'website/locales').glob('*.json'))}
base = 'https://witty-meadow-00543f01e.6.azurestaticapps.net'
download = 'https://github.com/ctwxdd/CardMe/releases/download/v0.3.37/CardMe-0.3.37.dmg'
source = download.replace('.dmg', '-source.tar.gz')
css_version = hashlib.sha256((site / 'style.css').read_bytes()).hexdigest()[:12]
def route(lang):
    return '/' if lang == 'en' else '/' + lang.lower()
alternates = '\n'.join(f'<link rel="alternate" hreflang="{lang}" href="{base}{route(lang)}">' for lang in locales)
alternates += f'\n<link rel="alternate" hreflang="x-default" href="{base}/">'
for lang, d in locales.items():
    url = base + route(lang)
    schema = {'@context': 'https://schema.org', '@type': 'SoftwareApplication', 'name': 'CardMe', 'url': url, 'inLanguage': lang, 'operatingSystem': 'macOS 14 or later; Apple silicon', 'applicationCategory': 'UtilitiesApplication', 'description': d['description'], 'offers': {'@type': 'Offer', 'price': '0', 'priceCurrency': 'USD'}, 'downloadUrl': download}
    language_links = []
    for code, copy in locales.items():
        current = ' aria-current="page"' if code == lang else ''
        language_links.append(f'<a href="{route(code)}" hreflang="{code}" lang="{code}"{current}>{esc(copy["name"])}</a>')
    links = ' · '.join(language_links)
    steps = ''.join(f'<article><span class="number">{i:02}</span><h3>{esc(title)}</h3><p>{esc(body)}</p></article>' for i, (title, body) in enumerate(d['steps'], 1))
    questions = ''.join(f'<details><summary>{esc(title)}</summary><p>{esc(body)}</p></details>' for i, (title, body) in enumerate(d['faq']))
    trust = ''.join(f'<p>{esc(text)}</p>' for text in d['trust'])
    html = f'''<!doctype html>
<html lang="{lang}"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(d['title'])}</title><meta name="description" content="{esc(d['description'], quote=True)}">
<script src="/metrics.js" defer></script>
<meta name="theme-color" content="#ffffff"><meta name="robots" content="index,follow">
<link rel="canonical" href="{url}">{alternates}
<meta property="og:type" content="website"><meta property="og:title" content="{esc(d['title'], quote=True)}">
<meta property="og:description" content="{esc(d['description'], quote=True)}"><meta property="og:url" content="{url}">
<meta property="og:image" content="{base}/assets/cardme-app.png">
<meta name="twitter:card" content="summary_large_image">
<link rel="icon" href="/assets/favicon.png" type="image/png"><link rel="apple-touch-icon" href="/assets/apple-touch-icon.png">
<link rel="stylesheet" href="/style.css?v={css_version}">
<script type="application/ld+json">{json.dumps(schema, ensure_ascii=False, separators=(',', ':')).replace('<', chr(92)+'u003c')}</script>
</head><body>
<header class="wrap header"><a class="brand" href="{route(lang)}" aria-label="CardMe"><img src="/assets/cardme-mark.svg" width="40" height="40" alt="">CardMe</a><nav><a href="#how-it-works">{esc(d['nav'][0])}</a><a href="#questions">{esc(d['nav'][1])}</a><a class="coffee-link" href="https://ko-fi.com/alittleseal" target="_blank" rel="noopener noreferrer">{esc(d['coffee'])}</a></nav></header>
<main><section class="wrap hero" aria-labelledby="intro"><div class="intro"><p class="eyebrow">{esc(d["kicker"])}</p><h1 id="intro">{d['heading']}</h1></div><div class="hero-actions"><p class="lead">{esc(d['lead'])}</p><a class="primary" href="{download}" data-download>{esc(d['download'])}<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="M12 3v12m-4-4 4 4 4-4M5 16v4h14v-4"/></svg></a><p class="requirements">macOS 14+ · Apple silicon<br>{esc(d['appNote'])}<br><a href="{source}" class="source-link">{esc(d['source'])} · GPL-3.0</a></p><p class="coffee-note"><a href="https://ko-fi.com/alittleseal" target="_blank" rel="noopener noreferrer">{esc(d['support'])} ☕️</a></p></div></section>
<figure class="wrap app-preview"><div class="app-stage"><div class="app-window"><img src="/assets/cardme-app.png" width="1480" height="1084" alt="{esc(d['caption'], quote=True)}"></div></div><figcaption>{esc(d['caption'])}</figcaption></figure><div class="wrap trust">{trust}</div>
<aside class="wrap safety-note"><strong>{esc(d["warningTitle"])}</strong><span>{esc(d["warning"])}</span></aside><section class="wrap steps-section" id="how-it-works"><h2>{esc(d['stepsTitle'])}</h2><div class="steps">{steps}</div></section>
<section class="wrap questions" id="questions"><div><h2>{esc(d['nav'][1])}</h2></div><div class="answers">{questions}</div></section></main>
<details class="wrap language-picker"><summary>{esc(d['name'])}</summary><nav class="languages" aria-label="{esc(d['languageLabel'], quote=True)}">{links}</nav></details>
<footer class="wrap footer"><span>CardMe</span><a href="https://github.com/ctwxdd/CardMe" target="_blank" rel="noopener noreferrer">GitHub</a><span>{esc(d['version'])}</span></footer>
</body></html>
'''
    target = site / ('index.html' if lang == 'en' else lang.lower() + '/index.html')
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(html)
xml = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + ''.join(f'  <url><loc>{base}{route(lang)}</loc></url>\n' for lang in locales) + '</urlset>\n'
(site / 'sitemap.xml').write_text(xml)
(site / 'robots.txt').write_text(f'User-agent: *\nAllow: /\nSitemap: {base}/sitemap.xml\n')
config = {'routes': [{'route': '/admin', 'rewrite': '/admin/index.html', 'headers': {'X-Robots-Tag': 'noindex, nofollow'}}, {'route': '/admin/*', 'headers': {'X-Robots-Tag': 'noindex, nofollow'}}] + [{'route': route(lang), 'rewrite': '/' + lang.lower() + '/index.html'} for lang in locales if lang != 'en'], 'globalHeaders': {'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer', 'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; connect-src https://cardme-control-plane.azurewebsites.net/api/v1/usage"}}
(site / 'staticwebapp.config.json').write_text(json.dumps(config, indent=2) + '\n')
print(f'Generated {len(locales)} localized pages and sitemap.')
