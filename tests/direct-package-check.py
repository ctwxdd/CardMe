#!/usr/bin/env python3
"""Check the built direct-download DMG and its non-sandboxed app/helper."""
import pathlib
import hashlib
import os
import plistlib
import subprocess
import argparse

root = pathlib.Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--build-dir', type=pathlib.Path, default=root / 'build')
build_dir = parser.parse_args().build_dir
app = build_dir / 'CardMe.app'
release = __import__('json').loads((root / 'VERSION.json').read_text())
info = plistlib.loads((app / 'Contents/Info.plist').read_bytes())
assert info['CFBundleShortVersionString'] == release['version']
assert info['CFBundleVersion'] == str(release['build'])
assert info['CardRescueDirectDownload'] is True
assert info['CFBundleName'] == info['CFBundleDisplayName'] == 'CardMe'
assert info['CFBundleIdentifier'] == 'com.nick.cardrescue.direct'
subprocess.run(['codesign', '--verify', '--deep', '--strict', str(app)], check=True)
resources = app / 'Contents/Resources'
assert (resources / 'engine/native/jpeg-ranker.cpp').read_bytes() == (root / 'engine/native/jpeg-ranker.cpp').read_bytes()
assert (resources / 'engine/native/jpeg-ranker').is_file()
assert not (resources / 'engine/card_directory.json').exists()
assert not (resources / 'engine/verified-rescue-profile.json').exists()
assert (resources / 'ThirdPartyLicenses/CardMe-GPL-3.0.txt').read_bytes() == (root / 'LICENSE').read_bytes()
assert (resources / 'ThirdPartyLicenses/CardMe-Copyright.txt').read_bytes() == (root / 'NOTICE').read_bytes()
for source in (root / 'engine').glob('*.py'):
    assert (resources / 'engine' / source.name).read_bytes() == source.read_bytes(), source.name
for target in [app, resources / 'python/bin/python3', resources / 'tools/ddrescue', resources / 'engine/native/jpeg-ranker']:
    result = subprocess.run(['codesign', '-d', '--entitlements', ':-', str(target)], capture_output=True, check=True)
    data = result.stdout
    entitlements = plistlib.loads(data) if data.strip() else {}
    assert not entitlements.get('com.apple.security.app-sandbox'), target
    assert not entitlements.get('com.apple.security.inherit'), target
for filename in ['CardMe-GPL-3.0.txt', 'CardMe-Copyright.txt', 'Notices.md', 'ddrescue-GPL-2.0.txt', 'ddrescue-AUTHORS.txt', 'Python-LICENSE.txt', 'Pillow-and-codecs-LICENSE.txt']:
    assert (resources / 'ThirdPartyLicenses' / filename).stat().st_size > 0
for filename in ['ddrescue-1.30.tar.lz', 'ddrescue-BUILD.md', 'input-fd.patch', 'Python-3.12.14.tar.xz', 'Python-BUILD.md', 'build-runtime.py']:
    source = resources / 'ThirdPartySources' / filename
    assert source.stat().st_size > 0
    if filename.endswith(('.tar.lz', '.tar.xz')):
        upstream = root / 'vendor' / ('ddrescue' if 'ddrescue' in filename else 'python') / filename
        assert hashlib.sha256(source.read_bytes()).digest() == hashlib.sha256(upstream.read_bytes()).digest()
env = {**os.environ, 'PYTHONHOME': str(resources / 'python')}
subprocess.run([str(resources / 'python/bin/python3'), '-B', '-c', "import sysconfig; assert 'readline' not in sysconfig.get_config_var('MODLIBS')"], env=env, check=True)
subprocess.run(['hdiutil', 'verify', str(build_dir / 'CardMe.dmg')], check=True)
print('Direct-download identity, signatures, non-sandboxed helper and DMG verified.')
