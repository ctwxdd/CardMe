#!/usr/bin/env python3
"""Check release metadata, local documentation links, and public-source hygiene."""
import json
from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
release = json.loads((root / 'VERSION.json').read_text())
assert re.fullmatch(r'0\.\d+\.\d+', release['version'])
assert isinstance(release['build'], int) and release['build'] > 0
project = (root / 'CardRescue.xcodeproj/project.pbxproj').read_text()
assert set(re.findall(r'MARKETING_VERSION = ([^;]+);', project)) == {release['version']}
assert set(re.findall(r'CURRENT_PROJECT_VERSION = ([^;]+);', project)) == {str(release['build'])}
assert 'Permission is hereby granted' in (root / 'LICENSE').read_text()
assert not (root / 'engine/card_directory.json').exists()
assert not (root / 'engine/verified-rescue-profile.json').exists()
assert not (root / 'investigations').exists()
for path in [root / 'README.md', root / 'CONTRIBUTING.md', root / 'docs/RELEASING.md']:
    for link in re.findall(r'\]\(([^)]+)\)', path.read_text()):
        if not link.startswith(('https://', '#')):
            assert (path.parent / link).exists(), (path.name, link)
print('Version, license, documentation links, and private-fixture exclusions checked.')
