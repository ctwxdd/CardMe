#!/usr/bin/env python3
"""Verify bilingual bundles, format safety and actual Cocoa language selection."""
import json, plistlib, re, shutil, subprocess, tempfile
from pathlib import Path
root = Path(__file__).resolve().parents[1]
localizations = root / 'Sources/Localization'
def strings(path):
    return json.loads(subprocess.check_output(['plutil', '-convert', 'json', '-o', '-', str(path)]))
en = strings(localizations / 'en.lproj/Localizable.strings')
zh = strings(localizations / 'zh-Hant.lproj/Localizable.strings')
assert en.keys() == zh.keys()
source = (root / 'Sources/CardRescue.swift').read_text() + (root / 'Sources/ResultExport.swift').read_text()
keys = {json.loads('"' + match + '"') for match in re.findall(r'\bL\("((?:[^"\\]|\\.)*)"', source)}
assert keys == set(en), (keys - set(en), set(en) - keys)
for key, value in zh.items():
    assert re.findall(r'%(?:%|ld|@)', key) == re.findall(r'%(?:%|ld|@)', value), key
    assert value and value != key, key
for lang in ['en', 'zh-Hant']:
    assert set(strings(localizations / (lang+'.lproj/InfoPlist.strings'))) == {'NSRemovableVolumesUsageDescription', 'NSDocumentsFolderUsageDescription', 'NSDownloadsFolderUsageDescription'}
with tempfile.TemporaryDirectory(prefix='cardme-localization-', dir=root / 'work') as folder:
    app = Path(folder) / 'LocalizationCheck.app'
    executable = app / 'Contents/MacOS/LocalizationCheck'
    executable.parent.mkdir(parents=True)
    resources = app / 'Contents/Resources'
    resources.mkdir()
    for lang in ['en', 'zh-Hant']:
        shutil.copytree(localizations / (lang+'.lproj'), resources / (lang+'.lproj'))
    (app / 'Contents/Info.plist').write_bytes(plistlib.dumps({'CFBundleExecutable': 'LocalizationCheck', 'CFBundleIdentifier': 'com.cardme.localization-check', 'CFBundlePackageType': 'APPL', 'CFBundleDevelopmentRegion': 'en', 'CFBundleLocalizations': ['en', 'zh-Hant']}))
    subprocess.run(['xcrun', 'swiftc', '-D', 'TESTING', '-parse-as-library', '-swift-version', '5', str(root/'Sources/CardRescue.swift'), str(root/'Sources/ResultExport.swift'), str(root/'tests/LocalizationCheck.swift'), '-o', str(executable)], check=True)
    for lang in ['en', 'zh-Hant', 'zh-Hant-TW', 'fr']:
        subprocess.run([str(executable), '-AppleLanguages', '('+lang+')'], check=True)
print(f'{len(en)} bilingual strings, all placeholders and Cocoa fallback checked.')
