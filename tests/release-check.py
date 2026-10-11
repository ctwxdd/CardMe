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
license_text = (root / 'LICENSE').read_text()
assert 'SPDX-License-Identifier: GPL-3.0-only' in license_text
assert 'Copyright (c) 2026 CHUN-TING WU' in license_text
assert '15. Disclaimer of Warranty.' in license_text
assert '16. Limitation of Liability.' in license_text
assert 'Permission is hereby granted' in (root / 'docs/licenses/MIT-previous.txt').read_text()
license_file = 'CardMe-GPL-3.0.txt'
assert license_file in (root / 'Sources/CardRescue.swift').read_text()
assert license_file in (root / 'scripts/build.py').read_text()
assert license_file in (root / 'tests/direct-package-check.py').read_text()
assert not (root / 'engine/card_directory.json').exists()
assert not (root / 'engine/verified-rescue-profile.json').exists()
assert not (root / 'investigations').exists()
for path in [root / 'README.md', root / 'CONTRIBUTING.md', root / 'docs/RELEASING.md', root / 'docs/LICENSING.md']:
    for link in re.findall(r'\]\(([^)]+)\)', path.read_text()):
        if not link.startswith(('https://', '#')):
            assert (path.parent / link).exists(), (path.name, link)
print('Version, license, documentation links, and private-fixture exclusions checked.')

app = (root / "Sources/CardRescue.swift").read_text().split("struct CardRescueApp: App", 1)[1]
assert app.index("WindowGroup") < app.index("Settings {"), "Recovery window must be the primary launch scene"
